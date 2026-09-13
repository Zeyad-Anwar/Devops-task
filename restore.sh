#!/usr/bin/env bash
# PostgreSQL restore script for barq-assessment
set -euo pipefail

CONTAINER="postgres"

# Accept backup file as argument, or find the latest one
if [ $# -ge 1 ]; then
    BACKUP_FILE="$1"
else
    BACKUP_DIR="./backups"
    BACKUP_FILE=$(ls -t "${BACKUP_DIR}"/*.dump 2>/dev/null | head -1)
    if [ -z "${BACKUP_FILE}" ]; then
        echo "ERROR: No backup file found in ${BACKUP_DIR}/" >&2
        echo "Usage: $0 [backup_file.dump]" >&2
        exit 1
    fi
fi

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file not found: ${BACKUP_FILE}" >&2
    exit 1
fi

echo "=== BARQ PostgreSQL Restore ==="
echo "Container: ${CONTAINER}"
echo "Restoring: ${BACKUP_FILE}"
echo ""

# Copy backup file into the container
echo "Copying backup to container..."
docker cp "${BACKUP_FILE}" "${CONTAINER}:/tmp/restore.dump"

# Restore using pg_restore inside the container
echo "Running pg_restore..."
docker exec "${CONTAINER}" pg_restore \
    -U barq_app \
    -d barq_tasks \
    --clean \
    --if-exists \
    --no-owner \
    /tmp/restore.dump || true
# Note: pg_restore may return non-zero for warnings (e.g. "does not exist" on clean),
# which is expected when restoring to a fresh database.

# Clean up temp file
docker exec "${CONTAINER}" rm -f /tmp/restore.dump

# Verify restore by checking records table
echo ""
echo "Verifying restore..."
RECORD_COUNT=$(docker exec "${CONTAINER}" psql -U barq_app -d barq_tasks -t -c "SELECT count(*) FROM records;" | tr -d ' ')
echo "Records in database: ${RECORD_COUNT}"

if [ "${RECORD_COUNT}" -gt 0 ]; then
    echo "Restore successful"
else
    echo "WARNING: No records found after restore" >&2
    exit 1
fi
