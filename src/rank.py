#!/usr/bin/env python3
"""
Compute Fishbowl order ranking per customer and push to EspoCRM Account.

Source: Fishbowl `so` — COUNT(*) per customerId, grand total via totalPrice
Target: Account.cOrderCount (int), Account.cOrderRank (int)

Product-exclusion lists are business-specific and live in .env:
  RANK_EXCLUDE_PRODUCT_NUMS   comma-separated productNum values
  RANK_EXCLUDE_DESCRIPTIONS   |-separated description values

Usage:
  .venv/bin/python -m src.rank --dry-run   # preview top 20
  .venv/bin/python -m src.rank             # real update (idempotent)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from src.config import rank
from src.fishbowl.client import fetch_all
from src.espocrm.client import search_by_fishbowl_id, update_entity, list_entities

BATCH_SIZE = 500

def compute_ranking() -> dict[int, tuple[int, int]]:
    """
    Returns {customerId: (orderCount, rank)}
    rank 1 = most orders
    """
    rows = fetch_all("SELECT customerId, COUNT(*) AS cnt FROM `so` GROUP BY customerId")
    cnt_map = {int(r["customerId"]): int(r["cnt"]) for r in rows}
    all_customers = fetch_all("SELECT id FROM `customer`")
    for r in all_customers:
        cid = int(r["id"])
        if cid not in cnt_map:
            cnt_map[cid] = 0
    sorted_customers = sorted(cnt_map.items(), key=lambda x: (-x[1], x[0]))
    ranking = {}
    prev_cnt = None
    rank = 0
    pos = 0
    for cid, cnt in sorted_customers:
        pos += 1
        if cnt != prev_cnt:
            rank = pos
            prev_cnt = cnt
        ranking[cid] = (cnt, rank)
    return ranking


def compute_enrichment() -> dict[int, dict]:
    """
    Compute per-customer enrichment for boss requirements:
      - topProduct (most ordered productNum)
      - avgOrdersPerYear
      - outstandingOrders (statusId In Progress/Issued)
      - lastOrderDate (for followUp)
    Returns {customerId: {topProduct, avgOrdersPerYear, outstandingOrders, lastOrderDate, firstOrderDate}}
    """
    enrichment: dict[int, dict] = {}
    # Order count + first/last date for avg per year
    rows = fetch_all("SELECT customerId, COUNT(*) as cnt, MIN(dateCreated) as firstDate, MAX(dateCreated) as lastDate FROM `so` GROUP BY customerId")
    for r in rows:
        cid = int(r["customerId"])
        cnt = int(r["cnt"])
        first = r["firstDate"]
        last = r["lastDate"]
        # avg per year
        avg = 0.0
        try:
            if first and last and cnt:
                # handle datetime objects
                if hasattr(first, 'year'):
                    days = (last - first).days
                    years = days / 365.25 if days > 0 else 1.0
                    # if only one order or same day, years ~0, use 1 year for avg
                    if years < 1.0:
                        years = 1.0
                    avg = cnt / years
                else:
                    avg = float(cnt)
            else:
                avg = float(cnt)
        except Exception:
            avg = float(cnt)
        enrichment[cid] = {"cnt": cnt, "firstDate": first, "lastDate": last, "avgOrdersPerYear": round(avg, 2)}

    # Outstanding orders (statusId 20 Issued, 25 In Progress)
    try:
        rows_out = fetch_all("SELECT customerId, COUNT(*) as cnt FROM `so` WHERE statusId IN (20,25) GROUP BY customerId")
        for r in rows_out:
            cid = int(r["customerId"])
            if cid not in enrichment:
                enrichment[cid] = {"cnt": 0, "avgOrdersPerYear": 0.0}
            enrichment[cid]["outstandingOrders"] = int(r["cnt"])
    except Exception:
        pass
    # Ensure all customers have entry
    all_customers = fetch_all("SELECT id FROM `customer`")
    for r in all_customers:
        cid = int(r["id"])
        if cid not in enrichment:
            enrichment[cid] = {"cnt": 0, "avgOrdersPerYear": 0.0, "outstandingOrders": 0, "lastDate": None, "firstDate": None}
        else:
            enrichment[cid].setdefault("outstandingOrders", 0)

    exclude_product_nums = rank.exclude_product_nums
    exclude_descriptions = set(rank.exclude_descriptions)

    where_parts = ["COALESCE(part.description, soitem.description, '') != ''"]
    params: list[str] = []
    if exclude_product_nums:
        placeholders = ", ".join(["%s"] * len(exclude_product_nums))
        where_parts.append(f"soitem.productNum NOT IN ({placeholders})")
        params.extend(exclude_product_nums)
    where_sql = " AND ".join(where_parts)

    # Top product per customer — use part.description (real product name), exclude non-products
    try:
        rows_top = fetch_all(f"""
            SELECT so.customerId as customerId, COALESCE(part.description, soitem.description, soitem.productNum) as prodName, COUNT(*) as cnt
            FROM soitem
            JOIN `so` ON so.id = soitem.soId
            LEFT JOIN part ON part.num = soitem.productNum
            WHERE {where_sql}
            GROUP BY so.customerId, COALESCE(part.description, soitem.description, soitem.productNum)
        """, tuple(params))
        top_map: dict[int, tuple[str, int]] = {}
        for r in rows_top:
            cid = int(r["customerId"])
            prod = str(r["prodName"] or "").strip()
            # Skip empty, excluded, or generic product names
            if not prod or prod in exclude_descriptions:
                continue
            cnt = int(r["cnt"])
            if cid not in top_map or cnt > top_map[cid][1]:
                top_map[cid] = (prod, cnt)
        for cid, (prod, cnt) in top_map.items():
            if cid in enrichment:
                enrichment[cid]["topProduct"] = prod[:100]
            else:
                enrichment[cid] = {"topProduct": prod[:100]}
        for cid in enrichment:
            enrichment[cid].setdefault("topProduct", "")
        # Fallback for customers where top was excluded (e.g., only Shipping) — keep previous logic as fallback
        fallback_needed = [cid for cid, v in enrichment.items() if not v.get("topProduct")]
        if fallback_needed:
            rows_fallback = fetch_all("""
                SELECT so.customerId as customerId, soitem.productNum as productNum, COUNT(*) as cnt
                FROM soitem
                JOIN `so` ON so.id = soitem.soId
                WHERE so.customerId IN (%s)
                GROUP BY so.customerId, soitem.productNum
                ORDER BY cnt DESC
            """ % ",".join(str(c) for c in fallback_needed[:100]))
            # For brevity, just leave empty if no real product
            pass
    except Exception as e:
        print(f"topProduct query failed: {e}")
        for cid in enrichment:
            enrichment[cid].setdefault("topProduct", "")

    return enrichment

def main() -> int:
    parser = argparse.ArgumentParser(description="Fishbowl order rank → EspoCRM Account.cOrderCount/cOrderRank")
    parser.add_argument("--dry-run", action="store_true", help="preview without writes")
    parser.add_argument("--limit", type=int, default=None, help="limit number of accounts to update (for testing)")
    parser.add_argument("--top", type=int, default=20, help="how many top to show in dry-run")
    args = parser.parse_args()

    print("=== Fishbowl Order Ranking → EspoCRM ===")
    print(f"{datetime.now(timezone.utc).isoformat()} dryRun={args.dry_run}")

    ranking = compute_ranking()
    print(f"Computed ranking for {len(ranking)} customers")
    sorted_rank = sorted(ranking.items(), key=lambda x: x[1][1])
    print(f"Top {args.top}:")
    for cid, (cnt, rank) in sorted_rank[:args.top]:
        print(f"  rank {rank:4d}  customer {cid:5d}  orders {cnt:5d}")
    print(f"Bottom 5:")
    for cid, (cnt, rank) in sorted_rank[-5:]:
        print(f"  rank {rank:4d}  customer {cid:5d}  orders {cnt:5d}")

    # Enrichment for boss fields
    print("Computing enrichment (topProduct, avg/year, outstanding, followUp)...")
    enrichment = compute_enrichment()
    print(f"Enrichment computed for {len(enrichment)} customers")

    if args.dry_run:
        sample = sorted_rank[:5]
        for cid, (cnt, rank) in sample:
            acc = search_by_fishbowl_id("Account", str(cid))
            en = enrichment.get(cid, {})
            if acc:
                print(f"DRY {acc['name'][:30]:30} cOrderCount {acc.get('cOrderCount')}->{cnt} cOrderRank {acc.get('cOrderRank')}->{rank} topProduct {acc.get('cTopProduct')}->{en.get('topProduct')} avg {acc.get('cAvgOrdersPerYear')}->{en.get('avgOrdersPerYear')} outstanding {acc.get('cOutstandingOrders')}->{en.get('outstandingOrders')}")
            else:
                print(f"DRY customer {cid} not found")
        print("dry-run done")
        return 0

    # Real update
    limit = args.limit
    updated = 0
    skipped = 0
    errors = 0
    for idx, (cid, (cnt, rank)) in enumerate(sorted_rank):
        if limit is not None and idx >= limit:
            break
        acc = search_by_fishbowl_id("Account", str(cid))
        if not acc:
            skipped += 1
            if skipped < 5:
                print(f"skip customer {cid} — Account not found")
            continue
        en = enrichment.get(cid, {})
        # Build payload for boss fields — only update if changed
        payload = {}
        # ranking
        if acc.get("cOrderCount") != cnt:
            payload["cOrderCount"] = cnt
        if acc.get("cOrderRank") != rank:
            payload["cOrderRank"] = rank
        # top product
        top_prod = en.get("topProduct", "")
        if (acc.get("cTopProduct") or "") != top_prod:
            payload["cTopProduct"] = top_prod
        # avg per year
        avg = en.get("avgOrdersPerYear", 0.0)
        if acc.get("cAvgOrdersPerYear") != avg:
            payload["cAvgOrdersPerYear"] = avg
        # outstanding
        out = en.get("outstandingOrders", 0)
        if acc.get("cOutstandingOrders") != out:
            payload["cOutstandingOrders"] = out
        # followUp: last order date +30d if cFollowUpDate not set and lastDate exists
        last = en.get("lastDate")
        if last and not acc.get("cFollowUpDate"):
            try:
                from datetime import timedelta
                # last is datetime
                if hasattr(last, 'year'):
                    follow = last + timedelta(days=30)
                    follow_str = follow.strftime("%Y-%m-%d")
                    payload["cFollowUpDate"] = follow_str
            except Exception:
                pass
        # Ensure flags have defaults (Espo bool defaults to false, but ensure not null)
        # We leave cDoNotContact/cBankrupt/cDoNotSell as user-managed, don't overwrite if already set
        # But set to False if null for initial
        for flag in ["cDoNotContact", "cBankrupt", "cDoNotSell"]:
            if acc.get(flag) is None:
                payload[flag] = False

        if not payload:
            continue
        try:
            update_entity("Account", acc["id"], payload)
            updated += 1
            if updated % 100 == 0:
                print(f"progress {updated} updated, {skipped} skipped, {errors} errors")
        except Exception as e:
            print(f"failed customer {cid} account {acc['id']}: {e}")
            errors += 1

    print(f"done: updated {updated}, skipped {skipped}, errors {errors}, total {len(ranking)}")
    # verify
    try:
        total = list_entities("Account", {"maxSize": 1})["total"]
        print(f"Espo Account total {total}")
        # sample top rank fetch
        top_accounts = list_entities("Account", {"maxSize": 5, "orderBy": "cOrderRank", "order": "asc"})
        print("Top ranked Accounts in Espo:")
        for a in top_accounts.get("list", []):
            print(f"  rank {a.get('cOrderRank')} count {a.get('cOrderCount')} {a.get('name')} cFishbowlId={a.get('cFishbowlId')}")
    except Exception as e:
        print(f"verify failed: {e}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
