"""
Fishbowl schema discovery — caches locally to data/schema-cache.json
No PII: only table names, row counts, column metadata (field/type/null/key).
The cache is intentionally gitignored; do not commit it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.fishbowl.client import fetch_all, fetch_one

# Project root = /path/to/project
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
CACHE_PATH = DATA_DIR / "schema-cache.json"

# Key tables to probe for counts/columns (AGENTS.md §3) — order matters for logging
KEY_TABLES = [
    "customer",
    "vendor",
    "part",
    "product",
    "inventory",
    "partinventory",
    "so",
    "soitem",
    "po",
    "poitem",
    "qbclass",
    "address",
]


def _show_tables() -> list[str]:
    rows = fetch_all("SHOW TABLES")
    # mysql-connector returns dict with key like "Tables_in_<db>"
    tables: list[str] = []
    for r in rows:
        # grab first value regardless of key name
        tables.append(next(iter(r.values())))
    return sorted(tables)


def discover() -> dict[str, Any]:
    """
    Discover Fishbowl schema:
      - SHOW TABLES
      - COUNT(*) per key table (if exists)
      - DESCRIBE per key table
    Returns dict {tables, counts, columns, errors} and writes cache to data/schema-cache.json
    """
    errors: list[str] = []
    tables = _show_tables()

    counts: dict[str, int] = {}
    columns: dict[str, list[dict]] = {}

    for t in KEY_TABLES:
        if t not in tables:
            continue
        # COUNT
        try:
            row = fetch_one(f"SELECT COUNT(*) AS cnt FROM `{t}`")
            counts[t] = int(row["cnt"]) if row else 0
        except Exception as e:
            errors.append(f"COUNT {t}: {e}")
            counts[t] = -1
        # COLUMNS
        try:
            desc = fetch_all(f"DESCRIBE `{t}`")
            # Normalize to {field, type, null, key, default, extra}
            cols = []
            for c in desc:
                cols.append(
                    {
                        "field": c.get("Field") or c.get("field"),
                        "type": c.get("Type") or c.get("type"),
                        "null": c.get("Null") or c.get("null"),
                        "key": c.get("Key") or c.get("key"),
                        "default": c.get("Default"),
                        "extra": c.get("Extra"),
                    }
                )
            columns[t] = cols
        except Exception as e:
            errors.append(f"DESCRIBE {t}: {e}")

    # Also include non-key tables in counts? Just list them; don't flood counts.
    data: dict[str, Any] = {
        "tables": tables,
        "counts": counts,
        "columns": columns,
        "errors": errors,
    }

    # Persist cache (no secrets)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        errors.append(f"cache write: {e}")

    return data


def load_cache() -> dict[str, Any] | None:
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None
