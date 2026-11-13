#!/bin/sh
# Copyright (c) 2026 Novusion
# Website: https://novusion.com
# Contact: info@novusion.com
#
# Author: Pavel Dostál
# Project: NovuConstruct
# Module: deploy/linux/tests
# Description: Behaviour test of bin/nc-backup (F9.1) and bin/nc-wg-metrics (F9.3) against
#              stubs of restic, runuser, pg_dump, pg_restore and wg – nothing leaves the host.
# Created: 2026-11-13
#
#   sh deploy/linux/tests/backup_monitoring_test.sh   (part of tests/validate-configs.sh)
#
# Work directory: $NC_BACKUP_TEST_DIR, else a fresh mktemp -d (CI container).
set -eu
D=$(cd "$(dirname "$0")/.." && pwd)
BACKUP="$D/bin/nc-backup"
WGM="$D/bin/nc-wg-metrics"
W=${NC_BACKUP_TEST_DIR:-$(mktemp -d)}
mkdir -p "$W"
W=$(cd "$W" && pwd)
fails=0
ok()  { echo "OK   backup: $*"; }
bad() { echo "FAIL backup: $*"; fails=$((fails + 1)); }

# ── stubs ────────────────────────────────────────────────────────────────────
STUBS="$W/stubs"
rm -rf "${STUBS:?}" "${W:?}/etc" "${W:?}/data" "${W:?}/state" "${W:?}/metrics" "${W:?}/uploaded" "${W:?}/sys"
mkdir -p "$STUBS" "$W/etc/secrets" "$W/etc/wireguard" "$W/data/garage/data" "$W/uploaded"
stub() { cat > "$STUBS/$1"; chmod +x "$STUBS/$1"; }

