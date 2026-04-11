#!/bin/bash
# AutoTrader Pro — Daily Database Backup
# Add to crontab: 0 2 * * * /var/www/autotrader/deploy/backup.sh

BACKUP_DIR="/var/backups/autotrader"
DB_NAME="autotrader"
DB_USER="autotrader"
DATE=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR"

echo "[$DATE] Starting backup..."
pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/autotrader_$DATE.sql.gz"

if [ $? -eq 0 ]; then
    echo "[$DATE] Backup successful: autotrader_$DATE.sql.gz"
else
    echo "[$DATE] ERROR: Backup failed!"
    exit 1
fi

# Delete backups older than KEEP_DAYS
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$KEEP_DAYS -delete
echo "[$DATE] Cleaned up old backups. Current backups:"
ls -lh "$BACKUP_DIR"
