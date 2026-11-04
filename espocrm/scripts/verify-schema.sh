#!/usr/bin/env bash
set -euo pipefail

DB_CONTAINER_NAME="espocrm-db"

require_command() {
    local command_name="$1"
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Missing required command: %s\n' "$command_name" >&2
        exit 1
    fi
}

require_command docker

if ! docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER_NAME"; then
    printf 'Container %s is not running. Start EspoCRM first.\n' "$DB_CONTAINER_NAME" >&2
    exit 1
fi

read -r -d '' SQL <<'SQL' || true
SELECT 'MISSING TABLE c_sales_order'
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'espocrm' AND table_name = 'c_sales_order'
);

SELECT 'MISSING TABLE c_sales_order_item'
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'espocrm' AND table_name = 'c_sales_order_item'
);

SELECT CONCAT(
    'SCHEMA DRIFT ', expected.table_name, '.', expected.column_name,
    ' expected type=', expected.column_type,
    ' nullable=', expected.is_nullable,
    ' default=', expected.column_default,
    ' got type=', COALESCE(actual.column_type, '<missing>'),
    ' nullable=', COALESCE(actual.is_nullable, '<missing>'),
    ' default=', COALESCE(actual.column_default, '<missing>')
)
FROM (
    SELECT 'account' AS table_name, 'c_fishbowl_id' AS column_name, 'varchar(255)' AS column_type, 'YES' AS is_nullable, 'NULL' AS column_default
    UNION ALL SELECT 'account', 'c_fishbowl_last_modified', 'datetime', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_c_order_count', 'int(11)', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_order_count', 'int(11)', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_order_rank', 'int(11)', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_last_contacted', 'datetime', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_last_contacted_reason', 'mediumtext', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_capital_osint', 'double', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_capital_osint_currency', 'varchar(3)', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_top_product', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_avg_orders_per_year', 'double', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_category', 'varchar(100)', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_follow_up_date', 'date', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_do_not_contact', 'tinyint(1)', 'NO', '0'
    UNION ALL SELECT 'account', 'c_bankrupt', 'tinyint(1)', 'NO', '0'
    UNION ALL SELECT 'account', 'c_do_not_sell', 'tinyint(1)', 'NO', '0'
    UNION ALL SELECT 'account', 'c_outstanding_orders', 'int(11)', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_last_contacted_by_id', 'varchar(17)', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_past_due', 'tinyint(1)', 'NO', '0'
    UNION ALL SELECT 'account', 'c_past_due_amount', 'double', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_past_due_date', 'date', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_past_due_data', 'mediumtext', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_past_due_amount_currency', 'varchar(3)', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'cDaysOverdue', 'int(11)', 'YES', '0'
    UNION ALL SELECT 'account', 'c_days_overdue', 'int(11)', 'YES', '0'
    UNION ALL SELECT 'account', 'c_last_ordered_date', 'date', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_total_order_amount', 'double', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_total_order_amount_currency', 'varchar(3)', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_last_reminder_sent', 'datetime', 'YES', 'NULL'
    UNION ALL SELECT 'account', 'c_pre_pay', 'tinyint(1)', 'NO', '0'
    UNION ALL SELECT 'account', 'c_comments', 'mediumtext', 'YES', 'NULL'
    UNION ALL SELECT 'contact', 'c_fishbowl_id', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'contact', 'c_do_not_contact', 'tinyint(1)', 'NO', '0'
    UNION ALL SELECT 'opportunity', 'c_fishbowl_id', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'id', 'varchar(17)', 'NO', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'name', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'deleted', 'tinyint(1)', 'YES', '0'
    UNION ALL SELECT 'c_sales_order', 'description', 'mediumtext', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'created_at', 'datetime', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'modified_at', 'datetime', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'stream_updated_at', 'datetime', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'created_by_id', 'varchar(17)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'modified_by_id', 'varchar(17)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'assigned_user_id', 'varchar(17)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'fishbowl_id', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'fishbowl_num', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'customer_id', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'amount', 'double', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'amount_currency', 'varchar(3)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'status', 'varchar(100)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'order_date', 'datetime', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'account_id', 'varchar(17)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order', 'item_summary', 'mediumtext', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'id', 'varchar(17)', 'NO', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'name', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'deleted', 'tinyint(1)', 'YES', '0'
    UNION ALL SELECT 'c_sales_order_item', 'description', 'mediumtext', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'created_at', 'datetime', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'modified_at', 'datetime', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'created_by_id', 'varchar(17)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'modified_by_id', 'varchar(17)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'assigned_user_id', 'varchar(17)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'fishbowl_id', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'fishbowl_so_id', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'product_num', 'varchar(255)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'qty_ordered', 'double', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'qty_fulfilled', 'double', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'total_price', 'double', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'total_price_currency', 'varchar(3)', 'YES', 'NULL'
    UNION ALL SELECT 'c_sales_order_item', 'sales_order_id', 'varchar(17)', 'YES', 'NULL'
) expected
LEFT JOIN information_schema.columns actual
    ON actual.table_schema = 'espocrm'
    AND actual.table_name = expected.table_name
    AND actual.column_name = expected.column_name