stub runuser <<'EOF'
#!/bin/sh
while [ "$1" != -- ]; do shift; done; shift
exec "$@"
EOF
stub pg_dump <<'EOF'
#!/bin/sh
[ "${STUB_PG_DUMP_FAIL:-0}" = 1 ] && exit 1
printf 'PGDMP-stub'
EOF
stub pg_restore <<'EOF'
#!/bin/sh
exit 0
EOF
stub restic <<'EOF'
#!/bin/sh
echo "restic $*" >> "$STUB_LOG"
for a in "$@"; do
  case "$a" in */wireguard) [ -d "$a" ] && cp "$a"/* "$STUB_UPLOADED"/ 2>/dev/null || true ;; esac
done
for a in "$@"; do
  case "$a" in
    backup) [ "${STUB_RESTIC_FAIL:-}" = backup ] && exit 1; exit 0 ;;
    snapshots) echo '[{"id":"0123abcd","tags":["stub"]}]'; exit 0 ;;
    forget|init) exit 0 ;;
  esac
done
exit 0
EOF
stub wg <<'EOF'
#!/bin/sh
case "$2" in
  wg-nc|wg-down) printf 'PEERKEYA+/=\t1763000000\nPEERKEYB=\t0\n' ;;
  wg-empty) ;;
  *) exit 1 ;;
esac
EOF

printf 'pw\n' > "$W/etc/secrets/RESTIC_PASSWORD"
printf 'key\n' > "$W/etc/secrets/BACKUP_SSH_KEY"
printf '[storage.example.invalid]:23 ssh-ed25519 AAAAstub\n' > "$W/etc/known_hosts"
printf 'NC_X=1\n' > "$W/etc/core.env"
cat > "$W/etc/wireguard/wg-nc.conf" <<'EOF'
[Interface]
Address    = 10.50.0.1/16
PrivateKey = SECRETPRIVATEKEYSECRETPRIVATEKEYSECRETPRIV=
[Peer]
PublicKey    = PEERKEYA+/=
PresharedKey = SECRETPSKSECRETPSKSECRETPSKSECRETPSKSECRET=
EOF

export STUB_LOG="$W/restic.log" STUB_UPLOADED="$W/uploaded"
run_backup() {  # run_backup REPO KNOWN_HOSTS → exit code in $rc
  rc=0
  env PATH="$STUBS:$PATH" NC_BACKUP_ENV=/nonexistent \
    RESTIC_REPOSITORY="$1" RESTIC_PASSWORD_FILE="$W/etc/secrets/RESTIC_PASSWORD" \
    NC_BACKUP_SSH_KEY="$W/etc/secrets/BACKUP_SSH_KEY" NC_BACKUP_KNOWN_HOSTS="$2" \
    NC_BACKUP_STATE="$W/state" NC_BACKUP_METRICS_DIR="$W/metrics" NC_DATA_ROOT="$W/data" \
    NC_BACKUP_CONFIG_PATHS="$W/etc" NC_BACKUP_SECRETS_DIR="$W/etc/secrets" NC_WG_DIR="$W/etc/wireguard" \
    sh "$BACKUP" > "$W/out.txt" 2>&1 || rc=$?
}
metric() { awk -v m="$1" '$1 == m { print $2 }' "$W/metrics/nc_backup.prom" 2>/dev/null; }
REPO=sftp://u1@storage.example.invalid:23/./nc

# 1. a repository on this server is refused (off-host only)
: > "$STUB_LOG"
run_backup /var/backups/restic "$W/etc/known_hosts"
if [ "$rc" -eq 2 ] && [ ! -s "$STUB_LOG" ]; then ok "local repository refused"; else bad "local repository accepted (rc=$rc)"; fi

# 2. no pinned host key → refused
run_backup "$REPO" "$W/etc/missing_known_hosts"
if [ "$rc" -eq 2 ] && [ ! -s "$STUB_LOG" ]; then ok "missing pinned host key refused"; else bad "missing host key accepted (rc=$rc)"; fi

# 3. successful run
: > "$STUB_LOG"
run_backup "$REPO" "$W/etc/known_hosts"
if [ "$rc" -eq 0 ]; then ok "backup run exit 0"; else bad "backup run rc=$rc: $(cat "$W/out.txt")"; fi
[ "$(metric nc_backup_last_run_success)" = 1 ] && ok "metric success 1" || bad "metric success not 1"
first_ok=$(metric nc_backup_last_success_timestamp_seconds)
[ "${first_ok:-0}" -gt 0 ] && ok "last success timestamp set" || bad "last success timestamp missing"
for t in nc-db nc-storage nc-config; do
  grep -q "backup .*--tag $t" "$STUB_LOG" && ok "restic backup --tag $t" || bad "no restic backup --tag $t"
done
grep -q "StrictHostKeyChecking=yes" "$STUB_LOG" && grep -q "UserKnownHostsFile=$W/etc/known_hosts" "$STUB_LOG" \
  && ok "SFTP pinned host key" || bad "SFTP host key not pinned"
grep -q -- "--exclude $W/etc/secrets" "$STUB_LOG" && ok "secrets excluded" || bad "secrets not excluded"
grep -q "forget .*--keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune" "$STUB_LOG" \
  && ok "retention 7/4/6" || bad "retention missing"
if [ -f "$W/uploaded/wg-nc.conf" ] && ! grep -q SECRET "$W/uploaded/wg-nc.conf" \
  && grep -q 'PublicKey    = PEERKEYA' "$W/uploaded/wg-nc.conf"; then
  ok "WireGuard config uploaded without private keys"
else bad "WireGuard private key leaked or config missing"; fi
[ ! -d "$W/state/staging" ] && [ ! -d "$W/state/lock" ] && ok "staging and lock removed" || bad "staging or lock left behind"

# 4. failed pg_dump → exit 1, success 0, previous success timestamp kept
STUB_PG_DUMP_FAIL=1; export STUB_PG_DUMP_FAIL
run_backup "$REPO" "$W/etc/known_hosts"
unset STUB_PG_DUMP_FAIL
[ "$rc" -eq 1 ] && ok "pg_dump failure exit 1" || bad "pg_dump failure rc=$rc"
[ "$(metric nc_backup_last_run_success)" = 0 ] && ok "metric success 0 after failure" || bad "failure not visible in metrics"
[ "$(metric nc_backup_last_success_timestamp_seconds)" = "$first_ok" ] \
  && ok "last success timestamp kept" || bad "last success timestamp overwritten"

# 5. failed upload → exit 1, success 0
STUB_RESTIC_FAIL=backup; export STUB_RESTIC_FAIL
run_backup "$REPO" "$W/etc/known_hosts"
unset STUB_RESTIC_FAIL
[ "$rc" -eq 1 ] && [ "$(metric nc_backup_last_run_success)" = 0 ] && ok "restic failure reported" || bad "restic failure rc=$rc"

# 6. nc-wg-metrics (F9.3): wg-nc up with two peers, wg-nc-admin missing, wg-down present
#    but administratively down, wg-empty up without peers; required peer marked
mkdir -p "$W/sys/wg-nc" "$W/sys/wg-down" "$W/sys/wg-empty"
echo 0x1091 > "$W/sys/wg-nc/flags"     # IFF_UP set
echo 0x1090 > "$W/sys/wg-down/flags"   # IFF_UP cleared (ip link set down)
echo 0x1091 > "$W/sys/wg-empty/flags"
run_wgm() {  # run_wgm VAR=VALUE… → exit code in $rc
  rc=0
  env PATH="$STUBS:$PATH" NC_BACKUP_METRICS_DIR="$W/metrics" NC_WG_SYSFS="$W/sys" \
    NC_WG_INTERFACES="wg-nc wg-nc-admin wg-down wg-empty" "$@" sh "$WGM" > "$W/out.txt" 2>&1 || rc=$?
}
P="$W/metrics/nc_wg.prom"
has() { grep -qx "$1" "$P"; }
run_wgm NC_WG_REQUIRED_PEERS="wg-nc:PEERKEYB=" NC_WG_HANDSHAKE_MAX_AGE_OVERRIDES="wg-empty:0 wg-nc-admin:86400"
[ "$rc" -eq 0 ] && ok "nc-wg-metrics exit 0" || bad "nc-wg-metrics rc=$rc: $(cat "$W/out.txt")"
has 'nc_wg_interface_up{interface="wg-nc"} 1' && ok "wg-nc up" || bad "wg-nc up missing"
has 'nc_wg_interface_up{interface="wg-nc-admin"} 0' && ok "missing wg-nc-admin reported down" || bad "missing wg-nc-admin not reported"
has 'nc_wg_interface_up{interface="wg-down"} 0' && ok "link-down interface reported down" || bad "link-down interface reported up"
has 'nc_wg_interface_up{interface="wg-empty"} 1' && ok "wg-empty up" || bad "wg-empty up missing"
has 'nc_wg_peer_latest_handshake_timestamp_seconds{interface="wg-nc",peer="PEERKEYA+/="} 1763000000' \
  && ok "peer handshake" || bad "peer handshake missing"
has 'nc_wg_interface_latest_handshake_timestamp_seconds{interface="wg-nc"} 1763000000' \
  && ok "interface newest handshake" || bad "interface newest handshake missing"
has 'nc_wg_interface_peers{interface="wg-nc"} 2' && ok "peer count" || bad "peer count missing"
has 'nc_wg_interface_latest_handshake_timestamp_seconds{interface="wg-empty"} 0' && has 'nc_wg_interface_peers{interface="wg-empty"} 0' \
  && ok "interface without peers: handshake 0" || bad "interface without peers not reported"
if grep -q 'nc_wg_interface_latest_handshake_timestamp_seconds{interface="wg-nc-admin"}' "$P"; then
  bad "handshake reported for a missing interface"
else ok "no handshake series for a missing interface"; fi
has 'nc_wg_handshake_max_age_seconds{interface="wg-nc"} 900' && ok "default handshake limit 900 s" || bad "default handshake limit missing"
has 'nc_wg_handshake_max_age_seconds{interface="wg-nc-admin"} 86400' && has 'nc_wg_handshake_max_age_seconds{interface="wg-empty"} 0' \
  && ok "per-interface handshake limits" || bad "per-interface handshake limits ignored"
has 'nc_wg_peer_required{interface="wg-nc",peer="PEERKEYB="} 1' && ok "required peer" || bad "required peer missing"

# 7. an invalid limit is refused and the previous metrics stay in place
cp "$P" "$W/prev.prom"
run_wgm NC_WG_HANDSHAKE_MAX_AGE=15m
if [ "$rc" -eq 2 ] && cmp -s "$P" "$W/prev.prom"; then ok "invalid handshake limit refused"; else bad "invalid handshake limit rc=$rc"; fi
run_wgm NC_WG_HANDSHAKE_MAX_AGE_OVERRIDES="wg-nc:-1"
if [ "$rc" -eq 2 ] && cmp -s "$P" "$W/prev.prom"; then ok "invalid override refused"; else bad "invalid override rc=$rc"; fi

[ "$fails" -eq 0 ] && echo "backup_monitoring_test: ALL PASSED" || { echo "backup_monitoring_test: $fails FAILED"; exit 1; }
