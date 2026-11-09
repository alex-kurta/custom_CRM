#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CONTAINER="${CONTAINER:-espocrm}"
PATCH_SRC="$REPO_ROOT/espocrm/patches/ClientManager.php"
PATCH_DST="/var/www/html/application/Espo/Core/Utils/ClientManager.php"
FPM_CONF="/usr/local/etc/php-fpm.d/zzz-custom.conf"
FPM_PROCESSES="${FPM_PROCESSES:-16}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    exit 0
fi

changed=0

if [ -f "$PATCH_SRC" ]; then
    src_sum="$(md5sum "$PATCH_SRC" | awk '{print $1}')"
    dst_sum="$(docker exec "$CONTAINER" md5sum "$PATCH_DST" 2>/dev/null | awk '{print $1}' || true)"

    if [ "$src_sum" != "$dst_sum" ]; then
        docker cp "$PATCH_SRC" "$CONTAINER:$PATCH_DST"
        changed=1
    fi
fi

desired="[www]
pm = dynamic
pm.max_children = $FPM_PROCESSES
pm.start_servers = 4
pm.min_spare_servers = 2
pm.max_spare_servers = 8
pm.max_requests = 500"

current="$(docker exec "$CONTAINER" cat "$FPM_CONF" 2>/dev/null || true)"

if [ "$current" != "$desired" ]; then
    printf '%s\n' "$desired" | docker exec -i "$CONTAINER" sh -c "cat > '$FPM_CONF'"
    changed=1
fi

if [ "$changed" -eq 1 ]; then
    docker restart "$CONTAINER" >/dev/null
    printf '%s restored container-only config and restarted %s\n' "$(date -Is)" "$CONTAINER"
fi
