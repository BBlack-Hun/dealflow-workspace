#!/usr/bin/env bash
# Container entrypoint. For the web service (RUN_MIGRATIONS=1) it applies DB
# migrations + idempotent demo seed before starting. The agent service skips this
# (it never touches the DB — HTTP only).
set -euo pipefail

cd /app

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] mkdir data dir: ${DEALFLOW_DATA_DIR:-/app/data}"
  mkdir -p "${DEALFLOW_DATA_DIR:-/app/data}"

  echo "[entrypoint] alembic upgrade head"
  alembic upgrade head

  echo "[entrypoint] seed demo data (idempotent)"
  python scripts/seed_demo.py
fi

echo "[entrypoint] exec: $*"
exec "$@"
