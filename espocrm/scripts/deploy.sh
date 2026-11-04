#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ESPO_ROOT="/var/www/espocrm"
ESPO_DATA="$ESPO_ROOT/data/espocrm"
CUSTOM_DST="$ESPO_DATA/persistent/custom"
CLIENT_DST="$ESPO_DATA/persistent/custom-client"
STATE_FILE="$ESPO_DATA/persistent/data/state.php"
CONTAINER_NAME="espocrm"

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
require_command rsync

require_path "$REPO_ROOT/espocrm/server/custom"
require_path "$REPO_ROOT/espocrm/client/custom"
require_path "$REPO_ROOT/espocrm/patches/ClientManager.php"
require_path "$REPO_ROOT/espocrm/config/config-overrides.php"
require_path "$REPO_ROOT/espocrm/scripts/merge-config.php"
require_path "$REPO_ROOT/espocrm/scripts/apply-schema.sh"
require_path "$REPO_ROOT/espocrm/scripts/verify-schema.sh"
require_path "$CUSTOM_DST"
require_path "$CLIENT_DST"
require_path "$STATE_FILE"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    printf 'Container %s is not running. Start EspoCRM first.\n' "$CONTAINER_NAME" >&2
    exit 1
fi

printf 'Syncing server custom files...\n'
rsync -a --delete "$REPO_ROOT/espocrm/server/custom/" "$CUSTOM_DST/"

printf 'Syncing client custom files...\n'
rsync -a --delete "$REPO_ROOT/espocrm/client/custom/" "$CLIENT_DST/"

printf 'Updating ClientManager.php inside container...\n'
docker cp "$REPO_ROOT/espocrm/patches/ClientManager.php" "$CONTAINER_NAME:/var/www/html/application/Espo/Core/Utils/ClientManager.php"
docker exec "$CONTAINER_NAME" php -l /var/www/html/application/Espo/Core/Utils/ClientManager.php >/dev/null

printf 'Merging safe config overrides...\n'
docker cp "$REPO_ROOT/espocrm/scripts/merge-config.php" "$CONTAINER_NAME:/tmp/merge-config.php"
docker cp "$REPO_ROOT/espocrm/config/config-overrides.php" "$CONTAINER_NAME:/tmp/config-overrides.php"
docker exec "$CONTAINER_NAME" php /tmp/merge-config.php /var/www/html/data/config.php /tmp/config-overrides.php
docker exec "$CONTAINER_NAME" php -l /var/www/html/data/config.php >/dev/null

printf 'Bumping appTimestamp...\n'
timestamp="$(date +%s)"
sed -i "s/appTimestamp' => [0-9]*/appTimestamp' => ${timestamp}/" "$STATE_FILE"
docker exec "$CONTAINER_NAME" php -l /var/www/html/data/state.php >/dev/null

printf 'Rebuilding EspoCRM metadata...\n'
docker exec --user www-data "$CONTAINER_NAME" php command.php rebuild >/dev/null

printf 'Applying supplemental live-parity schema...\n'
"$SCRIPT_DIR/apply-schema.sh"

printf 'Restarting php-fpm container to clear opcode cache...\n'
docker restart "$CONTAINER_NAME" >/dev/null

printf 'Verifying custom scripts are referenced...\n'
docker exec "$CONTAINER_NAME" grep -q 'past-due-highlight.js' /var/www/html/application/Espo/Core/Utils/ClientManager.php

printf 'Verifying schema parity...\n'
"$SCRIPT_DIR/verify-schema.sh"

printf 'Deploy complete.\n'
