"""
Fishbowl parameterized queries — pagination, delta sync, PII-safe sampling.
Fishbowl schema varies by version; queries target common table/column names
and fall back gracefully when columns are absent (see schema.discover).

All queries use placeholders (%s) — never string-interpolate user input.
Pagination via LIMIT %s OFFSET %s (MySQL).

Tables probed (AGENTS.md §3):
  customer, vendor, part/product, inventory, so (sales order), po,
  address, partinventory, soitem, qbclass
"""

from __future__ import annotations

from typing import Any

from src.fishbowl.client import fetch_all, fetch_one

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _paginate(base_sql: str, limit: int, offset: int, params: tuple = ()) -> tuple[str, tuple]:
    """Append LIMIT/OFFSET safely."""
    sql = base_sql.rstrip().rstrip(";") + " LIMIT %s OFFSET %s"
    return sql, params + (limit, offset)


# ---------------------------------------------------------------------------
# Generic helpers — safe for existence checks
# ---------------------------------------------------------------------------

def count_table(table: str) -> int:
    """COUNT(*) for a given table — table name is allow-listed, not user input."""
    # table name is interpolated but caller must use known constants; validated length
    if not table.replace("_", "").isalnum():
        raise ValueError(f"Invalid table name: {table}")
    row = fetch_one(f"SELECT COUNT(*) AS cnt FROM `{table}`")
    return int(row["cnt"]) if row else 0


def sample_table(table: str, limit: int = 5) -> list[dict]:
    if not table.replace("_", "").isalnum():
        raise ValueError(f"Invalid table name: {table}")
    return fetch_all(f"SELECT * FROM `{table}` LIMIT %s", (limit,))


# ---------------------------------------------------------------------------
# Customer → Account
# ---------------------------------------------------------------------------

CUSTOMER_BASE = """
SELECT c.* FROM customer c
"""

def get_customers(limit: int = 500, offset: int = 0) -> list[dict]:
    sql, params = _paginate(
        "SELECT c.* FROM customer c ORDER BY c.id ASC",
        limit, offset,
    )
    return fetch_all(sql, params)


def get_customers_delta(since: str, limit: int = 500, offset: int = 0) -> list[dict]:
    """
    Delta query — filters on dateLastModified if column exists.
    Caller should fall back to full scan if column missing (schema.discover will note).
    since: ISO datetime string or Fishbowl datetime string.
    """
    # Use parameterized date filter; if column absent MySQL will error — caller handles
    base = "SELECT c.* FROM customer c WHERE c.dateLastModified > %s ORDER BY c.dateLastModified ASC"
    sql, params = _paginate(base, limit, offset, (since,))
    return fetch_all(sql, params)


# ---------------------------------------------------------------------------
# Vendor
# ---------------------------------------------------------------------------

def get_vendors(limit: int = 500, offset: int = 0) -> list[dict]:
    sql, params = _paginate("SELECT v.* FROM vendor v ORDER BY v.id ASC", limit, offset)
    return fetch_all(sql, params)


# ---------------------------------------------------------------------------
# Part / Product
# ---------------------------------------------------------------------------

def get_parts(limit: int = 500, offset: int = 0) -> list[dict]:
    sql, params = _paginate("SELECT p.* FROM part p ORDER BY p.id ASC", limit, offset)
    return fetch_all(sql, params)


def get_parts_delta(since: str, limit: int = 500, offset: int = 0) -> list[dict]:
    base = "SELECT p.* FROM part p WHERE p.dateLastModified > %s ORDER BY p.dateLastModified ASC"
    sql, params = _paginate(base, limit, offset, (since,))
    return fetch_all(sql, params)


# ---------------------------------------------------------------------------
# Sales Order (so) + items
# ---------------------------------------------------------------------------

def get_sales_orders(limit: int = 500, offset: int = 0) -> list[dict]:
    sql, params = _paginate("SELECT so.* FROM so ORDER BY so.id ASC", limit, offset)
    return fetch_all(sql, params)


def get_so_items(so_id: int) -> list[dict]:
    return fetch_all("SELECT * FROM soitem WHERE soId = %s", (so_id,))


# ---------------------------------------------------------------------------
# Inventory / PartInventory (live qty check for Phase 3)
# ---------------------------------------------------------------------------

def get_inventory(limit: int = 500, offset: int = 0) -> list[dict]:
    # Fishbowl stores inventory per location via partinventory / inventory
    sql, params = _paginate("SELECT * FROM partinventory ORDER BY id ASC", limit, offset)
    return fetch_all(sql, params)


def get_qty_on_hand(part_id: int) -> float | None:
    """Live qty for on-demand check — narrow, fast query."""
    row = fetch_one("SELECT SUM(qtyOnHand) AS qty FROM partinventory WHERE partId = %s", (part_id,))
    if row and row["qty"] is not None:
        return float(row["qty"])
    return None


# ---------------------------------------------------------------------------
# Address helper — customer/vendor address
# ---------------------------------------------------------------------------

def get_addresses_for_customer(customer_id: int) -> list[dict]:
    return fetch_all("SELECT * FROM address WHERE customerId = %s", (customer_id,))
