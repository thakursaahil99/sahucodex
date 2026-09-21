#!/bin/sh
# Container entrypoint for the API: apply migrations, optionally seed, then start the server.
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] applying database migrations"
  alembic upgrade head
fi

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] seeding development data (demo users are skipped when APP_ENV=production)"
  python /srv/database/seeds/run.py
fi

exec "$@"
