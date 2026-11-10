#!/bin/sh
# Copyright (c) 2026 Novusion
# Website: https://novusion.com
# Contact: info@novusion.com
#
# Author: Pavel Dostál
# Project: NovuConstruct
# Module: deploy/linux/tests
# Description: Behaviour test of deploy.sh (F6.6, T8.1 rollback policy) against stubs of
#              systemctl, pg_dump, curl, redis-cli and nc-migrate – no real service is touched.
# Created: 2026-11-10
#
#   sh deploy/linux/tests/deploy_test.sh        (part of tests/validate-configs.sh)
#
# Work directory: $NC_DEPLOY_TEST_DIR, else a fresh mktemp -d (CI container).
set -eu
D=$(cd "$(dirname "$0")/.." && pwd)
DEPLOY="$D/deploy.sh"
W=${NC_DEPLOY_TEST_DIR:-$(mktemp -d)}
mkdir -p "$W"
W=$(cd "$W" && pwd)
fails=0
ok()  { echo "OK   deploy: $*"; }
bad() { echo "FAIL deploy: $*"; fails=$((fails + 1)); }

[ -f "$DEPLOY" ] || { echo "FAIL deploy: $DEPLOY missing"; exit 1; }

# ── stubs ────────────────────────────────────────────────────────────────────
STUBS="$W/stubs"
rm -rf "$STUBS"; mkdir -p "$STUBS"
stub() { cat > "$STUBS/$1"; chmod +x "$STUBS/$1"; }

stub id <<'EOF'
#!/bin/sh
[ "${1:-}" = -u ] && { echo 0; exit 0; }
exec /usr/bin/id "$@"
EOF
stub hostname <<'EOF'
#!/bin/sh
echo "test host"
EOF
stub runuser <<'EOF'
#!/bin/sh
while [ "$#" -gt 0 ] && [ "$1" != -- ]; do shift; done
shift
exec "$@"
EOF
stub pg_dump <<'EOF'
#!/bin/sh
echo "backup" >> "$SIM/calls"
[ "$(cat "$SIM/backup_mode")" = ok ] || exit 1
echo "PGDMP fake archive"
EOF
stub pg_restore <<'EOF'
#!/bin/sh
[ "$1" = --list ] && head -c 5 "$2" | grep -q PGDMP
EOF
stub python3 <<'EOF'
#!/bin/sh
[ "$1" = -m ] && [ "$2" = venv ] || exit 1
mkdir -p "$3/bin"
printf '#!/bin/sh\nexit 0\n' > "$3/bin/pip"; chmod +x "$3/bin/pip"
EOF
# systemctl: $SIM/active lists running units; nc-worker gets a new MainPID on every start.
stub systemctl <<'EOF'
#!/bin/sh
cmd=$1; shift
case "$cmd" in
  is-active) [ "$1" = --quiet ] && shift; grep -qxF "$1" "$SIM/active" ;;
  stop)
    echo "stop $*" >> "$SIM/calls"
    for u in "$@"; do grep -vxF "$u" "$SIM/active" > "$SIM/active.n" || true; mv "$SIM/active.n" "$SIM/active"; done
    for u in "$@"; do [ "$u" = nc-worker.service ] && echo 0 > "$SIM/worker_pid"; done; exit 0 ;;
  start)
    echo "start $* release=$(basename "$(readlink "$NC_APP_LINK")")" >> "$SIM/calls"
    for u in "$@"; do
      echo "$u" >> "$SIM/active"
      if [ "$u" = nc-worker.service ]; then
        n=$(( $(cat "$SIM/pid_seq") + 1 )); echo "$n" > "$SIM/pid_seq"; echo "$n" > "$SIM/worker_pid"
      fi
    done ;;
  show) cat "$SIM/worker_pid" ;;
  *) exit 1 ;;
esac
EOF
# curl: health/ready fail while the release named in $SIM/bad_health is active.
stub curl <<'EOF'
#!/bin/sh
url=""; for a in "$@"; do url=$a; done
rel=$(basename "$(readlink "$NC_APP_LINK")")
[ "$rel" = "$(cat "$SIM/bad_health")" ] && exit 22
case "$url" in
  */ready) echo '{"status":"ok","service":"x","ready":true}' ;;
  */health) echo '{"status":"ok"}' ;;
  *) exit 22 ;;
esac
EOF
# redis-cli: while the release in $SIM/bad_heartbeat is active only the heartbeat of the
# PREVIOUS worker process is fresh (a leftover key); otherwise the current one is.
stub redis-cli <<'EOF'
#!/bin/sh
key=""; for a in "$@"; do key=$a; done
[ "${REDISCLI_AUTH:-}" = s3cret ] || exit 1
pid=$(cat "$SIM/worker_pid")
rel=$(basename "$(readlink "$NC_APP_LINK")")
[ "$rel" = "$(cat "$SIM/bad_heartbeat")" ] && pid=$((pid - 1))
if [ "$key" = "worker:heartbeat:test-host-$pid" ]; then date -u +%Y-%m-%dT%H:%M:%S.123456+00:00; else echo; fi
EOF

