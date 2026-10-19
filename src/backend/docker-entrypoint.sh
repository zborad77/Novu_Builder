#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

echo "Starting server..."
echo "Database migrations are deployment responsibility; startup will fail fast if schema is not at Alembic head."
# Proxy headers are resolved by the app from TRUSTED_PROXY_IPS (app/core/client_ip.py).
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers
