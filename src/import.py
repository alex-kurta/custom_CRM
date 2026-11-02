#!/usr/bin/env python3
"""
Bulk import — idempotent, paginated, dry-run capable (AGENTS.md §4 Phase 1).

  .venv/bin/python -m src.import --dry-run --limit 10      # preview 10 per entity
  .venv/bin/python -m src.import --dry-run                  # preview all (batch 500)
  .venv/bin/python -m src.import --entity Account           # only Accounts
  .venv/bin/python -m src.import                             # real run

Idempotency: upsert by fishbowlId via EspoCRM API search; stores fishbowlId→espoId in data/map.json
Safety: never truncates; DRY_RUN logs without writes; --limit caps total per entity.

Entities: Account (customer), Product (part), Vendor→Account[type=Vendor] (optional)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from src.config import sync as sync_cfg, has_fishbowl_config, has_espo_config
from src.fishbowl.client import fetch_all
from src.espocrm.client import upsert_entity
from src.espocrm.mapper import customer_to_account, part_to_product, vendor_to_account

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MAP_PATH = DATA_DIR / "map.json"
LOGS_DIR = ROOT / "logs"


def _load_map() -> dict:
    if MAP_PATH.exists():
        try:
            with open(MAP_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_map(m: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, default=str)


def _paginate_query(base_sql: str, limit: int, offset: int):
    return base_sql.rstrip().rstrip(";") + " LIMIT %s OFFSET %s", (limit, offset)


def _import_entity(
    entity: str,
    fishbowl_table: str,
    base_sql: str,
    mapper,
    args,
    stats: dict,
    id_map: dict,
) -> None:
    batch = sync_cfg.batch_size
    total_limit = args.limit  # None means unlimited
    offset = 0
    imported = 0
    created = 0
    updated = 0
    skipped = 0

    print(f"\n[{entity}] table={fishbowl_table} sql={base_sql[:80]}... batch={batch} limit={total_limit} dryRun={args.dry_run}")

    while True:
        # Honor --limit overall
        if total_limit is not None and imported >= total_limit:
            break
        cur_batch = batch
        if total_limit is not None:
            cur_batch = min(batch, total_limit - imported)

        sql, params = _paginate_query(base_sql, cur_batch, offset)
        # offset for next iteration
        offset += cur_batch

        try:
            rows = fetch_all(sql, params)
        except Exception as e:
            # Table may not exist in this Fishbowl version
            print(f"[{entity}] query failed (table missing?) — {e}")
            stats[entity] = {"error": str(e)[:200], "imported": imported}
            break

        if not rows:
            print(f"[{entity}] no more rows at offset {offset - cur_batch}")
            break

        for row in rows:
            # PII redaction for logs: only log fishbowl id, not full row
            fb_id = row.get("id") or row.get("customerId") or row.get("partId") or row.get("vendorId") or "?"
            try:
                payload = mapper(row)
            except Exception as e:
                print(f"[{entity}] mapper error id={fb_id}: {e}")
                skipped += 1
                continue

            fb_key = payload.get("fishbowlId", str(fb_id))

            if args.dry_run:
                print(f"  DRY-RUN {entity} fishbowlId={fb_key} → {payload.get('name', '')[:60]}")
                imported += 1
                continue

            try:
                result, was_created = upsert_entity(entity, fb_key, payload)
                espo_id = result.get("id", "?")
                # Persist mapping
                id_map.setdefault(entity, {})[str(fb_key)] = espo_id
                if was_created:
                    created += 1
                else:
                    updated += 1
                imported += 1
                if imported % 50 == 0:
                    print(f"[{entity}] progress: {imported} (created {created}, updated {updated})")
            except Exception as e:
                print(f"[{entity}] upsert failed fishbowlId={fb_key}: {e}")
                skipped += 1
                # Continue; don't abort bulk on single failure

        # Persist map periodically
        if not args.dry_run and imported % 100 == 0:
            _save_map(id_map)

        # If last batch smaller than cur_batch, we're done
        if len(rows) < cur_batch:
            break

    # Final counts
    if args.dry_run:
        print(f"[{entity}] DRY-RUN done: {imported} would be upserted, {skipped} skipped")
    else:
        print(f"[{entity}] done: {imported} (created {created}, updated {updated}, skipped {skipped})")
    stats[entity] = {"imported": imported, "created": created, "updated": updated, "skipped": skipped}
    if not args.dry_run:
        _save_map(id_map)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fishbowl → EspoCRM bulk import (idempotent, paginated)")
    parser.add_argument("--dry-run", action="store_true", help="preview mappings without writes")
    parser.add_argument("--limit", type=int, default=None, help="max rows per entity (e.g., 10 for preview)")
    parser.add_argument("--entity", type=str, default=None, help="only import this EspoCRM entity (Account, Product)")
    parser.add_argument("--batch-size", type=int, default=None, help="override SYNC_BATCH_SIZE")
    args = parser.parse_args()

    # Allow batch size override via CLI without env mutation
    if args.batch_size is not None:
        # monkey-patch for this run (config uses property, so we adjust via env)
        import os
        os.environ["SYNC_BATCH_SIZE"] = str(args.batch_size)

    print("=== Fishbowl → EspoCRM Bulk Import ===")
    print(f"{datetime.now(timezone.utc).isoformat()}  dryRun={args.dry_run} limit={args.limit} entity={args.entity}")
    print(f"[Config] batchSize={sync_cfg.batch_size} interval={sync_cfg.interval_minutes}min")
    print(f"[Config] fishbowlConfig={has_fishbowl_config()} espoConfig={has_espo_config()}")

    if not has_fishbowl_config():
        print("ERROR: FISHBOWL_DB_* incomplete — set .env (see .env.example)")
        return 1
    if not has_espo_config() and not args.dry_run:
        print("ERROR: ESPOCRM_API_KEY missing — cannot write without --dry-run")
        return 1
    if args.dry_run and not has_espo_config():
        print("WARN: no EspoCRM key — dry-run will only preview Fishbowl→mapping, no API calls")

    id_map = _load_map()
    stats: dict[str, Any] = {}

    # Entity registry: (EspoCRM entity, Fishbowl table, base SQL, mapper)
    registry = [
        ("Account", "customer", "SELECT c.* FROM customer c WHERE c.id IN (SELECT DISTINCT customerId FROM `so`) ORDER BY c.id ASC", customer_to_account),
        ("Product", "part", "SELECT p.* FROM part p ORDER BY p.id ASC", part_to_product),
        # Vendor as Account type=Vendor — optional; can be skipped via --entity filter
        # Uncomment to enable by default:
        # ("Account", "vendor", "SELECT v.* FROM vendor v ORDER BY v.id ASC", vendor_to_account),
    ]

    # Filter by --entity if provided
    filtered = registry
    if args.entity:
        filtered = [r for r in registry if r[0].lower() == args.entity.lower()]
        if not filtered:
            print(f"Unknown entity '{args.entity}' — available: {', '.join(r[0] for r in registry)}")
            return 1

    # Vendor is same EspoCRM entity as customer but different source; handle separately if requested
    # For now registry covers Account+Product; user can also import vendors via explicit flag
    # If someone passes --entity Vendor, map to Account/vendor
    if args.entity and args.entity.lower() == "vendor":
        filtered = [("Account", "vendor", "SELECT v.* FROM vendor v ORDER BY v.id ASC", vendor_to_account)]

    for entity, table, sql, mapper in filtered:
        _import_entity(entity, table, sql, mapper, args, stats, id_map)

    print("\n--- Summary ---")
    for e, s in stats.items():
        print(f"  {e}: {s}")

    # Log to logs/sync.log (append, no secrets)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOGS_DIR / "sync.log"
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(f"{datetime.now(timezone.utc).isoformat()} import dryRun={args.dry_run} limit={args.limit} stats={json.dumps(stats)}\n")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