# ── a source repository with three releases ──────────────────────────────────
# A: revision 0001_a   C: code change, same revision   B: new migration 0002_b
REPO="$W/repo"
rm -rf "$REPO"; mkdir -p "$REPO"
git -C "$REPO" init -q
commit() {  # commit HEAD_REVISION MESSAGE
  mkdir -p "$REPO/deploy/linux/bin" "$REPO/src/backend"
  echo "$1" > "$REPO/src/backend/HEAD_REV"
  echo "fastapi" > "$REPO/src/backend/requirements.txt"
  echo "$2" > "$REPO/VERSION"
  cat > "$REPO/deploy/linux/bin/nc-migrate" <<'EOF'
#!/bin/sh
# fake nc-migrate: DB revision in $SIM/db_rev, code head in $NC_APP_DIR/HEAD_REV
head=$(cat "$NC_APP_DIR/HEAD_REV")
case "$1" in
  status) echo "database revision: $(cat "$SIM/db_rev")"; echo "code head:         $head" ;;
  upgrade)
    echo "migrate $(basename "$(dirname "$(dirname "$NC_APP_DIR")")")" >> "$SIM/calls"
    case "$(cat "$SIM/migrate_mode")" in
      ok) echo "$head" > "$SIM/db_rev" ;;
      fail_norev) exit 1 ;;
      fail_rev) echo "$head" > "$SIM/db_rev"; exit 1 ;;
    esac ;;
esac
EOF
  chmod +x "$REPO/deploy/linux/bin/nc-migrate"
  git -C "$REPO" add -A
  git -C "$REPO" -c user.name=test -c user.email=test@example.invalid commit -q -m "$2"
  git -C "$REPO" rev-parse HEAD
}
SHA_A=$(commit 0001_a A)
SHA_C=$(commit 0001_a C)
SHA_B=$(commit 0002_b B)

# ── per-case environment ─────────────────────────────────────────────────────
setup_case() {  # setup_case NAME – fresh state, release A active and healthy
  C="$W/case-$1"
  rm -rf "$C"; mkdir -p "$C/releases/$SHA_A" "$C/sim" "$C/secrets"
  git -C "$REPO" archive "$SHA_A" | tar -x -C "$C/releases/$SHA_A"
  echo "NC_RELEASE_SHA=$SHA_A" > "$C/releases/$SHA_A/.nc-release"
  ln -s "$C/releases/$SHA_A" "$C/app"
  SIM="$C/sim"
  echo 0001_a > "$SIM/db_rev"
  echo ok > "$SIM/backup_mode"; echo ok > "$SIM/migrate_mode"
  echo none > "$SIM/bad_health"; echo none > "$SIM/bad_heartbeat"
  printf 'nc-worker.service\nnc-api@desktop.service\nnc-api@admin.service\n' > "$SIM/active"
  echo 41 > "$SIM/pid_seq"; echo 41 > "$SIM/worker_pid"; : > "$SIM/calls"
  echo "redis://nc-worker:s3cret@127.0.0.1:6379/0" > "$C/secrets/REDIS_URL_WORKER"
}

run_deploy() {  # run_deploy SHA – sets RC
  RC=0
  env PATH="$STUBS:$PATH" SIM="$SIM" NC_APP_LINK="$C/app" NC_RELEASES_DIR="$C/releases" \
    NC_DEPLOY_REPO="$REPO" NC_DEPLOY_STATE="$C/state" NC_BACKUP_DIR="$C/backups" \
    NC_SECRETS="$C/secrets" NC_RUN_DIR="$C/run" NC_DEPLOY_VERIFY_TIMEOUT=2 NC_DEPLOY_VERIFY_INTERVAL=1 \
    sh "$DEPLOY" "$1" > "$C/out.log" 2>&1 || RC=$?
}

active_release() { basename "$(readlink "$C/app")"; }
expect() {  # expect DESCRIPTION CONDITION...
  desc=$1; shift
  if "$@"; then ok "$CASE: $desc"; else bad "$CASE: $desc"; sed 's/^/     | /' "$C/out.log"; fi
}
line_of() { grep -n "^$1" "$SIM/calls" | head -n 1 | cut -d: -f1; }
before() { a=$(line_of "$1"); b=$(line_of "$2"); [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ]; }
deployed() { grep -qx "$1" "$C/state/deployed.env"; }
worker_running() { grep -qxF nc-worker.service "$SIM/active"; }