WHERE actual.column_name IS NULL
    OR actual.column_type <> expected.column_type
    OR actual.is_nullable <> expected.is_nullable
    OR COALESCE(actual.column_default, 'NULL') <> expected.column_default;

SELECT CONCAT(
    'INDEX DRIFT ', expected.table_name, '.', expected.index_name,
    ' expected unique=', expected.is_unique,
    ' columns=', expected.columns,
    ' got unique=', COALESCE(actual.is_unique, '<missing>'),
    ' columns=', COALESCE(actual.columns, '<missing>')
)
FROM (
    SELECT 'account' AS table_name, 'IDX_C_LAST_CONTACTED_BY' AS index_name, '0' AS is_unique, 'c_last_contacted_by_id' AS columns
    UNION ALL SELECT 'c_sales_order', 'UNIQ_CREATED_AT_ID', '1', 'created_at,id'
    UNION ALL SELECT 'c_sales_order', 'IDX_NAME', '0', 'name,deleted'
    UNION ALL SELECT 'c_sales_order', 'IDX_ASSIGNED_USER', '0', 'assigned_user_id,deleted'
    UNION ALL SELECT 'c_sales_order', 'IDX_CREATED_AT', '0', 'created_at'
    UNION ALL SELECT 'c_sales_order', 'IDX_CREATED_BY_ID', '0', 'created_by_id'
    UNION ALL SELECT 'c_sales_order', 'IDX_MODIFIED_BY_ID', '0', 'modified_by_id'
    UNION ALL SELECT 'c_sales_order', 'IDX_ASSIGNED_USER_ID', '0', 'assigned_user_id'
    UNION ALL SELECT 'c_sales_order', 'IDX_ACCOUNT_ID', '0', 'account_id'
    UNION ALL SELECT 'c_sales_order_item', 'UNIQ_CREATED_AT_ID', '1', 'created_at,id'
    UNION ALL SELECT 'c_sales_order_item', 'IDX_NAME', '0', 'name,deleted'
    UNION ALL SELECT 'c_sales_order_item', 'IDX_ASSIGNED_USER', '0', 'assigned_user_id,deleted'
    UNION ALL SELECT 'c_sales_order_item', 'IDX_CREATED_AT', '0', 'created_at'
    UNION ALL SELECT 'c_sales_order_item', 'IDX_CREATED_BY_ID', '0', 'created_by_id'
    UNION ALL SELECT 'c_sales_order_item', 'IDX_MODIFIED_BY_ID', '0', 'modified_by_id'
    UNION ALL SELECT 'c_sales_order_item', 'IDX_ASSIGNED_USER_ID', '0', 'assigned_user_id'
    UNION ALL SELECT 'c_sales_order_item', 'IDX_SALES_ORDER_ID', '0', 'sales_order_id'
) expected
LEFT JOIN (
    SELECT
        table_name,
        index_name,
        CAST(1 - MIN(non_unique) AS CHAR) AS is_unique,
        GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',') AS columns
    FROM information_schema.statistics
    WHERE table_schema = 'espocrm'
    GROUP BY table_name, index_name
) actual
    ON actual.table_name = expected.table_name
    AND actual.index_name = expected.index_name
WHERE actual.index_name IS NULL
    OR actual.is_unique <> expected.is_unique
    OR actual.columns <> expected.columns;
SQL

issues="$(printf '%s\n' "$SQL" | docker exec -i "$DB_CONTAINER_NAME" sh -lc 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" espocrm -N')"

if [[ -n "$issues" ]]; then
    printf '%s\n' "$issues" >&2
    exit 1
fi

printf 'Schema verify OK.\n'
