#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/www/espocrm-backup}"
TAR_KEEP_DAYS="${TAR_KEEP_DAYS:-14}"
SQL_KEEP_DAYS="${SQL_KEEP_DAYS:-30}"
DB_CONTAINER="${DB_CONTAINER:-espocrm-db}"
ESPO_HOME="${ESPO_HOME:-/var/www/espocrm}"

mkdir -p "$BACKUP_DIR/sql"
chmod 700 "$BACKUP_DIR" "$BACKUP_DIR/sql"

ts="$(date +%F_%H%M%S)"
tmp="$BACKUP_DIR/sql/.db-$ts.sql.gz.tmp"

cleanup() {
    rm -f "$tmp"
}
trap cleanup EXIT

printf 'Creating logical database dump...\n'

docker exec "$DB_CONTAINER" sh -lc \
    'exec mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --single-transaction --quick --routines --triggers --events --all-databases' \
    | gzip >"$tmp"

gzip -t "$tmp"
mv "$tmp" "$BACKUP_DIR/sql/db-$ts.sql.gz"
chmod 600 "$BACKUP_DIR/sql/db-$ts.sql.gz"

printf 'Logical dump: %s\n' "$BACKUP_DIR/sql/db-$ts.sql.gz"

if [ -x "$ESPO_HOME/command.sh" ]; then
    printf 'Creating full application backup...\n'
    "$ESPO_HOME/command.sh" backup
fi

find "$BACKUP_DIR" -maxdepth 1 -type f -name '*.tar.gz' -mtime +"$TAR_KEEP_DAYS" -delete
find "$BACKUP_DIR/sql" -type f -name '*.sql.gz' -mtime +"$SQL_KEEP_DAYS" -delete

printf '%s backup complete\n' "$ts"
