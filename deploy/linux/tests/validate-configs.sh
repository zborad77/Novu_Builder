#!/bin/sh
# Static validation of the deploy/linux configuration on Ubuntu 24.04 (CI or a
# disposable container – never on a production host):
#   docker run --rm --cap-add NET_ADMIN -v "$PWD:/src:ro" ubuntu:24.04 \
#       sh /src/deploy/linux/tests/validate-configs.sh
# Checks: nginx -t (both gateway-zone variants), nft -c -f (all three rulesets),
# systemd-analyze verify + security, shellcheck and shell syntax of the helpers,
# that no template carries a real-looking secret, and for the Web Gateway (NC-007):
# edge vhost behaviour against a stub gateway (404 for /api, /docs, …; CSP without
# unsafe-*; X-Forwarded-For overwritten; X-NC-* dropped; body limits), the gateway
# unit's isolation from core secrets, nc-gen-secrets permissions and the ACL of
# the gateway Redis.
set -eu
SRC=${SRC:-/src}
D="$SRC/deploy/linux"
export DEBIAN_FRONTEND=noninteractive
export LANG=C.UTF-8

need=""
for tool in nginx nft systemd-analyze shellcheck redis-server redis-cli curl python3 ss; do
  command -v "$tool" >/dev/null || need=1
done
if [ -n "$need" ]; then
  apt-get update -qq
  apt-get install -y -qq nginx nftables systemd openssl shellcheck redis-server curl python3 iproute2 >/dev/null
fi

fail=0
ok()   { echo "OK   $*"; }
bad()  { echo "FAIL $*"; fail=1; }

# ── users/groups referenced by units and rulesets ─────────────────────────────
getent group nc-api-sock >/dev/null || groupadd --system nc-api-sock
getent group novuconstruct >/dev/null || groupadd --system novuconstruct
id novuconstruct >/dev/null 2>&1 || useradd --system -g novuconstruct -G nc-api-sock -d /nonexistent -s /usr/sbin/nologin novuconstruct
# Web Gateway accounts exactly as nc-provision creates them (no core groups).
getent group nc-gateway >/dev/null || groupadd --system nc-gateway
getent group nc-gw-redis >/dev/null || groupadd --system nc-gw-redis
id nc-gateway >/dev/null 2>&1 || useradd --system -g nc-gateway -G nc-gw-redis -d /nonexistent -s /usr/sbin/nologin nc-gateway
id nc-gw-redis >/dev/null 2>&1 || useradd --system -g nc-gw-redis -d /nonexistent -s /usr/sbin/nologin nc-gw-redis
# Object store account (S-1, Garage) exactly as nc-provision creates it.
getent group nc-garage >/dev/null || groupadd --system nc-garage
id nc-garage >/dev/null 2>&1 || useradd --system -g nc-garage -d /nonexistent -s /usr/sbin/nologin nc-garage

