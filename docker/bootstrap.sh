#!/bin/sh
set -eu

DATA_DIR="${APP_DATA_DIR:-/app/storage}"
mkdir -p "$DATA_DIR"

if [ ! -f "$DATA_DIR/operations.db" ]; then
    python /app/backend/seed_database.py
fi

if [ "${SKIP_POLICY_INGEST:-0}" != "1" ] && [ ! -f "$DATA_DIR/vectorstore/chroma.sqlite3" ]; then
    python /app/backend/ingest_policies.py
fi

exec "$@"
