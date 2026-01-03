#!/bin/bash
# ✅ APPROVED: Database Backup Script
# scripts/backup-database.sh
# Reference: docs/architecture/operational-runbooks.md § 6.2 (Backup & Recovery)

set -e

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="saraise_backup_${DATE}.sql"

echo "🗄️ Starting database backup..."

# Create backup directory
mkdir -p ${BACKUP_DIR}

# Backup database
# CRITICAL: All backups must be immutable and fully audited
# See docs/architecture/operational-runbooks.md § 6.2
pg_dump ${POSTGRES_CONNECTION_STRING} > ${BACKUP_DIR}/${BACKUP_FILE}

# Compress backup
gzip ${BACKUP_DIR}/${BACKUP_FILE}

# Clean up old backups (keep last 7 days)
find ${BACKUP_DIR} -name "saraise_backup_*.sql.gz" -mtime +7 -delete

echo "✅ Database backup complete: ${BACKUP_FILE}.gz"

