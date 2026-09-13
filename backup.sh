#!/usr/bin/env bash
# PostgreSQL backup script for barq-assessment
set -euo pipefail

BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/barq_tasks_${TIMESTAMP}.dump"
CONTAINER="postgres"

mkdir -p "${BACKUP_DIR}"

echo "=== BARQ PostgreSQL Backup ==="
echo "Timestamp: ${TIMESTAMP}"
echo "Container: ${CONTAINER}"
echo "Output:    ${BACKUP_FILE}"
echo ""

# Run pg_dump inside the postgres container
echo "Running pg_dump..."
docker exec "${CONTAINER}" pg_dump \
    -U barq_app \
    -d barq_tasks \
    -F custom \
    --clean \
    --if-exists \
    > "${BACKUP_FILE}"

# Verify the backup file exists and is non-empty
if [ -s "${BACKUP_FILE}" ]; then
    SIZE=$(stat --format="%s" "${BACKUP_FILE}" 2>/dev/null || stat -f "%z" "${BACKUP_FILE}" 2>/dev/null)
    echo "Backup successful: ${BACKUP_FILE} (${SIZE} bytes)"
else
    echo "ERROR: Backup file is empty or missing" >&2
    exit 1
fi
