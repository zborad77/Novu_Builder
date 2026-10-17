#!/bin/sh
# Static validation of the deploy/linux configuration on Ubuntu 24.04 (CI or a
# disposable container – never on a production host):
#   docker run --rm --cap-add NET_ADMIN -v "$PWD:/src:ro" ubuntu:24.04 \
#       sh /src/deploy/linux/tests/validate-configs.sh
# Checks: nginx -t, nft -c -f (all three rulesets), systemd-analyze verify,
# shell syntax of the helpers, and that no template carries a real-looking secret.
set -eu
SRC=${SRC:-/src}
D="$SRC/deploy/linux"
export DEBIAN_FRONTEND=noninteractive

if ! command -v nginx >/dev/null || ! command -v nft >/dev/null || ! command -v systemd-analyze >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq nginx nftables systemd openssl >/dev/null
fi

fail=0
ok()   { echo "OK   $*"; }
bad()  { echo "FAIL $*"; fail=1; }

# ── users/groups referenced by units and rulesets ─────────────────────────────
getent group nc-api-sock >/dev/null || groupadd --system nc-api-sock
getent group novuconstruct >/dev/null || groupadd --system novuconstruct
id novuconstruct >/dev/null 2>&1 || useradd --system -g novuconstruct -G nc-api-sock -d /nonexistent -s /usr/sbin/nologin novuconstruct

# ── nginx ────────────────────────────────────────────────────────────────────
mkdir -p /etc/nginx/snippets /etc/novuconstruct/tls /var/www/novuconstruct/public /var/www/letsencrypt
cp "$D"/nginx/snippets/*.conf /etc/nginx/snippets/
cp "$D/nginx/nc-http-common.conf" /etc/nginx/conf.d/00-nc-http-common.conf
cp "$D/nginx/nc-core-private.conf" "$D/nginx/nc-edge-public.conf" /etc/nginx/conf.d/
rm -f /etc/nginx/sites-enabled/default
# nginx -t binds listeners: give the container the WireGuard addresses on lo.
command -v ip >/dev/null || apt-get install -y -qq iproute2 >/dev/null
ip addr add 10.50.0.1/32 dev lo 2>/dev/null || true
ip addr add 10.51.0.1/32 dev lo 2>/dev/null || true
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=validate.invalid" \
  -keyout /etc/novuconstruct/tls/privkey.pem -out /etc/novuconstruct/tls/fullchain.pem >/dev/null 2>&1
if nginx -t -q; then ok "nginx -t (core-private + edge-public)"; else bad "nginx -t"; fi

# Core listeners must be WireGuard addresses only; the edge must not proxy.
if grep -E '^\s*listen' "$D/nginx/nc-core-private.conf" | grep -vqE 'listen 10\.5[01]\.0\.1:'; then
  bad "nc-core-private.conf listens outside WireGuard addresses"
else ok "core listeners bound to WireGuard addresses"; fi
if grep -qE '^\s*proxy_pass' "$D/nginx/nc-edge-public.conf"; then
  bad "edge must not proxy to the core in this phase"
else ok "edge has no proxy_pass"; fi

# ── nftables ─────────────────────────────────────────────────────────────────
for ruleset in "$D"/nftables/*.nft; do
  if nft -c -f "$ruleset"; then ok "nft -c $(basename "$ruleset")"; else bad "nft -c $(basename "$ruleset")"; fi
done
for ruleset in "$D"/nftables/nc-single-server.nft "$D"/nftables/nc-core.nft; do
  for port in 5432 6379 9000 9001 8000; do
    if grep -E "dport[^;]*\b$port\b" "$ruleset" | grep -q accept; then bad "$(basename "$ruleset") opens $port"; fi
  done
done
ok "no ruleset opens PostgreSQL/Redis/MinIO/raw API ports"

# ── systemd ──────────────────────────────────────────────────────────────────
mkdir -p /opt/novuconstruct/python-backend/.venv/bin /opt/novuconstruct/deploy/linux/bin /etc/novuconstruct/secrets
cp "$D"/bin/* /opt/novuconstruct/deploy/linux/bin/ && chmod 0755 /opt/novuconstruct/deploy/linux/bin/*
for exe in uvicorn python; do printf '#!/bin/sh\n' > "/opt/novuconstruct/python-backend/.venv/bin/$exe"; chmod 0755 "/opt/novuconstruct/python-backend/.venv/bin/$exe"; done
touch /etc/novuconstruct/core.env
units=$(mktemp -d)
cp "$D"/systemd/*.service "$D"/systemd/*.target "$units/"
chmod 0644 "$units"/*
grep -q 'After=.*nftables.service.*wg-quick@wg-nc' "$D/systemd/nginx.service.d/10-novuconstruct.conf" \
  && ok "nginx ordered after nftables and WireGuard" || bad "nginx drop-in missing ordering"
cp "$units/nc-api@.service" "$units/nc-api@desktop.service"
cp "$units/nc-api@.service" "$units/nc-api@admin.service"
chmod 0644 "$units"/*
if SYSTEMD_LOG_LEVEL=warning systemd-analyze verify --man=no "$units/nc-api@desktop.service" "$units/nc-api@admin.service" "$units/nc-worker.service" "$units/nc-core.target" 2>&1 | grep -v -E "Failed to (connect|open|create).*bus|Unit.*not found|postgresql|redis-server|minio" | grep . ; then
  bad "systemd-analyze verify reported problems"
else ok "systemd-analyze verify"; fi
# F6.1: sandbox exposure below 3.0 ("threshold" is exposure x 10).
for unit in nc-api@desktop.service nc-worker.service; do
  if systemd-analyze security --offline=yes --threshold=30 "$units/$unit" >/tmp/sec.txt 2>&1; then
    ok "systemd-analyze security $unit: $(tail -n 1 /tmp/sec.txt | sed 's/.*exposure level for [^:]*: //')"
  else
    bad "systemd-analyze security $unit: $(tail -n 1 /tmp/sec.txt)"
  fi
done
grep -q '^Environment=NC_ZONE=%i' "$D/systemd/nc-api@.service" && ok "zone fixed per instance (NC_ZONE=%i)" || bad "NC_ZONE not fixed by the unit"
grep -q -- '--no-proxy-headers' "$D/systemd/nc-api@.service" && ok "uvicorn --no-proxy-headers" || bad "proxy headers not disabled"
grep -q -- '--uds ' "$D/systemd/nc-api@.service" && ok "API on unix socket only" || bad "API not on a unix socket"

# ── shell helpers ────────────────────────────────────────────────────────────
for script in "$D"/bin/* "$D"/tests/*.sh; do
  if sh -n "$script"; then ok "sh -n $(basename "$script")"; else bad "sh -n $(basename "$script")"; fi
done

# ── templates carry placeholders only ────────────────────────────────────────
if grep -rEn '(PrivateKey|PresharedKey)\s*=\s*[A-Za-z0-9+/]{43}=' "$D/wireguard"; then
  bad "WireGuard template contains a real-looking key"
else ok "WireGuard templates hold placeholders only"; fi

[ "$fail" -eq 0 ] && echo "ALL CHECKS PASSED" || { echo "VALIDATION FAILED"; exit 1; }
