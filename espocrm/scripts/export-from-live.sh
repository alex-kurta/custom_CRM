#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
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

require_path /var/www/espocrm/data/espocrm/persistent/custom
require_path /var/www/espocrm/data/espocrm/persistent/custom-client

printf 'Refreshing server custom tree from live instance...\n'
rsync -a --delete \
    --exclude='test_www' \
    --exclude='test_www2' \
    /var/www/espocrm/data/espocrm/persistent/custom/ \
    "$REPO_ROOT/espocrm/server/custom/"

printf 'Refreshing client custom tree from live instance...\n'
rsync -a --delete \
    --exclude='dummy.txt' \
    /var/www/espocrm/data/espocrm/persistent/custom-client/ \
    "$REPO_ROOT/espocrm/client/custom/"

printf 'Refreshing ClientManager.php and patch...\n'
docker cp "$CONTAINER_NAME:/var/www/html/application/Espo/Core/Utils/ClientManager.php" "$REPO_ROOT/espocrm/patches/ClientManager.php"
docker run --rm --entrypoint=cat espocrm/espocrm:fpm /var/www/html/application/Espo/Core/Utils/ClientManager.php > /tmp/opencode/ClientManager.stock.php
tr -d '\r' < /tmp/opencode/ClientManager.stock.php > /tmp/opencode/ClientManager.stock.lf.php
tr -d '\r' < "$REPO_ROOT/espocrm/patches/ClientManager.php" > /tmp/opencode/ClientManager.live.lf.php
tmp_patch="$(mktemp)"
set +e
diff -u /tmp/opencode/ClientManager.stock.lf.php /tmp/opencode/ClientManager.live.lf.php > "$tmp_patch"
diff_status=$?
set -e

if [[ $diff_status -gt 1 ]]; then
    printf 'Failed generating ClientManager patch.\n' >&2
    rm -f "$tmp_patch"
    exit 1
fi

sed "s|/tmp/opencode/ClientManager.stock.lf.php|a/application/Espo/Core/Utils/ClientManager.php|; s|/tmp/opencode/ClientManager.live.lf.php|b/application/Espo/Core/Utils/ClientManager.php|" \
    "$tmp_patch" > "$REPO_ROOT/espocrm/patches/ClientManager.php.patch"
rm -f "$tmp_patch"

printf 'Export complete. Review git diff before committing.\n'
