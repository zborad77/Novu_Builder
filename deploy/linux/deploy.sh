#!/bin/sh
# Copyright (c) 2026 Novusion
# Website: https://novusion.com
# Contact: info@novusion.com
#
# Author: Pavel Dostál
# Project: NovuConstruct
# Module: deploy/linux
# Description: Deploy one exact Git SHA of the Private Core with pre-deploy backup,
#              health/READY/heartbeat verification and the T8.1 rollback policy (F6.6).
# Created: 2026-11-10
#
#   deploy.sh <sha>      deploy the commit <sha> (7–40 hex chars, must resolve uniquely)
#
# Phases (README.md, section "Deploy a rollback"):
#   1. preflight   root, lock, exact SHA in $NC_DEPLOY_REPO, current release is a symlink,
#                  DB revision known to the new code (nc-migrate status of the staged release)
#   2. stage       git archive into $NC_RELEASES_DIR/<sha> + its own venv (nothing running changes)
#   3. stop        API zones and workers (consistent backup, no writes during migration)
#   4. backup      pg_dump -Fc verified by pg_restore --list (+ optional storage hook) – mandatory
#   5. switch      atomic symlink $NC_APP_LINK -> release
#   6. migrate     nc-migrate upgrade (only `upgrade head`, never downgrade)
#   7. start       units, then /health (desktop, admin), /ready (admin) and a fresh
#                  heartbeat of the NEW worker process (worker:heartbeat:<host>-<MainPID>)
#   8. record      $NC_DEPLOY_STATE/deployed.env (SHA + Alembic revision) and history.log
#
# Rollback policy T8.1 (the backend refuses to start unless the DB is exactly at the
# head of its own code, app/main.py lifespan):
#   * failure before the switch          -> release unchanged, services restarted   exit 1
#   * failure, DB revision unchanged      -> automatic return to the previous release exit 2
#   * failure, DB revision changed/unknown-> NO automatic rollback, NO restore; the new
#                                            release stays, the backup is printed     exit 3
#   * the rollback itself failed          -> manual intervention                     exit 4
set -eu

NC_APP_LINK=${NC_APP_LINK:-/opt/novuconstruct}
NC_RELEASES_DIR=${NC_RELEASES_DIR:-/opt/novuconstruct-releases}
NC_DEPLOY_REPO=${NC_DEPLOY_REPO:-/opt/novuconstruct-src.git}
NC_DEPLOY_STATE=${NC_DEPLOY_STATE:-/var/lib/nc-deploy}
NC_BACKUP_DIR=${NC_BACKUP_DIR:-/var/backups/novuconstruct}
NC_SECRETS=${NC_SECRETS:-/etc/novuconstruct/secrets}
NC_RUN_DIR=${NC_RUN_DIR:-/run/novuconstruct}
NC_DEPLOY_STORAGE_BACKUP=${NC_DEPLOY_STORAGE_BACKUP:-}
NC_DEPLOY_VERIFY_TIMEOUT=${NC_DEPLOY_VERIFY_TIMEOUT:-120}
NC_DEPLOY_VERIFY_INTERVAL=${NC_DEPLOY_VERIFY_INTERVAL:-3}
DB=novuconstruct
# Freshness of a worker heartbeat (app/platform/jobs/heartbeat.py WORKER_HEARTBEAT_FRESHNESS_SECONDS).
HEARTBEAT_FRESHNESS=90

CORE_UNITS="nc-worker.service nc-api@desktop.service nc-api@admin.service"
OPTIONAL_UNITS="nc-api@gateway.service nc-offer-worker.service nc-gateway.service"

say() { printf '==> %s\n' "$*"; }
err() { printf 'ERROR %s\n' "$*" >&2; }

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET=""; PREVIOUS=""; UNITS=""; BACKUP=""; REV_BEFORE=""; SWITCHED=0; LOCKED=0

