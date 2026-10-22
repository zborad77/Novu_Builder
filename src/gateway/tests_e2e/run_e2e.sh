#!/usr/bin/env bash
# E2E gateway ↔ core (NC-007): spustí core v zóně gateway a gateway, pustí tests_e2e, obojí ukončí.
#
# Předpoklady (jen lokální vývoj, žádná produkční data):
#   - PostgreSQL 16 na NC_E2E_PG (výchozí localhost:55432, postgres/postgres), databáze se vytvoří znovu,
#   - Redis 7 na NC_E2E_REDIS_HOST:PORT (výchozí localhost:56379), používá DB 3 (core) a 4 (gateway),
#   - venv src/backend/.venv a src/gateway/.venv.
# RATE_LIMIT_LOGIN core je zvýšený jen pro tento testovací běh (E2E se přihlašuje víckrát z jedné IP);
# limity loginu samotné testují tests/ (gateway) a sada core.
# Klíče jsou náhodné pro každý běh, nikde se neukládají.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PG="${NC_E2E_PG:-postgres:postgres@localhost:55432}"
REDIS="${NC_E2E_REDIS:-localhost:56379}"
DB="${NC_E2E_DB:-nc_e2e_gateway}"
CORE_PORT="${NC_E2E_CORE_PORT:-8010}"
GW_PORT="${NC_E2E_GATEWAY_PORT:-8080}"
WORK="$(mktemp -d)"
command -v cygpath >/dev/null && WORK="$(cygpath -m "$WORK")"  # Windows Python nezná /tmp z Git Bash
PY_CORE="$ROOT/src/backend/.venv/Scripts/python.exe"; [ -x "$PY_CORE" ] || PY_CORE="$ROOT/src/backend/.venv/bin/python"
PY_GW="$ROOT/src/gateway/.venv/Scripts/python.exe"; [ -x "$PY_GW" ] || PY_GW="$ROOT/src/gateway/.venv/bin/python"

HMAC_SECRET="$("$PY_GW" -c 'import secrets; print(secrets.token_hex(32))')"
SESSION_KEY="$("$PY_GW" -c 'import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())')"

"$PY_CORE" - "$PG" "$DB" <<'EOF'
import sys, psycopg
user_pass, host = sys.argv[1].split("@")
with psycopg.connect(f"postgresql://{user_pass}@{host}/postgres", autocommit=True) as conn:
    conn.execute(f'DROP DATABASE IF EXISTS "{sys.argv[2]}" WITH (FORCE)')
    conn.execute(f'CREATE DATABASE "{sys.argv[2]}"')
EOF

cleanup() {
  for pid in "${GW_PID:-}" "${WORKER_PID:-}" "${CORE_PID:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT

# Prostředí core i workeru (worker je nutný: bez heartbeat core odmítne upload fotek 503).
core_env() {
  export APP_ENV=development NC_ZONE=gateway NC_GATEWAY_HMAC_KEYS="gw-e2e:$HMAC_SECRET"
  export DATABASE_URL="postgresql+asyncpg://$PG/$DB" DATABASE_URL_SYNC="postgresql+psycopg://$PG/$DB"
  export DB_AUTO_CREATE_SCHEMA=true DB_SEED_ON_STARTUP=true JWT_SECRET="$JWT_SECRET"
  export REDIS_URL="redis://$REDIS/3" STORAGE_ROOT="$WORK/storage" AI_ANALYSIS_PROVIDER=mock AI_OFFER_PROVIDER=mock
  export LOG_LEVEL="${NC_E2E_LOG_LEVEL:-WARNING}" PYTHONUTF8=1 RATE_LIMIT_LOGIN=100/minute WORKER_HEAVY_CONCURRENCY=1
}
JWT_SECRET="e2e-$("$PY_GW" -c 'import secrets; print(secrets.token_hex(16))')"
"$PY_GW" -c "import redis; redis.Redis.from_url('redis://$REDIS/3').flushdb()"

(cd "$ROOT/src/backend" && core_env && exec "$PY_CORE" -m uvicorn app.main:app --host 127.0.0.1 --port "$CORE_PORT") \
  > "$WORK/core.log" 2>&1 &
CORE_PID=$!
sleep 8  # schéma a seed vytvoří API, worker startuje až po něm
(cd "$ROOT/src/backend" && core_env && exec "$PY_CORE" -m app.worker.runner) > "$WORK/worker.log" 2>&1 &
WORKER_PID=$!

"$PY_GW" -c "import redis; redis.Redis.from_url('redis://$REDIS/4').flushdb()"
(
  cd "$ROOT/src/gateway"
  NC_ENV=development NC_BFF_PUBLIC_ORIGIN=http://localhost:5173 NC_BFF_DEV_INSECURE_COOKIE=1 \
  NC_BFF_CORE_URL="http://127.0.0.1:$CORE_PORT" NC_GATEWAY_HMAC_KEY="gw-e2e:$HMAC_SECRET" \
  NC_BFF_SESSION_KEYS="e2e:$SESSION_KEY" NC_BFF_REDIS_URL="redis://$REDIS/4" \
  NC_BFF_ALLOWLIST_PATH="$ROOT/docs/security/gateway-allowlist.json" \
  NC_BFF_LISTEN_HOST=127.0.0.1 NC_BFF_LISTEN_PORT="$GW_PORT" \
  exec "$PY_GW" -m nc_gateway
) > "$WORK/gateway.log" 2>&1 &
GW_PID=$!

for _ in $(seq 1 90); do
  if "$PY_GW" -c "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:$GW_PORT/bff/health').status_code==200 and httpx.post('http://127.0.0.1:$CORE_PORT/api/v1/auth/login').status_code==401 else 1)" 2>/dev/null; then
    break
  fi
  sleep 1
done

sleep 5  # worker zapíše heartbeat
set +e
(cd "$ROOT/src/gateway" && NC_E2E_GATEWAY_URL="http://127.0.0.1:$GW_PORT" NC_E2E_ORIGIN=http://localhost:5173 \
  "$PY_GW" -m pytest tests_e2e -v --no-header -rfE -p no:cacheprovider)
STATUS=$?
set -e

# bezpečnostní události z gateway musí skončit v audit_logs core
"$PY_CORE" - "$PG" "$DB" <<'EOF'
import sys, psycopg
user_pass, host = sys.argv[1].split("@")
with psycopg.connect(f"postgresql://{user_pass}@{host}/{sys.argv[2]}") as conn:
    rows = conn.execute("SELECT action, count(*) FROM audit_logs WHERE action LIKE 'gateway.%' GROUP BY action ORDER BY action").fetchall()
print("audit_logs gateway.*:", rows)
EOF

echo "logy: $WORK/core.log $WORK/worker.log $WORK/gateway.log"
exit "$STATUS"
