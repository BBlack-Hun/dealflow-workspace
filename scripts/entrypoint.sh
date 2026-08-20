#!/usr/bin/env bash
# Container entrypoint. For the web service (RUN_MIGRATIONS=1) it applies DB
# migrations + idempotent bootstrap before starting. The agent service skips this
# (it never touches the DB — HTTP only).
set -euo pipefail

cd /app

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] mkdir data dir: ${DEALFLOW_DATA_DIR:-/app/data}"
  mkdir -p "${DEALFLOW_DATA_DIR:-/app/data}"

  echo "[entrypoint] alembic upgrade head"
  alembic upgrade head

  echo "[entrypoint] bootstrap (팀 기본 문구 + 관리자; 데모는 DEALFLOW_SEED_DEMO=1 일 때만)"
  python scripts/bootstrap.py
fi

echo "[entrypoint] exec: $*"
exec "$@"