history() {  # history OUTCOME DETAIL
  printf '%s sha=%s previous=%s outcome=%s %s\n' "$STAMP" "${TARGET:-?}" "${PREVIOUS:-?}" "$1" "$2" \
    >> "$NC_DEPLOY_STATE/history.log" 2>/dev/null || true
}

finish() {  # finish EXIT_CODE OUTCOME DETAIL
  history "$2" "$3"
  exit "$1"
}

cleanup() { [ "$LOCKED" -eq 1 ] && rmdir "$NC_DEPLOY_STATE/lock" 2>/dev/null; return 0; }
trap cleanup EXIT

# ── helpers ──────────────────────────────────────────────────────────────────
migrate_cmd() {  # migrate_cmd RELEASE_DIR ARGS...  – the nc-migrate of that release
  rel=$1; shift
  NC_APP_DIR="$rel/src/backend" NC_BACKUP_DIR="$NC_BACKUP_DIR" "$rel/deploy/linux/bin/nc-migrate" "$@"
}

db_revision() {  # db_revision RELEASE_DIR – prints the DB revision ("" when unknown/failure)
  out=$(migrate_cmd "$1" status 2>/dev/null) || return 1
  printf '%s\n' "$out" | sed -n 's/^database revision: *//p' | tail -n 1
}

code_head() {  # code_head RELEASE_DIR
  out=$(migrate_cmd "$1" status 2>/dev/null) || return 1
  printf '%s\n' "$out" | sed -n 's/^code head: *//p' | tail -n 1
}

switch_link() {  # switch_link RELEASE_DIR – atomic (rename of a new symlink over the old one)
  ln -sfn "$1" "$NC_APP_LINK.nc-new"
  mv -Tf "$NC_APP_LINK.nc-new" "$NC_APP_LINK"
}

# $UNITS is a list of unit names (no spaces inside a name); word splitting is intended.
# shellcheck disable=SC2086
stop_units() { systemctl stop $UNITS; }
# shellcheck disable=SC2086
start_units() { systemctl start $UNITS; }

probe() {  # probe ZONE PATH – HTTP 2xx over the zone's unix socket
  curl -fsS -o /dev/null --max-time 5 --unix-socket "$NC_RUN_DIR/$1/api.sock" "http://core/api/v1$2"
}

ready_admin() {  # /ready answers 200 only when ready; the body must say so as well
  body=$(curl -fsS --max-time 5 --unix-socket "$NC_RUN_DIR/admin/api.sock" "http://core/api/v1/ready") || return 1
  printf '%s' "$body" | grep -q '"ready": *true'
}

