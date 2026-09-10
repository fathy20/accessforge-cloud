#!/bin/sh
# API container entrypoint: bring the schema to head, then serve.
#
# RUN_MIGRATIONS=0 skips the schema step (e.g. when a release pipeline runs
# `alembic upgrade head` once, before rolling several API replicas).
set -eu
cd /app

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  case "${DATABASE_URL:-}" in
    sqlite*)
      # db_bootstrap creates a fresh SQLite file with `alembic upgrade head`
      # (never create_all + stamp, which is how the dev DB drifted) and
      # upgrades a known revision in place.
      python -m backend.tools.db_bootstrap --url "$DATABASE_URL" --upgrade-existing
      ;;
    "")
      echo "DATABASE_URL is unset; skipping migrations." >&2
      ;;
    *)
      python -m alembic upgrade head
      ;;
  esac
fi

exec python -m uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