# 1. success without a migration
CASE=success-no-migration; setup_case 1; run_deploy "$SHA_C"
expect "exit 0" [ "$RC" -eq 0 ]
expect "release switched" [ "$(active_release)" = "$SHA_C" ]
expect "SHA recorded" deployed "NC_DEPLOYED_SHA=$SHA_C"
expect "revision recorded" deployed "NC_DEPLOYED_ALEMBIC_REVISION=0001_a"
expect "services stopped before the backup" before stop backup
expect "backup before the migration" before backup migrate
expect "migration before the start" before migrate start
expect "backup file 0600" sh -c "[ \"\$(stat -c %a \"$C\"/backups/pre-deploy-*.dump)\" = 600 ]"

# 2. success with a migration
CASE=success-migration; setup_case 2; run_deploy "$SHA_B"
expect "exit 0" [ "$RC" -eq 0 ]
expect "database migrated" [ "$(cat "$SIM/db_rev")" = 0002_b ]
expect "revision recorded" deployed "NC_DEPLOYED_ALEMBIC_REVISION=0002_b"
expect "history written" grep -q "outcome=deployed" "$C/state/history.log"

# 3. invalid and unknown SHA: nothing stops
CASE=invalid-sha; setup_case 3; run_deploy "not-a-sha"
expect "exit 1" [ "$RC" -eq 1 ]
run_deploy "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
expect "unknown sha exit 1" [ "$RC" -eq 1 ]
expect "no service touched" [ ! -s "$SIM/calls" ]
expect "release unchanged" [ "$(active_release)" = "$SHA_A" ]

# 4. backup fails: release unchanged, services back, no migration
CASE=backup-failed; setup_case 4; echo fail > "$SIM/backup_mode"; run_deploy "$SHA_B"
expect "exit 1" [ "$RC" -eq 1 ]
expect "release unchanged" [ "$(active_release)" = "$SHA_A" ]
expect "not migrated" sh -c "! grep -q '^migrate' '$SIM/calls'"
expect "database untouched" [ "$(cat "$SIM/db_rev")" = 0001_a ]
expect "services running again" worker_running
expect "nothing recorded as deployed" [ ! -f "$C/state/deployed.env" ]

# 5. health fails, schema unchanged: automatic rollback
CASE=health-rollback; setup_case 5; echo "$SHA_C" > "$SIM/bad_health"; run_deploy "$SHA_C"
expect "exit 2" [ "$RC" -eq 2 ]
expect "previous release back" [ "$(active_release)" = "$SHA_A" ]
expect "services running" worker_running

# 6. migration fails without changing the revision: automatic rollback
CASE=migration-failed-unchanged; setup_case 6; echo fail_norev > "$SIM/migrate_mode"; run_deploy "$SHA_B"
expect "exit 2" [ "$RC" -eq 2 ]
expect "previous release back" [ "$(active_release)" = "$SHA_A" ]
expect "revision unchanged" [ "$(cat "$SIM/db_rev")" = 0001_a ]

# 7. failure after the revision changed: T8.1 – no automatic rollback, no restore
CASE=migration-failed-changed; setup_case 7; echo fail_rev > "$SIM/migrate_mode"; run_deploy "$SHA_B"
expect "exit 3" [ "$RC" -eq 3 ]
expect "new release stays" [ "$(active_release)" = "$SHA_B" ]
expect "no restore" [ "$(cat "$SIM/db_rev")" = 0002_b ]
expect "failure recorded" grep -q "NC_FAILED_SHA=$SHA_B" "$C/state/last-failure.env"
expect "backup reported" grep -q "pre-deploy-" "$C/out.log"

# 8. only the old worker's heartbeat is fresh: not accepted, rollback
CASE=stale-heartbeat; setup_case 8; echo "$SHA_C" > "$SIM/bad_heartbeat"; run_deploy "$SHA_C"
expect "exit 2" [ "$RC" -eq 2 ]
expect "worker-heartbeat named" grep -q "worker-heartbeat" "$C/out.log"
expect "previous release back" [ "$(active_release)" = "$SHA_A" ]

# 9. healthy start but the new schema rejects the old code: health fails after migration
CASE=health-failed-after-migration; setup_case 9; echo "$SHA_B" > "$SIM/bad_health"; run_deploy "$SHA_B"
expect "exit 3" [ "$RC" -eq 3 ]
expect "new release stays" [ "$(active_release)" = "$SHA_B" ]

[ -n "${NC_DEPLOY_TEST_DIR:-}" ] || rm -rf "$W"
[ "$fails" -eq 0 ] && echo "deploy_test: ALL PASSED" || { echo "deploy_test: $fails FAILED"; exit 1; }