# ── nginx ────────────────────────────────────────────────────────────────────
mkdir -p /etc/nginx/snippets /etc/novuconstruct/tls /var/www/novuconstruct/public /var/www/novuconstruct/app/assets /var/www/letsencrypt
cp "$D"/nginx/snippets/*.conf /etc/nginx/snippets/
cp "$D/nginx/nc-http-common.conf" /etc/nginx/conf.d/00-nc-http-common.conf
cp "$D/nginx/nc-core-private.conf" "$D/nginx/nc-edge-public.conf" "$D/nginx/nc-edge-webapp.conf" /etc/nginx/conf.d/
rm -f /etc/nginx/sites-enabled/default
# nginx -t binds listeners: give the container the WireGuard addresses on lo.
ip addr add 10.50.0.1/32 dev lo 2>/dev/null || true
ip addr add 10.51.0.1/32 dev lo 2>/dev/null || true
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=validate.invalid" \
  -keyout /etc/novuconstruct/tls/privkey.pem -out /etc/novuconstruct/tls/fullchain.pem >/dev/null 2>&1
if nginx -t -q 2>/tmp/nginx-t.txt; then ok "nginx -t (core-private + edge-public + edge-webapp)"; else bad "nginx -t: $(cat /tmp/nginx-t.txt)"; fi
if grep -q '\[warn\]' /tmp/nginx-t.txt; then bad "nginx -t warnings: $(grep '\[warn\]' /tmp/nginx-t.txt | head -n 2)"; else ok "nginx -t without warnings"; fi
# Gateway zone on the core: variant A (WG address) and variant B (loopback) are
# alternatives installed under the same name; test each one.
cp "$D/nginx/nc-core-gateway.conf" /etc/nginx/conf.d/nc-core-gateway.conf
if nginx -t -q; then ok "nginx -t + nc-core-gateway.conf (variant A)"; else bad "nginx -t nc-core-gateway.conf"; fi
cp "$D/nginx/nc-core-gateway-single.conf" /etc/nginx/conf.d/nc-core-gateway.conf
if nginx -t -q; then ok "nginx -t + nc-core-gateway-single.conf (variant B)"; else bad "nginx -t nc-core-gateway-single.conf"; fi

# Core listeners must be WireGuard addresses only; the info site must not proxy.
if grep -E '^\s*listen' "$D/nginx/nc-core-private.conf" "$D/nginx/nc-core-gateway.conf" | grep -vqE 'listen 10\.5[01]\.0\.1:'; then
  bad "core vhosts listen outside WireGuard addresses"
else ok "core listeners bound to WireGuard addresses"; fi
if grep -E '^\s*listen' "$D/nginx/nc-core-gateway-single.conf" | grep -vqE 'listen 127\.0\.0\.1:8200;'; then
  bad "single-server gateway zone listens beyond loopback"
else ok "single-server gateway zone on 127.0.0.1:8200 only"; fi
if grep -qE '^\s*proxy_pass' "$D/nginx/nc-edge-public.conf"; then
  bad "information website must not proxy to anything"
else ok "information website has no proxy_pass"; fi
# The app vhost proxies only /bff/ and only to the gateway upstream.
bad_proxy=$(awk '
  /^[[:space:]]*location/ { loc = $0 }
  /^[[:space:]]*proxy_pass/ {
    if ($0 !~ /proxy_pass http:\/\/nc_gateway;/ || loc !~ /(\/bff\/|\^\/bff\/)/) print FILENAME ":" NR ": " $0 "  (in: " loc ")"
  }' "$D/nginx/nc-edge-webapp.conf")
if [ -n "$bad_proxy" ]; then bad "edge app proxies outside /bff/ → nc_gateway: $bad_proxy"; else ok "edge app proxies only /bff/ to nc_gateway"; fi
for path in '/api/' '/docs' '/openapi.json' '/metrics' '/admin'; do
  if grep -qE "^\s*location \^~ $(printf '%s' "$path" | sed 's/[.]/\\./g')\s*\{ return 404; \}" "$D/nginx/nc-edge-webapp.conf"; then :
  else bad "edge app: $path is not a 404 location"; fi
done
ok "edge app: /api/, /docs, /openapi.json, /metrics, /admin declared 404"
# CSP: no 'unsafe-*' anywhere; the SPA policy is exactly SECURITY_ARCHITECTURE §4.7.
if grep -rhiE "Content-Security-Policy|default-src" "$D/nginx" | grep -v '^[[:space:]]*#' | grep -qi "unsafe-"; then
  bad "a Content-Security-Policy contains unsafe-*"
else ok "no CSP contains unsafe-*"; fi
SPA_CSP="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
grep -qF "\"$SPA_CSP\"" "$D/nginx/nc-edge-webapp.conf" && ok "SPA CSP = SECURITY_ARCHITECTURE 4.7" || bad "SPA CSP differs from SECURITY_ARCHITECTURE 4.7"
if awk '/^[[:space:]]*location/,/}/' "$D/nginx/nc-edge-webapp.conf" | grep -q 'add_header'; then
  bad "edge app: add_header inside a location drops the inherited security headers"
else ok "edge app: security headers only at server level (inherited everywhere)"; fi
grep -q 'Strict-Transport-Security' "$D/nginx/nc-edge-webapp.conf" && ok "edge app sends HSTS" || bad "edge app without HSTS"
grep -q '^server_tokens off;' "$D/nginx/nc-http-common.conf" && ok "server_tokens off" || bad "server_tokens not off"
grep -q 'client_max_body_size 256k;' "$D/nginx/nc-edge-webapp.conf" && [ "$(grep -c 'client_max_body_size 25m;' "$D/nginx/nc-edge-webapp.conf")" -eq 1 ] \
  && ok "edge app: 256k default body, 25m only on the upload location" || bad "edge app body limits"
grep -q 'X-Forwarded-For    \$remote_addr;' "$D/nginx/snippets/nc-proxy-bff.conf" && ok "BFF proxy overwrites X-Forwarded-For with the TCP peer" || bad "BFF proxy X-Forwarded-For"
for h in X-NC-Client-IP X-NC-Gateway-Key X-NC-Gateway-Ts X-NC-Gateway-Nonce X-NC-Gateway-Sig X-NC-Zone; do
  grep -qE "proxy_set_header $h +\"\";" "$D/nginx/snippets/nc-proxy-bff.conf" || bad "BFF proxy forwards client $h"
done
ok "BFF proxy clears client X-NC-* headers"

# ── edge app against a stub gateway (behaviour, not just syntax) ─────────────
printf '<!doctype html><title>spa</title>\n' > /var/www/novuconstruct/app/index.html
printf 'console.log(1)\n' > /var/www/novuconstruct/app/assets/app.js
rm -f /etc/nginx/conf.d/nc-core-gateway.conf
cat > /tmp/stub_gateway.py <<'PY'
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
    def _reply(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if self.path == "/bff/health":
            out = {"status": "ok"}
        else:
            out = {"path": self.path, "method": self.command, "bodyLength": len(body),
                   "headers": {k.lower(): v for k, v in self.headers.items()}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _reply
    def log_message(self, *a):
        pass
ThreadingHTTPServer(("127.0.0.1", 8300), H).serve_forever()
PY
python3 /tmp/stub_gateway.py & stub=$!
nginx
sleep 1
APP=app.example.invalid
c() { curl -sk --path-as-is --resolve "$APP:443:127.0.0.1" "$@"; }
code() { c -o /dev/null -w '%{http_code}' "$@"; }
for path in /api/v1/health /api/v1/auth/login /api /docs /redoc /openapi.json /metrics /admin /admin/users /bff/../api/v1/health; do
  got=$(code "https://$APP$path")
  [ "$got" = 404 ] || bad "edge $path → $got (want 404)"
done
got=$(code -X POST "https://$APP/api/v1/auth/login"); [ "$got" = 404 ] || bad "edge POST /api/v1/auth/login → $got"
ok "edge: /api, /docs, /redoc, /openapi.json, /metrics, /admin → 404 (incl. dot-segment)"
hdr=$(c -D - -o /dev/null "https://$APP/")
printf '%s' "$hdr" | grep -qi "^content-security-policy: $SPA_CSP" && ok "edge /: SPA CSP served" || bad "edge /: CSP missing or different"
printf '%s' "$hdr" | grep -i '^content-security-policy' | grep -qi unsafe && bad "edge /: CSP has unsafe-*" || true
printf '%s' "$hdr" | grep -qi '^strict-transport-security: max-age=31536000' && ok "edge /: HSTS" || bad "edge /: no HSTS"
printf '%s' "$hdr" | grep -qiE '^server: nginx\s*$' && ok "edge /: no version in Server header" || bad "edge /: Server header leaks version"
[ "$(code "https://$APP/some/spa/route")" = 200 ] && ok "edge: SPA fallback to index.html" || bad "edge: SPA fallback"
[ "$(code -X POST "https://$APP/")" = 403 ] && ok "edge: static files GET/HEAD only" || bad "edge: POST on static files allowed"
c -D - -o /dev/null "https://$APP/assets/app.js" | grep -qi '^x-content-type-options: nosniff' && ok "edge: security headers on assets" || bad "edge: assets lose security headers"
[ "$(c "https://$APP/bff/health")" = '{"status": "ok"}' ] && ok "edge /bff/health → gateway" || bad "edge /bff/health not proxied"
c -D - -o /dev/null "https://$APP/bff/health" | grep -qi "^content-security-policy: default-src 'none'" && ok "edge /bff/: restrictive CSP" || bad "edge /bff/: CSP"
echo=$(c -H 'X-Forwarded-For: 203.0.113.66' -H 'X-Real-IP: 203.0.113.66' -H 'Forwarded: for=203.0.113.66' \
  -H 'X-NC-Client-IP: 203.0.113.66' -H 'X-NC-Gateway-Sig: forged' -H 'X-NC-Gateway-Key: forged' -H 'X-NC-Zone: admin' \
  "https://$APP/bff/api/cases?x=1")
printf '%s' "$echo" | python3 -c '
import json, sys
d = json.load(sys.stdin); h = d["headers"]
assert h.get("x-forwarded-for") == "127.0.0.1", h.get("x-forwarded-for")
assert h.get("x-forwarded-proto") == "https"
for k in ("x-real-ip", "forwarded", "x-nc-client-ip", "x-nc-gateway-sig", "x-nc-gateway-key", "x-nc-zone"):
    assert k not in h, k
assert d["path"] == "/bff/api/cases?x=1", d["path"]
' && ok "edge → gateway: X-Forwarded-For = TCP peer only, client X-NC-*/X-Real-IP/Forwarded dropped" \
  || bad "edge → gateway header hygiene: $echo"
