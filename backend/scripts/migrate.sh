#!/bin/sh
# One-shot: apply migrations, then seed the world (idempotent).
set -e
alembic upgrade head
if [ "${AUTO_SEED:-true}" = "true" ]; then
  python -m app.world.seed
fi