redis_get() {  # redis_get KEY – with the worker's ACL user; the password never in argv
  url=$(cat "$NC_SECRETS/REDIS_URL_WORKER")
  rest=${url#*://}; cred=${rest%%@*}; hostpart=${rest#*@}
  user=${cred%%:*}; pass=${cred#*:}
  hp=${hostpart%%/*}; dbn=${hostpart#*/}; [ "$dbn" != "$hostpart" ] || dbn=0
  host=${hp%:*}; port=${hp##*:}; [ "$port" != "$hp" ] || port=6379
  REDISCLI_AUTH=$pass redis-cli --no-auth-warning --user "$user" -h "$host" -p "$port" -n "${dbn:-0}" GET "$1"
}

worker_heartbeat_fresh() {  # heartbeat of the CURRENT worker process, not of a previous one
  pid=$(systemctl show -p MainPID --value nc-worker.service 2>/dev/null) || return 1
  case "$pid" in ''|0|*[!0-9]*) return 1 ;; esac
  [ "$pid" != "${OLD_WORKER_PID:-}" ] || return 1
  host=$(hostname | sed -E 's/[^A-Za-z0-9._-]+/-/g; s/^-+//; s/-+$//')
  ts=$(redis_get "worker:heartbeat:${host:-worker}-$pid" 2>/dev/null) || return 1
  [ -n "$ts" ] || return 1
  seen=$(date -u -d "$ts" +%s 2>/dev/null) || return 1
  age=$(( $(date -u +%s) - seen ))
  [ "$age" -ge -5 ] && [ "$age" -lt "$HEARTBEAT_FRESHNESS" ]
}

verify() {  # all checks must pass within NC_DEPLOY_VERIFY_TIMEOUT
  deadline=$(( $(date +%s) + NC_DEPLOY_VERIFY_TIMEOUT ))
  while :; do
    missing=""
    probe desktop /health || missing="$missing desktop/health"
    probe admin /health   || missing="$missing admin/health"
    ready_admin           || missing="$missing admin/ready"
    worker_heartbeat_fresh || missing="$missing worker-heartbeat"
    [ -n "$missing" ] || { say "verified: /health (desktop, admin), READY (admin), worker heartbeat"; return 0; }
    [ "$(date +%s)" -lt "$deadline" ] || { err "verification failed:$missing"; return 1; }
    sleep "$NC_DEPLOY_VERIFY_INTERVAL"
  done
}

rollback() {  # rollback REASON – only when the DB revision did not change (T8.1)
  err "$1; rolling back to $PREVIOUS (database revision $REV_BEFORE unchanged)"
  stop_units || true
  if [ "$SWITCHED" -eq 1 ]; then switch_link "$NC_RELEASES_DIR/$PREVIOUS" || finish 4 rollback-failed "$1; switch back failed"; fi
  OLD_WORKER_PID=$(systemctl show -p MainPID --value nc-worker.service 2>/dev/null || echo 0)
  if start_units && verify; then
    say "rolled back to $PREVIOUS; pre-deploy backup kept: $BACKUP"
    finish 2 rolled-back "$1"
  fi
  err "the rollback to $PREVIOUS did not come up healthy – manual intervention required (backup: $BACKUP)"
  finish 4 rollback-failed "$1"
}

after_schema_change() {  # after_schema_change REASON – T8.1: no automatic rollback, no restore
  err "$1"
  err "the database revision changed ($REV_BEFORE -> ${2:-unknown}); the previous release cannot run on it."
  err "NO automatic rollback and NO restore. Release $TARGET stays active at $NC_APP_LINK."
  err "Decide: fix forward with a new release, or restore the pre-deploy backup and switch back:"
  err "  backup:   $BACKUP"
  err "  previous: $NC_RELEASES_DIR/$PREVIOUS  (see README.md, Deploy a rollback)"
  {
    printf 'NC_FAILED_SHA=%s\nNC_FAILED_AT=%s\nNC_PREVIOUS_SHA=%s\n' "$TARGET" "$STAMP" "$PREVIOUS"
    printf 'NC_REVISION_BEFORE=%s\nNC_REVISION_AFTER=%s\nNC_PREDEPLOY_BACKUP=%s\n' "$REV_BEFORE" "${2:-unknown}" "$BACKUP"
  } > "$NC_DEPLOY_STATE/last-failure.env"
  finish 3 failed-after-migration "$1"
}

build_venv() {  # build_venv APP_DIR – venv from requirements.txt (or the package itself)
  [ -f "$1/requirements.txt" ] || [ -f "$1/pyproject.toml" ] || return 0
  python3 -m venv "$1/.venv" || return 1
  if [ -f "$1/requirements.txt" ]; then
    "$1/.venv/bin/pip" install --quiet --disable-pip-version-check -r "$1/requirements.txt"
  else
    "$1/.venv/bin/pip" install --quiet --disable-pip-version-check "$1"
  fi
}

# ── 1. preflight ─────────────────────────────────────────────────────────────
[ "$#" -eq 1 ] || { echo "usage: deploy.sh <sha>" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || { err "run as root"; exit 1; }
REQUESTED=$1
mkdir -p "$NC_DEPLOY_STATE"
chmod 0700 "$NC_DEPLOY_STATE"
mkdir "$NC_DEPLOY_STATE/lock" 2>/dev/null || { err "another deploy is running ($NC_DEPLOY_STATE/lock)"; exit 1; }
LOCKED=1

case "$REQUESTED" in
  *[!0-9a-f]*|'') err "'$REQUESTED' is not a commit SHA (7–40 lowercase hex characters)"; finish 1 refused invalid-sha ;;
esac
[ "${#REQUESTED}" -ge 7 ] && [ "${#REQUESTED}" -le 40 ] || { err "'$REQUESTED' must have 7–40 hex characters"; finish 1 refused invalid-sha; }
TARGET=$(git -C "$NC_DEPLOY_REPO" rev-parse --verify --quiet "$REQUESTED^{commit}" 2>/dev/null) || TARGET=""
case "$TARGET" in
  "$REQUESTED"*) ;;
  *) err "commit $REQUESTED not found in $NC_DEPLOY_REPO (git fetch first)"; TARGET=$REQUESTED; finish 1 refused unknown-sha ;;
