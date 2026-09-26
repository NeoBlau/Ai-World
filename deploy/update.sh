#!/usr/bin/env bash
# Pull the latest code and restart (keeps the database and .env).
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only || true
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml ps
