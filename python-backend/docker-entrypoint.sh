#!/bin/sh
set -eu

echo "Starting server..."
echo "Database migrations are deployment responsibility; startup will fail fast if schema is not at Alembic head."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
