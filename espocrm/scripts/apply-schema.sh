#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DB_CONTAINER_NAME="espocrm-db"
SCHEMA_FILE="$REPO_ROOT/espocrm/schema/live-parity.sql"

require_path() {
    local path="$1"
    if [[ ! -e "$path" ]]; then
        printf 'Missing required path: %s\n' "$path" >&2
        exit 1
    fi
}

require_command() {
    local command_name="$1"
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Missing required command: %s\n' "$command_name" >&2
        exit 1
    fi
}

require_command docker
require_path "$SCHEMA_FILE"

if ! docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER_NAME"; then
    printf 'Container %s is not running. Start EspoCRM first.\n' "$DB_CONTAINER_NAME" >&2
    exit 1
fi

printf 'Applying supplemental live-parity schema...\n'
docker exec -i "$DB_CONTAINER_NAME" sh -lc 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" espocrm' < "$SCHEMA_FILE"
printf 'Supplemental schema applied.\n'
