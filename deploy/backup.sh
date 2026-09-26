#!/usr/bin/env bash
# Dump the database to ./backups (keep 14 days). Cron example:
#   0 4 * * * /opt/ai-world/deploy/backup.sh >/dev/null 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
set -a; . ./.env; set +a
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-aiworld}" "${POSTGRES_DB:-aiworld}" | gzip > "backups/aiworld-$(date +%F-%H%M).sql.gz"
find backups -name 'aiworld-*.sql.gz' -mtime +14 -delete
echo "backup done"