esac

if [ ! -L "$NC_APP_LINK" ]; then
  err "$NC_APP_LINK is not a release symlink; convert it once (README.md, Deploy a rollback)"
  finish 1 refused no-release-symlink
fi
PREVIOUS=$(basename "$(readlink "$NC_APP_LINK")")
[ -d "$NC_RELEASES_DIR/$PREVIOUS" ] || { err "current release $NC_RELEASES_DIR/$PREVIOUS missing"; finish 1 refused no-previous-release; }
if [ "$PREVIOUS" = "$TARGET" ]; then say "$TARGET is already deployed; nothing to do"; exit 0; fi
say "deploying $TARGET (current release $PREVIOUS)"

# ── 2. stage (nothing running changes) ──────────────────────────────────────
RELEASE="$NC_RELEASES_DIR/$TARGET"
if [ ! -f "$RELEASE/.nc-release" ]; then
  say "staging $RELEASE"
  partial="$NC_RELEASES_DIR/.$TARGET.partial"
  umask 022
  rm -rf "$partial"; mkdir -p "$partial"
  if ! git -C "$NC_DEPLOY_REPO" archive --format=tar "$TARGET" | tar -x -C "$partial"; then
    rm -rf "$partial"; err "git archive of $TARGET failed"; finish 1 refused stage-failed
  fi
  if ! build_venv "$partial/src/backend"; then rm -rf "$partial"; err "backend venv failed"; finish 1 refused stage-failed; fi
  if [ -d "$NC_RELEASES_DIR/$PREVIOUS/src/gateway/.venv" ] && ! build_venv "$partial/src/gateway"; then
    rm -rf "$partial"; err "gateway venv failed"; finish 1 refused stage-failed
  fi
  printf 'NC_RELEASE_SHA=%s\nNC_STAGED_AT=%s\n' "$TARGET" "$STAMP" > "$partial/.nc-release"
  rm -rf "$RELEASE"; mv "$partial" "$RELEASE"
fi
[ -x "$RELEASE/deploy/linux/bin/nc-migrate" ] || { err "$RELEASE has no deploy/linux/bin/nc-migrate"; finish 1 refused stage-failed; }

# The database must be at a revision the new code knows (nc-migrate refuses otherwise).
REV_BEFORE=$(db_revision "$RELEASE") || { err "cannot read the database revision with the new code; refusing"; finish 1 refused revision-unknown; }
HEAD_NEW=$(code_head "$RELEASE")
say "database revision $REV_BEFORE, new code head $HEAD_NEW"

umask 077
mkdir -p "$NC_BACKUP_DIR"; chmod 0700 "$NC_BACKUP_DIR"

# ── 3. stop ──────────────────────────────────────────────────────────────────
UNITS=$CORE_UNITS
for u in $OPTIONAL_UNITS; do
  if systemctl is-active --quiet "$u"; then UNITS="$UNITS $u"; fi
