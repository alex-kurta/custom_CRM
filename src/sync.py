#!/usr/bin/env python3
"""
Incremental sync — every 30 min via cron (AGENTS.md §4 Phase 2).

  .venv/bin/python -m src.sync --dry-run
  .venv/bin/python -m src.sync

State: data/lastSyncAt.txt  (ISO timestamp, UTC)
Logic: SELECT ... WHERE dateLastModified > :lastSyncAt  else fallback to full scan with limit
Upsert: idempotent via fishbowlId → EspoCRM API
Cron:  */30 * * * * cd /path/to/project && .venv/bin/python -m src.sync >> logs/cron.log 2>&1

Configurable via SYNC_INTERVAL_MINUTES / SYNC_BATCH_SIZE env vars (default 30 / 500).
Logs to logs/sync.log (no secrets).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from src.config import sync as sync_cfg, has_fishbowl_config, has_espo_config
from src.fishbowl.client import fetch_all, fetch_one
from src.espocrm.client import upsert_entity
from src.espocrm.mapper import customer_to_account, part_to_product

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LAST_SYNC_PATH = DATA_DIR / "lastSyncAt.txt"
LOGS_DIR = ROOT / "logs"
MAP_PATH = DATA_DIR / "map.json"


def _read_last_sync() -> str | None:
    if LAST_SYNC_PATH.exists():
        try:
            txt = LAST_SYNC_PATH.read_text(encoding="utf-8").strip()
            if txt:
                return txt
        except Exception:
            return None
    return None


def _write_last_sync(ts: str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LAST_SYNC_PATH.write_text(ts + "\n", encoding="utf-8")


def _load_map() -> dict:
    if MAP_PATH.exists():
        try:
            return json.loads(MAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_map(m: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(m, indent=2, default=str), encoding="utf-8")


def _parse_ts(ts: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            # Handle Z suffix
            cleaned = ts.replace("Z", "+00:00").strip()
            # Try fromisoformat first
            try:
                dt = datetime.fromisoformat(cleaned)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass
            return datetime.strptime(ts.strip(), fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _delta_or_full(
    table: str,
    date_column: str,
    last_sync: str | None,
    base_order: str,
    batch: int,
) -> list[dict]:
    """
    Try delta: WHERE dateColumn > lastSync  ORDER BY dateColumn
    On failure (column missing), fall back to full scan ORDER BY id.
    Returns at most batch rows.
    """
    if last_sync:
        # Try delta
        try:
            sql = f"SELECT * FROM `{table}` WHERE `{date_column}` > %s ORDER BY `{date_column}` ASC LIMIT %s"
            rows = fetch_all(sql, (last_sync, batch))
            if rows:
                print(f"  delta {table}: {len(rows)} rows since {last_sync} (col {date_column})")
                return rows
            print(f"  delta {table}: 0 rows since {last_sync}")
            return []
        except Exception as e:
            print(f"  delta {table} failed (col {date_column} missing?) — {e} — falling back to full scan")
    # Full scan fallback — Paginated full scan would need offset; for incremental we just take latest batch
    try:
        sql = f"SELECT * FROM `{table}` ORDER BY {base_order} ASC LIMIT %s"
        rows = fetch_all(sql, (batch,))
        print(f"  full scan {table}: {len(rows)} rows (order {base_order})")
        return rows
    except Exception as e:
        print(f"  full scan {table} failed — {e}")
        return []


def _sync_customers(last_sync: str | None, args, id_map: dict, stats: dict) -> None:
    batch = sync_cfg.batch_size
    # Probe if dateLastModified exists via schema cache or try delta
    rows = _delta_or_full("customer", "dateLastModified", last_sync, "id", batch)
    # Alternative column names if first delta returned 0 but table non-empty? Try dateModified
    if not rows and last_sync:
        # Try alternate column
        try:
            alt = fetch_all("SELECT * FROM `customer` WHERE `dateModified` > %s ORDER BY `dateModified` ASC LIMIT %s", (last_sync, batch))
            if alt:
                rows = alt
                print(f"  delta customer (alt col dateModified): {len(rows)} rows")
        except Exception:
            pass

    created = updated = skipped = 0
    for row in rows:
        fb_id = row.get("id") or row.get("customerId") or "?"
        # Skip customers with zero sales orders
        try:
            so_check = fetch_all("SELECT 1 FROM `so` WHERE customerId = %s LIMIT 1", (fb_id,))
            if not so_check:
                skipped += 1
                continue
        except Exception:
            pass
        try:
            payload = customer_to_account(row)
        except Exception as e:
            print(f"  customer mapper skip id={fb_id}: {e}")
            skipped += 1
            continue
        fb_key = payload.get("fishbowlId", str(fb_id))
        if args.dry_run:
            print(f"  DRY-RUN Account fishbowlId={fb_key} → {payload.get('name', '')[:60]}")
            continue
        try:
            result, was_created = upsert_entity("Account", fb_key, payload)
            id_map.setdefault("Account", {})[str(fb_key)] = result.get("id", "?")
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as e:
            print(f"  Account upsert fail fishbowlId={fb_key}: {e}")
            skipped += 1
    stats["Account"] = {"found": len(rows), "created": created, "updated": updated, "skipped": skipped}
    print(f"[Account] found {len(rows)} → created {created} updated {updated} skipped {skipped}")


def _sync_products(last_sync: str | None, args, id_map: dict, stats: dict) -> None:
    batch = sync_cfg.batch_size
    rows = _delta_or_full("part", "dateLastModified", last_sync, "id", batch)
    if not rows and last_sync:
        try:
            alt = fetch_all("SELECT * FROM `part` WHERE `dateModified` > %s ORDER BY `dateModified` ASC LIMIT %s", (last_sync, batch))
            if alt:
                rows = alt
                print(f"  delta part (alt col dateModified): {len(rows)} rows")
        except Exception:
            pass

    created = updated = skipped = 0
    for row in rows:
        fb_id = row.get("id") or row.get("partId") or "?"
        try:
            payload = part_to_product(row)
        except Exception as e:
            print(f"  part mapper skip id={fb_id}: {e}")
            skipped += 1
            continue
        fb_key = payload.get("fishbowlId", str(fb_id))
        if args.dry_run:
            print(f"  DRY-RUN Product fishbowlId={fb_key} sku={payload.get('sku','')}")
            continue
        try:
            result, was_created = upsert_entity("Product", fb_key, payload)
            id_map.setdefault("Product", {})[str(fb_key)] = result.get("id", "?")
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as e:
            print(f"  Product upsert fail fishbowlId={fb_key}: {e}")
            skipped += 1
    stats["Product"] = {"found": len(rows), "created": created, "updated": updated, "skipped": skipped}
    print(f"[Product] found {len(rows)} → created {created} updated {updated} skipped {skipped}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fishbowl → EspoCRM incremental sync (30min cron)")
    parser.add_argument("--dry-run", action="store_true", help="preview without writes; does not update lastSyncAt")
    parser.add_argument("--force-full", action="store_true", help="ignore lastSyncAt and do full scan batch")
    parser.add_argument("--since", type=str, default=None, help="override lastSyncAt timestamp (e.g., '2024-01-01 00:00:00')")
    args = parser.parse_args()

    print("=== Fishbowl ↔ EspoCRM Incremental Sync ===")
    print(f"{datetime.now(timezone.utc).isoformat()}  dryRun={args.dry_run} forceFull={args.force_full} since={args.since}")

    if not has_fishbowl_config():
        print("ERROR: FISHBOWL_DB_* incomplete — set .env")
        return 1
    if not has_espo_config() and not args.dry_run:
        print("ERROR: ESPOCRM_API_KEY missing — cannot write without --dry-run")
        return 1

    last_sync = args.since or _read_last_sync()
    if args.force_full:
        last_sync = None

    if last_sync:
        print(f"[State] lastSyncAt: {last_sync}")
        # Validate parsable
        if not _parse_ts(last_sync):
            print(f"[State] lastSyncAt unparsable, will try as-is; consider resetting data/lastSyncAt.txt")
    else:
        print("[State] lastSyncAt: (none) — first run will do full scan batch")

    print(f"[Config] batchSize={sync_cfg.batch_size} interval={sync_cfg.interval_minutes}min")

    id_map = _load_map()
    stats: dict[str, Any] = {}

    # Sync each entity
    _sync_customers(last_sync, args, id_map, stats)
    _sync_products(last_sync, args, id_map, stats)

    # Persist map + lastSyncAt on success (only if not dry-run)
    if not args.dry_run:
        _save_map(id_map)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        _write_last_sync(now_iso)
        print(f"[State] updated lastSyncAt → {now_iso}")
    else:
        print("[State] dry-run — lastSyncAt NOT updated")

    print("\n--- Summary ---")
    for e, s in stats.items():
        print(f"  {e}: {s}")

    # Append to logs/sync.log (no secrets)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOGS_DIR / "sync.log", "a", encoding="utf-8") as log:
            log.write(f"{datetime.now(timezone.utc).isoformat()} sync dryRun={args.dry_run} lastSync={last_sync} stats={json.dumps(stats)}\n")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
