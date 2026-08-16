#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
DATABASE_URL="${DATABASE_URL:-postgresql://oia:oia@localhost:5432/oia}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/oia-${STAMP}.sql"

mkdir -p "${BACKUP_DIR}"
pg_dump "${DATABASE_URL}" > "${TARGET}"
echo "backup written to ${TARGET}"

if [[ "${2:-}" == "--restore" ]]; then
  psql "${DATABASE_URL}" < "${TARGET}"
  echo "restore complete from ${TARGET}"
fi