done
OLD_WORKER_PID=$(systemctl show -p MainPID --value nc-worker.service 2>/dev/null || echo 0)
say "stopping $UNITS"
if ! stop_units; then
  start_units || true
  err "stopping the services failed"; finish 1 refused stop-failed
fi

restart_previous() {  # failure before the switch: the previous release keeps running
  err "$1; release $PREVIOUS unchanged"
  if start_units && verify; then finish 1 aborted-unchanged "$1"; fi
  err "the previous release did not come back healthy – manual intervention required"
  finish 4 rollback-failed "$1"
}

# ── 4. pre-deploy backup (mandatory) ────────────────────────────────────────
rev_tag=$(printf '%s' "${REV_BEFORE:-none}" | tr -c 'A-Za-z0-9_' '_')
BACKUP="$NC_BACKUP_DIR/pre-deploy-$STAMP-$(printf '%.12s' "$PREVIOUS")-$rev_tag.dump"
say "pre-deploy backup $BACKUP"
if ! runuser -u postgres -- pg_dump -Fc -d "$DB" > "$BACKUP"; then
  rm -f "$BACKUP"; restart_previous "pre-deploy backup failed"
fi
chmod 0600 "$BACKUP"
if [ ! -s "$BACKUP" ] || ! pg_restore --list "$BACKUP" >/dev/null 2>&1; then
  rm -f "$BACKUP"; restart_previous "pre-deploy backup is not a readable pg_dump archive"
fi
if [ -n "$NC_DEPLOY_STORAGE_BACKUP" ]; then
  if ! "$NC_DEPLOY_STORAGE_BACKUP" "$NC_BACKUP_DIR" "$STAMP"; then restart_previous "object storage backup hook failed"; fi
else
  say "NOTE: NC_DEPLOY_STORAGE_BACKUP not set – object storage is covered by the scheduled backup only"
fi
say "backup ok ($(wc -c < "$BACKUP") bytes)"

# ── 5. switch ────────────────────────────────────────────────────────────────
switch_link "$RELEASE" || restart_previous "switching $NC_APP_LINK failed"
SWITCHED=1

# ── 6. migrate ───────────────────────────────────────────────────────────────
if ! migrate_cmd "$NC_APP_LINK" upgrade; then
  rev_now=$(db_revision "$NC_APP_LINK") || rev_now="?"
  if [ "$rev_now" = "$REV_BEFORE" ]; then rollback "migration failed"; fi
  after_schema_change "migration failed" "$rev_now"
fi
REV_AFTER=$(db_revision "$NC_APP_LINK") || REV_AFTER="?"

# ── 7. start + verify ────────────────────────────────────────────────────────
say "starting $UNITS"
if ! start_units || ! verify; then
  if [ "$REV_AFTER" = "$REV_BEFORE" ]; then rollback "the new release did not come up healthy"; fi
  after_schema_change "the new release did not come up healthy" "$REV_AFTER"
fi

# ── 8. record ────────────────────────────────────────────────────────────────
{
  printf 'NC_DEPLOYED_SHA=%s\nNC_DEPLOYED_ALEMBIC_REVISION=%s\n' "$TARGET" "$REV_AFTER"
  printf 'NC_DEPLOYED_AT=%s\nNC_PREVIOUS_SHA=%s\nNC_PREDEPLOY_BACKUP=%s\n' "$STAMP" "$PREVIOUS" "$BACKUP"
} > "$NC_DEPLOY_STATE/deployed.env.nc-new"
mv -f "$NC_DEPLOY_STATE/deployed.env.nc-new" "$NC_DEPLOY_STATE/deployed.env"
say "deployed $TARGET at alembic revision $REV_AFTER"
finish 0 deployed "revision=$REV_AFTER backup=$BACKUP"