raw=$(c "https://$APP/bff/api/cases/a%2Fb" | python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])')
[ "$raw" = "/bff/api/cases/a%2Fb" ] && ok "edge → gateway: raw path unchanged (gateway sees %2F)" || bad "edge rewrites the path: $raw"
head -c 300000 /dev/zero > /tmp/body300k
head -c 2000000 /dev/zero > /tmp/body2m
[ "$(code -X POST -H 'Content-Type: application/json' --data-binary @/tmp/body300k "https://$APP/bff/api/cases")" = 413 ] \
  && ok "edge: JSON body > 256k → 413" || bad "edge: large JSON body accepted"
[ "$(code -X POST --data-binary @/tmp/body300k "https://$APP/bff/auth/login")" = 413 ] \
  && ok "edge: login body > 16k → 413" || bad "edge: large login body accepted"
up=$(c -X POST -H 'Content-Type: multipart/form-data; boundary=x' --data-binary @/tmp/body2m "https://$APP/bff/api/cases/c1/images" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("bodyLength"))' 2>/dev/null || echo none)
[ "$up" = 2000000 ] && ok "edge: upload route accepts 2 MB (limit 25m)" || bad "edge: upload route rejected 2 MB ($up)"
[ "$(code -X POST --data-binary @/tmp/body2m "https://$APP/bff/api/cases/c1/notes")" = 413 ] \
  && ok "edge: 2 MB on a non-upload route → 413" || bad "edge: non-upload route accepts 2 MB"
[ "$(curl -sk -o /dev/null -w '%{http_code}' --resolve "www.example.invalid:443:127.0.0.1" https://www.example.invalid/bff/health)" = 404 ] \
  && ok "information website: /bff → 404" || bad "information website proxies /bff"
nginx -s stop 2>/dev/null || true
kill "$stub" 2>/dev/null || true

# ── nftables ─────────────────────────────────────────────────────────────────
for ruleset in "$D"/nftables/*.nft; do
  if nft -c -f "$ruleset"; then ok "nft -c $(basename "$ruleset")"; else bad "nft -c $(basename "$ruleset")"; fi
done
for ruleset in "$D"/nftables/nc-single-server.nft "$D"/nftables/nc-core.nft "$D"/nftables/nc-edge.nft; do
  for port in 5432 6379 6380 9000 9001 8000 8300 3900 3901 3903; do
    if grep -E "dport[^;]*\b$port\b" "$ruleset" | grep -q accept; then bad "$(basename "$ruleset") opens $port"; fi
  done
done
ok "no ruleset opens PostgreSQL/Redis/object store/raw API/gateway ports"
# T5.1: a ruleset replaces only its own table; other services' tables survive.
for ruleset in "$D"/nftables/*.nft; do
  grep -qE '^[[:space:]]*flush[[:space:]]+ruleset' "$ruleset" && bad "$(basename "$ruleset") flushes the whole ruleset"
  if grep -E '^[[:space:]]*(table|delete table|flush table|add table|create table)[[:space:]]' "$ruleset" | grep -vqE '[[:space:]]inet nc(_edge)?([[:space:]]|$)'; then
    bad "$(basename "$ruleset") touches a table other than inet nc / inet nc_edge"
  fi
done
ok "rulesets without flush ruleset, only tables inet nc / inet nc_edge"
nft -f - <<'NFT' || bad "cannot load the foreign test table inet novuserver"
table inet novuserver {
    set peers { type ipv4_addr; elements = { 10.20.0.2 } }
    chain input { type filter hook input priority filter; policy accept; iifname "wg-platform" accept; }
}
NFT
foreign_before=$(nft list table inet novuserver 2>/dev/null || true)
for ruleset in "$D"/nftables/*.nft; do
  name=$(basename "$ruleset")
  t=$(awk '$1 == "table" && $2 == "inet" && $4 == "{" {print $3; exit}' "$ruleset")
  if nft -f "$ruleset" && first=$(nft -a list table inet "$t" | wc -l) && nft -f "$ruleset"; then
    [ "$(nft -a list table inet "$t" | wc -l)" -eq "$first" ] && ok "$name: reload replaces inet $t (no duplicate rules)" || bad "$name: reload duplicates rules"
  else
    bad "$name: nft -f failed next to a foreign table"
  fi
  [ "$(nft list table inet novuserver 2>/dev/null)" = "$foreign_before" ] && ok "$name: foreign table inet novuserver unchanged" || bad "$name: foreign table changed or removed"
  nft delete table inet "$t" 2>/dev/null || true
done
nft delete table inet novuserver 2>/dev/null || true
grep -qE 'tcp dport 8200 meta skuid \{ 0, "nc-gateway" \} accept' "$D/nftables/nc-edge.nft" \
  && ok "edge: only uid nc-gateway reaches core:8200" || bad "edge: core:8200 not limited to nc-gateway"
grep -qE 'tcp dport 8200 ct state new meta skuid != \{ 0, "nc-gateway" \} drop' "$D/nftables/nc-single-server.nft" \
  && ok "single: only uid nc-gateway reaches 127.0.0.1:8200" || bad "single: loopback 8200 not limited"
grep -qE 'tcp dport 8300 ct state new meta skuid != \{ 0, "www-data" \} drop' "$D/nftables/nc-single-server.nft" \
  && grep -qE 'tcp dport 8300 ct state new meta skuid != \{ 0, "www-data" \} drop' "$D/nftables/nc-edge.nft" \
  && ok "only nginx (www-data) reaches the gateway on 8300" || bad "gateway port 8300 not limited to nginx"

# ── systemd ──────────────────────────────────────────────────────────────────
mkdir -p /opt/novuconstruct/src/backend/.venv/bin /opt/novuconstruct/src/gateway/.venv/bin /opt/novuconstruct/deploy/linux/bin /etc/novuconstruct/secrets /etc/nc-gateway
cp "$D"/bin/* /opt/novuconstruct/deploy/linux/bin/ && chmod 0755 /opt/novuconstruct/deploy/linux/bin/*
for exe in uvicorn python; do printf '#!/bin/sh\n' > "/opt/novuconstruct/src/backend/.venv/bin/$exe"; chmod 0755 "/opt/novuconstruct/src/backend/.venv/bin/$exe"; done
printf '#!/bin/sh\n' > /opt/novuconstruct/src/gateway/.venv/bin/python; chmod 0755 /opt/novuconstruct/src/gateway/.venv/bin/python
[ -e /usr/local/bin/garage ] || { printf '#!/bin/sh\n' > /usr/local/bin/garage; chmod 0755 /usr/local/bin/garage; }
mkdir -p /srv/novuconstruct/garage
touch /etc/novuconstruct/core.env /etc/nc-gateway/gateway.env
units=$(mktemp -d)
cp "$D"/systemd/*.service "$D"/systemd/*.target "$units/"
chmod 0644 "$units"/*
grep -q 'After=.*nftables.service.*wg-quick@wg-nc' "$D/systemd/nginx.service.d/10-novuconstruct.conf" \
  && ok "nginx ordered after nftables and WireGuard" || bad "nginx drop-in missing ordering"
cp "$units/nc-api@.service" "$units/nc-api@gateway.service"
mkdir -p "$units/nc-api@gateway.service.d"
cp "$D/systemd/nc-api@gateway.service.d/"*.conf "$units/nc-api@gateway.service.d/"
chmod 0644 "$units/nc-api@gateway.service.d/"*
cp "$units/nc-api@.service" "$units/nc-api@desktop.service"
cp "$units/nc-api@.service" "$units/nc-api@admin.service"
chmod 0644 "$units"/*
if SYSTEMD_LOG_LEVEL=warning systemd-analyze verify --man=no "$units/nc-api@gateway.service" "$units/nc-api@desktop.service" "$units/nc-api@admin.service" "$units/nc-worker.service" "$units/nc-offer-worker.service" "$units/nc-core.target" "$units/nc-gateway.service" "$units/nc-gateway-redis.service" "$units/nc-edge.target" "$units/nc-garage.service" 2>&1 | grep -v -E "Failed to (connect|open|create).*bus|Unit.*not found|postgresql|redis-server.service|minio|wg-quick|nftables.service" | grep . ; then
  bad "systemd-analyze verify reported problems"
else ok "systemd-analyze verify (core + gateway units)"; fi
# F6.1: sandbox exposure below 3.0 ("threshold" is exposure x 10).
for unit in nc-api@desktop.service nc-worker.service nc-offer-worker.service nc-gateway.service nc-gateway-redis.service nc-garage.service; do
  if systemd-analyze security --offline=yes --threshold=30 "$units/$unit" >/tmp/sec.txt 2>&1; then
    ok "systemd-analyze security $unit: $(tail -n 1 /tmp/sec.txt | sed 's/.*exposure level for [^:]*: //')"
  else
    bad "systemd-analyze security $unit: $(tail -n 1 /tmp/sec.txt)"
  fi
done
# N2: offer worker exists but starts only after an explicit, backlog-reviewed enable.
if grep -q 'python -m app.worker.offer_runner' "$D/systemd/nc-offer-worker.service"; then ok "offer worker unit present"; else bad "offer worker unit missing (N2)"; fi
if grep -q '^Wants=.*nc-offer-worker' "$D/systemd/nc-core.target"; then bad "nc-core.target auto-starts the offer worker"; else ok "offer worker not auto-started by nc-core.target"; fi
if grep -q 'NC_CONFIRM_OFFER_BACKLOG' "$D/provision/nc-provision" && grep -q 'nc-offer-backlog' "$D/provision/nc-provision"; then ok "offer worker enabled only after backlog review"; else bad "offer worker enable lacks backlog review"; fi
grep -q '^Environment=NC_ZONE=%i' "$D/systemd/nc-api@.service" && ok "zone fixed per instance (NC_ZONE=%i)" || bad "NC_ZONE not fixed by the unit"
grep -q -- '--no-proxy-headers' "$D/systemd/nc-api@.service" && ok "uvicorn --no-proxy-headers" || bad "proxy headers not disabled"
grep -q -- '--uds ' "$D/systemd/nc-api@.service" && ok "API on unix socket only" || bad "API not on a unix socket"
# F3.4: only the gateway instance loads the gateway HMAC keys.
grep -q 'NC_GATEWAY_HMAC_KEYS' "$D/systemd/nc-api@.service" && bad "gateway HMAC key loaded by every zone"   || ok "gateway HMAC key not in the shared unit"
grep -q '^LoadCredential=NC_GATEWAY_HMAC_KEYS:' "$D/systemd/nc-api@gateway.service.d/10-gateway-hmac.conf"   && ok "gateway HMAC key loaded by nc-api@gateway only" || bad "gateway drop-in missing"
grep -q 'X-NC-Client-IP     ""' "$D/nginx/snippets/nc-proxy.conf"   && ok "desktop/admin proxies clear X-NC-* headers" || bad "nc-proxy.conf forwards X-NC-* headers"
grep -q 'X-Forwarded-For   ""' "$D/nginx/snippets/nc-proxy-gateway.conf"   && ok "gateway proxy sends no X-Forwarded-For" || bad "gateway proxy forwards X-Forwarded-For"

# ── Web Gateway unit: own identity, no access to core secrets/DB/sockets ─────
GU="$D/systemd/nc-gateway.service"
grep -qx 'User=nc-gateway' "$GU" && grep -qx 'Group=nc-gateway' "$GU" && ok "nc-gateway runs as nc-gateway:nc-gateway" || bad "nc-gateway user/group"
if grep -E '^(Group|SupplementaryGroups)=' "$GU" | grep -qwE 'novuconstruct|nc-api-sock|root'; then bad "nc-gateway is in a core group"; else ok "nc-gateway has no core group"; fi
if grep -E '^(LoadCredential|EnvironmentFile|ReadWritePaths|ReadOnlyPaths|BindPaths|BindReadOnlyPaths|WorkingDirectory)=' "$GU" | grep -q '/etc/novuconstruct'; then
  bad "nc-gateway references /etc/novuconstruct (core secrets)"
else ok "nc-gateway loads nothing from /etc/novuconstruct"; fi
for p in /etc/novuconstruct /run/novuconstruct /var/lib/novuconstruct /var/lib/postgresql /var/run/postgresql /etc/redis /var/lib/redis; do
  grep -E '^InaccessiblePaths=' "$GU" | grep -q -- "-$p\( \|$\)" || bad "nc-gateway: $p not masked (InaccessiblePaths)"
done
ok "nc-gateway: core secrets, DB, core Redis and API sockets masked"
grep -q '^LoadCredential=NC_GATEWAY_HMAC_KEY:/etc/nc-gateway/secrets/NC_GATEWAY_HMAC_KEY$' "$GU" \
  && grep -q '^LoadCredential=NC_BFF_SESSION_KEYS:/etc/nc-gateway/secrets/NC_BFF_SESSION_KEYS$' "$GU" \
  && ok "nc-gateway: HMAC and session keys via LoadCredential" || bad "nc-gateway credentials"
grep -qx 'IPAddressDeny=any' "$GU" && grep -qx 'IPAddressAllow=127.0.0.1 10.50.0.1' "$GU" && ok "nc-gateway: IPAddressDeny=any, allow loopback + core WG only" || bad "nc-gateway IP allow list"
grep -qx 'RestrictAddressFamilies=AF_UNIX AF_INET' "$GU" && ok "nc-gateway: AF_UNIX AF_INET only" || bad "nc-gateway address families"
grep -q 'python -m nc_gateway' "$GU" && grep -q '/opt/novuconstruct/src/gateway/.venv/bin/python' "$GU" && ok "nc-gateway: python -m nc_gateway from src/gateway/.venv" || bad "nc-gateway ExecStart"
grep -qx 'PartOf=nc-edge.target' "$GU" && grep -qx 'WantedBy=nc-edge.target' "$GU" && ok "nc-gateway belongs to nc-edge.target" || bad "nc-gateway target"
grep -q 'nc-gateway' "$D/systemd/nc-core.target" && bad "nc-core.target references the gateway (edge ≠ core)" || ok "nc-core.target does not start the gateway"
grep -q '^Wants=' "$D/systemd/nc-edge.target" && bad "nc-edge.target auto-starts units (Wants=)" || ok "nc-edge.target has no Wants= (explicit enable only)"
grep -qx 'PrivateNetwork=yes' "$D/systemd/nc-gateway-redis.service" && grep -qx 'RestrictAddressFamilies=AF_UNIX' "$D/systemd/nc-gateway-redis.service" \
  && ok "gateway Redis: no network at all" || bad "gateway Redis network isolation"
# nc-provision: install prepares, only `gateway` (with NC_CONFIRM_GATEWAY=1) enables/starts.
body() { awk -v f="$1() {" 'index($0, f) == 1 {on = 1} on {print} on && /^}/ {exit}' "$D/provision/nc-provision"; }
if body cmd_install | grep -q 'nc-gateway\|nc-edge' || body install_units | grep -q 'systemctl enable\|--now' || body install_gateway_app | grep -q 'systemctl'; then
  bad "nc-provision install enables/starts the gateway"
else ok "nc-provision install never enables/starts the gateway"; fi
confirm_line=$(body cmd_gateway | grep -n 'NC_CONFIRM_GATEWAY:-0' | head -n 1 | cut -d: -f1)
enable_line=$(body cmd_gateway | grep -n 'systemctl enable' | head -n 1 | cut -d: -f1)
if [ -n "$confirm_line" ] && [ -n "$enable_line" ] && [ "$confirm_line" -lt "$enable_line" ]; then
  ok "nc-provision gateway: NC_CONFIRM_GATEWAY=1 required before enabling"
else bad "nc-provision gateway enables without NC_CONFIRM_GATEWAY"; fi
# gateway.env template: contract variables present, no secret values.
GE="$D/env/gateway.env.example"
for v in NC_ENV NC_BFF_PUBLIC_ORIGIN NC_BFF_CORE_URL NC_BFF_TRUSTED_PROXY NC_BFF_IDLE_TIMEOUT_SECONDS NC_BFF_ABSOLUTE_TIMEOUT_SECONDS NC_BFF_ALLOWLIST_PATH; do
  grep -q "^$v=" "$GE" || bad "gateway.env.example: $v missing"
done
grep -qE '^(NC_GATEWAY_HMAC_KEYS?|NC_BFF_SESSION_KEYS|NC_BFF_REDIS_URL|NC_BFF_DEV_INSECURE_COOKIE)=' "$GE" \
  && bad "gateway.env.example assigns a secret / dev-only variable" || ok "gateway.env.example: contract variables, no secrets"
grep -qE '^NC_BFF_PUBLIC_ORIGIN=https://' "$GE" && grep -qx 'NC_BFF_TRUSTED_PROXY=127.0.0.1' "$GE" && grep -qx 'NC_ENV=production' "$GE" \
  && ok "gateway.env.example: https origin, nginx as the only trusted proxy, production" || bad "gateway.env.example values"

# ── nc-gen-secrets: core and gateway secrets never visible to each other ─────
G=/opt/novuconstruct/deploy/linux/bin/nc-gen-secrets
sh "$G" >/dev/null
sh "$G" --gateway >/dev/null
perm() { stat -c '%a %U:%G' "$1"; }
[ "$(perm /etc/nc-gateway/secrets)" = "700 root:root" ] && ok "gateway secrets dir 0700 root:root" || bad "gateway secrets dir $(perm /etc/nc-gateway/secrets)"
badperm=$(find /etc/nc-gateway/secrets /etc/nc-gateway-redis -type f ! -perm 0600 -o -type f ! -user root | head -n 3)
[ -z "$badperm" ] && ok "gateway secret files 0600 root" || bad "gateway secret files: $badperm"
for f in NC_GATEWAY_HMAC_KEY NC_BFF_SESSION_KEYS NC_BFF_REDIS_URL REDIS_GATEWAY_PASSWORD; do
  [ -s "/etc/nc-gateway/secrets/$f" ] || bad "nc-gen-secrets --gateway did not write $f"
done
if runuser -u nc-gateway -- cat /etc/novuconstruct/secrets/JWT_SECRET >/dev/null 2>&1 || runuser -u nc-gateway -- cat /etc/novuconstruct/secrets/NC_GATEWAY_HMAC_KEYS >/dev/null 2>&1; then
  bad "nc-gateway can read core secrets"
else ok "nc-gateway cannot read core secrets"; fi
if runuser -u novuconstruct -- cat /etc/nc-gateway/secrets/NC_BFF_SESSION_KEYS >/dev/null 2>&1 || runuser -u novuconstruct -- cat /etc/nc-gateway-redis/users.acl >/dev/null 2>&1; then
  bad "core user can read gateway secrets"
else ok "core user cannot read gateway session keys / Redis ACL"; fi
runuser -u nc-gateway -- cat /etc/nc-gateway/secrets/NC_BFF_SESSION_KEYS >/dev/null 2>&1 && bad "nc-gateway reads its secrets outside LoadCredential" || ok "gateway secrets readable only by PID 1 (LoadCredential)"
python3 - /etc/nc-gateway/secrets/NC_BFF_SESSION_KEYS <<'PY' && ok "NC_BFF_SESSION_KEYS = kid:base64(32 B)" || bad "NC_BFF_SESSION_KEYS format"
import base64, re, sys
v = open(sys.argv[1]).read()
for e in v.split(","):
    kid, key = e.split(":", 1)
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,32}", kid), kid
    assert len(base64.b64decode(key, validate=True)) == 32
PY
hmac=$(cat /etc/nc-gateway/secrets/NC_GATEWAY_HMAC_KEY)
tr ',' '\n' < /etc/novuconstruct/secrets/NC_GATEWAY_HMAC_KEYS | grep -qxF "$hmac" && ok "NC_GATEWAY_HMAC_KEY = an entry of core NC_GATEWAY_HMAC_KEYS" || bad "gateway HMAC key not in core keys"
grep -qE '^unix://nc-gateway:[0-9a-f]{64}@/run/nc-gateway-redis/redis\.sock\?db=0$' /etc/nc-gateway/secrets/NC_BFF_REDIS_URL && ok "NC_BFF_REDIS_URL → own Redis socket, ACL user nc-gateway" || bad "NC_BFF_REDIS_URL format"
# Rotation paths used by GATEWAY_RUNBOOK.md.
old_first=$(cut -d, -f1 /etc/nc-gateway/secrets/NC_BFF_SESSION_KEYS)
sh "$G" --gateway --rotate-session-key >/dev/null
[ "$(awk -F, '{print NF}' /etc/nc-gateway/secrets/NC_BFF_SESSION_KEYS)" -eq 2 ] && [ "$(cut -d, -f2 /etc/nc-gateway/secrets/NC_BFF_SESSION_KEYS)" = "$old_first" ] \
  && ok "--rotate-session-key: new key first, previous kept for decryption" || bad "--rotate-session-key"
sh "$G" --gateway --revoke-session-keys >/dev/null
[ "$(awk -F, '{print NF}' /etc/nc-gateway/secrets/NC_BFF_SESSION_KEYS)" -eq 1 ] && ! grep -qF "$old_first" /etc/nc-gateway/secrets/NC_BFF_SESSION_KEYS \
  && ok "--revoke-session-keys: one fresh key, old keys gone (logout all)" || bad "--revoke-session-keys"
sh "$G" --add-gateway-hmac >/dev/null
newest=$(sh "$G" --export-gateway-hmac)
[ "$(awk -F, '{print NF}' /etc/novuconstruct/secrets/NC_GATEWAY_HMAC_KEYS)" -eq 2 ] && [ "$newest" != "$hmac" ] && ok "--add-gateway-hmac appends a second core key" || bad "--add-gateway-hmac"
printf '%s\n' "$newest" | sh "$G" --gateway --hmac-stdin >/dev/null
[ "$(cat /etc/nc-gateway/secrets/NC_GATEWAY_HMAC_KEY)" = "$newest" ] && ok "--hmac-stdin installs the new key for the gateway" || bad "--hmac-stdin"
printf 'kid:short\n' | sh "$G" --gateway --hmac-stdin >/dev/null 2>&1 && bad "--hmac-stdin accepted a short secret" || ok "--hmac-stdin rejects a short secret"
sh "$G" --drop-gateway-hmac "${hmac%%:*}" >/dev/null
[ "$(cat /etc/novuconstruct/secrets/NC_GATEWAY_HMAC_KEYS)" = "$newest" ] && ok "--drop-gateway-hmac removes the old core key" || bad "--drop-gateway-hmac"
sh "$G" --drop-gateway-hmac "${newest%%:*}" >/dev/null 2>&1 && bad "--drop-gateway-hmac removed the last key" || ok "--drop-gateway-hmac keeps the last key"

# ── gateway Redis: no TCP, ACL limited to nc:bff:* ───────────────────────────
# (/var/lib/nc-gateway-redis is the unit's StateDirectory; systemd creates it on a host.)
mkdir -p /etc/nc-gateway-redis /run/nc-gateway-redis /var/lib/nc-gateway-redis /tmp/ncgr
cp "$D/redis/nc-gateway-redis.conf" /etc/nc-gateway-redis/redis.conf
redis-server /etc/nc-gateway-redis/redis.conf --aclfile /etc/nc-gateway-redis/users.acl \
  --supervised no --daemonize yes --dir /tmp/ncgr --logfile /tmp/ncgr/redis.log >/tmp/ncgr/start.log 2>&1 \
  || bad "gateway Redis config rejected: $(tail -n 3 /tmp/ncgr/start.log)"
sleep 1
S=/run/nc-gateway-redis/redis.sock
REDISCLI_AUTH=$(cat /etc/nc-gateway/secrets/REDIS_GATEWAY_PASSWORD); export REDISCLI_AUTH
rc() { redis-cli --no-auth-warning -s "$S" --user nc-gateway "$@" 2>&1; }
if [ -S "$S" ]; then
  env -u REDISCLI_AUTH redis-cli -s "$S" ping 2>&1 | grep -qE 'NOAUTH|NOPERM|WRONGPASS' && ok "gateway Redis: default user disabled" || bad "gateway Redis: default user works"
  [ "$(rc set nc:bff:sess:validate x EX 5)" = OK ] && ok "gateway Redis: nc-gateway writes nc:bff:*" || bad "gateway Redis: nc-gateway cannot write nc:bff:*"
  rc set nc:core:x 1 | grep -q NOPERM && ok "gateway Redis: keys outside nc:bff:* denied" || bad "gateway Redis: foreign keys allowed"
  set -f   # "keys *" must reach Redis, not the shell's glob
  for cmd in flushall "keys *" "config get *" "debug sleep 0" "acl list" "shutdown"; do
    # DEBUG is refused by enable-debug-command before the ACL check; both are a denial.
    # shellcheck disable=SC2086
    rc $cmd | grep -qE 'NOPERM|command not allowed' || bad "gateway Redis: '$cmd' allowed"
  done
  set +f
  ok "gateway Redis: FLUSHALL, KEYS, CONFIG, DEBUG, ACL denied"
  rc subscribe nc:bff:x | grep -q NOPERM && ok "gateway Redis: pub/sub denied" || bad "gateway Redis: pub/sub allowed"
  ss -Hltnp 2>/dev/null | grep -q redis-server && bad "gateway Redis listens on TCP" || ok "gateway Redis: no TCP listener (port 0)"
else
  bad "gateway Redis did not start: $(tail -n 3 /tmp/ncgr/redis.log 2>/dev/null)"
fi
pidof redis-server | xargs -r kill 2>/dev/null || true
unset REDISCLI_AUTH

# ── object store (S-1, Garage): loopback only, secrets via LoadCredential ────
GT="$D/garage/garage.toml"
binds=$(grep -E '^\s*(rpc_bind_addr|rpc_public_addr|api_bind_addr)\s*=' "$GT")
[ "$(printf '%s\n' "$binds" | grep -c .)" -eq 4 ] && ! printf '%s\n' "$binds" | grep -qv '"127\.0\.0\.1:' \
  && ok "garage.toml: S3, RPC and admin on 127.0.0.1 only" || bad "garage.toml binds beyond loopback: $binds"
grep -qE '^\s*(rpc_secret|admin_token|metrics_token)\s*=' "$GT" && bad "garage.toml holds a secret" || ok "garage.toml holds no secret"
grep -qx 'replication_factor = 1' "$GT" && grep -qx 'metadata_fsync = true' "$GT" && grep -q '^metadata_auto_snapshot_interval' "$GT" \
  && ok "garage.toml: single node with fsync + metadata snapshots" || bad "garage.toml durability settings"
GA="$D/systemd/nc-garage.service"
grep -qx 'User=nc-garage' "$GA" && grep -qx 'IPAddressDeny=any' "$GA" && grep -qx 'IPAddressAllow=localhost' "$GA" \
  && ok "nc-garage: own user, loopback only" || bad "nc-garage user / IP allow list"
grep -q '^LoadCredential=GARAGE_RPC_SECRET:/etc/nc-garage/secrets/GARAGE_RPC_SECRET$' "$GA" && grep -q '^Environment=GARAGE_RPC_SECRET_FILE=%d/GARAGE_RPC_SECRET$' "$GA" \
  && ok "nc-garage: RPC secret via LoadCredential" || bad "nc-garage RPC secret"
grep -E '^(LoadCredential|EnvironmentFile|ReadWritePaths)=' "$GA" | grep -q '/etc/novuconstruct' && bad "nc-garage reads core secrets" || ok "nc-garage loads nothing from /etc/novuconstruct"
sh "$G" --garage >/dev/null
[ "$(perm /etc/nc-garage/secrets)" = "700 root:root" ] && ok "Garage secrets dir 0700 root:root" || bad "Garage secrets dir $(perm /etc/nc-garage/secrets)"
for f in GARAGE_RPC_SECRET GARAGE_ADMIN_TOKEN; do
  grep -qxE '[0-9a-f]{64}' "/etc/nc-garage/secrets/$f" || bad "$f is not 32 B hex"
  [ "$(perm "/etc/nc-garage/secrets/$f")" = "600 root:root" ] || bad "$f $(perm "/etc/nc-garage/secrets/$f")"
done
ok "Garage secrets: 32 B hex, 0600 root:root"
for u in nc-garage novuconstruct nc-gateway; do
  runuser -u "$u" -- cat /etc/nc-garage/secrets/GARAGE_RPC_SECRET >/dev/null 2>&1 && bad "$u reads the Garage RPC secret"
done
ok "Garage RPC secret readable only by root / PID 1"
body cmd_start | grep -q 'NC_OBJECT_STORAGE_READY' && bad "nc-provision start still needs NC_OBJECT_STORAGE_READY" || ok "nc-provision start without manual NC_OBJECT_STORAGE_READY"
body cmd_install | grep -q '^  install_object_storage$' && ok "nc-provision install installs the object store" || bad "nc-provision install skips the object store"
body install_garage_binary | grep -q 'NC_GARAGE_SHA256' && ok "Garage binary verified against NC_GARAGE_SHA256" || bad "Garage binary not verified"
# T5.1: nc-provision firewall backs up, rolls back and persists only its own table.
fw=$(body cmd_firewall)
printf '%s\n' "$fw" | grep -qE 'nft list ruleset|nft flush ruleset|\\nflush ruleset' && bad "nc-provision firewall backs up / flushes the whole ruleset" || ok "nc-provision firewall: backup and rollback only of its own table"
printf '%s\n' "$fw" | grep -qE 'install .*"\$ruleset" /etc/nftables\.conf' && bad "nc-provision firewall overwrites /etc/nftables.conf" || ok "nc-provision firewall: /etc/nftables.conf only gets an include"

# ── shell helpers ────────────────────────────────────────────────────────────
if bash -n "$D/provision/nc-provision"; then ok "bash -n nc-provision"; else bad "bash -n nc-provision"; fi
for script in "$D"/bin/* "$D"/tests/*.sh; do
  if sh -n "$script"; then ok "sh -n $(basename "$script")"; else bad "sh -n $(basename "$script")"; fi
done
if shellcheck -S warning -f gcc "$D/provision/nc-provision"; then ok "shellcheck nc-provision"; else bad "shellcheck nc-provision"; fi
# shellcheck disable=SC2046
if shellcheck -S warning -s sh -f gcc $(ls "$D"/bin/* "$D"/tests/*.sh); then ok "shellcheck bin/* tests/*.sh"; else bad "shellcheck bin/* tests/*.sh"; fi

# ── templates carry placeholders only ────────────────────────────────────────
if grep -rEn '(PrivateKey|PresharedKey)\s*=\s*[A-Za-z0-9+/]{43}=' "$D/wireguard"; then
  bad "WireGuard template contains a real-looking key"
else ok "WireGuard templates hold placeholders only"; fi
if grep -rEn '[0-9a-f]{64}|[A-Za-z0-9+/]{43}=' "$D/env" "$D/redis" "$D/systemd" "$D/nginx"; then
  bad "a template contains a real-looking secret"
else ok "env/redis/systemd/nginx templates hold no secrets"; fi

[ "$fail" -eq 0 ] && echo "ALL CHECKS PASSED" || { echo "VALIDATION FAILED"; exit 1; }
