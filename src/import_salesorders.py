#!/usr/bin/env python3
"""
Bulk import sales_order -> CSalesOrder + soitem -> CSalesOrderItem
Idempotent via fishbowlId, paginated 500, with account linkage.

Usage:
  .venv/bin/python -m src.import_salesorders --dry-run --limit 5
  .venv/bin/python -m src.import_salesorders --limit 1000
  .venv/bin/python -m src.import_salesorders
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
import requests
from src.config import espocrm
from src.fishbowl.client import fetch_all, fetch_one
from src.espocrm.client import search_by_fishbowl_id

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MAP_PATH = DATA_DIR / "map.json"

# Map sostatus id -> status string for CSalesOrder
SOSTATUS = {10:"Estimate",20:"Issued",25:"In Progress",60:"Fulfilled",85:"Cancelled",80:"Voided",70:"Closed Short",90:"Expired",95:"Historical"}

def load_account_map():
    # Build customerId -> accountId from Espo via search or from map.json
    # Use map.json for speed, fallback to API
    try:
        data = json.loads(MAP_PATH.read_text())
        return {k: v for k,v in data.get("Account",{}).items()}
    except Exception:
        return {}

def format_dt(dt):
    if not dt:
        return None
    if hasattr(dt, 'strftime'):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    s = str(dt).replace("T"," ").split(".")[0][:19]
    return s

def _fmt_qty(q):
    try:
        # q is Decimal
        f = float(q or 0)
        if f.is_integer():
            return str(int(f))
        # otherwise keep one decimal if needed
        return str(int(f)) if f == int(f) else str(f).rstrip("0").rstrip(".")
    except:
        return str(q)

def _product_name(soitem):
    # Prefer soitem.description (actual name at order time), fallback to part.description via productNum
    desc = (soitem.get("description") or "").strip()
    if desc and desc != soitem.get("productNum"):
        return desc
    # Fallback: lookup part
    try:
        # Use cached part map if available
        return _part_cache.get(soitem.get("productNum"), soitem.get("productNum"))
    except:
        return soitem.get("productNum")

_part_cache = {}
def _load_part_cache():
    try:
        rows = fetch_all("SELECT num, description FROM part")
        for r in rows:
            _part_cache[r["num"]] = r["description"] or r["num"]
    except:
        pass
_load_part_cache()

def so_to_payload(so, account_id, item_summary=None):
    status = SOSTATUS.get(int(so.get("statusId") or 0), "In Progress")
    payload = {
        "name": f"SO {so['num']}",
        "fishbowlId": str(so["id"]),
        "fishbowlNum": so["num"],
        "customerId": str(so["customerId"]),
        "amount": float(so["totalPrice"] or 0),
        "amountCurrency": "USD",
        "status": status,
        "orderDate": format_dt(so.get("dateCreated") or so.get("dateIssued")),
        "accountId": account_id
    }
    if item_summary:
        payload["itemSummary"] = item_summary[:4000]
    return payload

def upsert_salesorder(payload):
    fid = payload["fishbowlId"]
    # search CSalesOrder by fishbowlId
    # Use direct search via API (search_by_fishbowl_id works for CSalesOrder? It searches fishbowlId attribute, but for CSalesOrder field is fishbowlId without prefix)
    # Our search_by_fishbowl_id searches cFishbowlId first then fishbowlId, but for CSalesOrder it's fishbowlId
    # So we need custom search for CSalesOrder
    url = f"{espocrm.api_url.rstrip('/')}/CSalesOrder"
    h = {"X-Api-Key": espocrm.api_key, "Content-Type":"application/json"}
    params = {"where[0][type]":"equals","where[0][attribute]":"fishbowlId","where[0][value]": fid, "maxSize":1}
    r = requests.get(url, headers=h, params=params, timeout=15)
    r.raise_for_status()
    lst = r.json().get("list",[])
    if lst:
        eid = lst[0]["id"]
        # update
        ru = requests.put(f"{url}/{eid}", headers=h, data=json.dumps(payload), timeout=15)
        ru.raise_for_status()
        return ru.json(), False
    else:
        rc = requests.post(url, headers=h, data=json.dumps(payload), timeout=15)
        rc.raise_for_status()
        return rc.json(), True

def upsert_item(payload):
    fid = payload["fishbowlId"]
    url = f"{espocrm.api_url.rstrip('/')}/CSalesOrderItem"
    h = {"X-Api-Key": espocrm.api_key, "Content-Type":"application/json"}
    params = {"where[0][type]":"equals","where[0][attribute]":"fishbowlId","where[0][value]": fid, "maxSize":1}
    r = requests.get(url, headers=h, params=params, timeout=15)
    r.raise_for_status()
    lst = r.json().get("list",[])
    if lst:
        eid = lst[0]["id"]
        ru = requests.put(f"{url}/{eid}", headers=h, data=json.dumps(payload), timeout=15)
        ru.raise_for_status()
        return ru.json(), False
    else:
        rc = requests.post(url, headers=h, data=json.dumps(payload), timeout=15)
        rc.raise_for_status()
        return rc.json(), True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    print(f"=== CSalesOrder bulk import dryRun={args.dry_run} limit={args.limit} offset={args.offset} ===")
    account_map = load_account_map()
    print(f"loaded account_map {len(account_map)} entries")
    # For missing mappings, fallback to API search cache
    batch = 500
    offset = args.offset
    total_imported = 0
    total_created = 0
    total_updated = 0
    total_items = 0
    while True:
        if args.limit and total_imported >= args.limit:
            break
        cur_batch = batch
        if args.limit:
            cur_batch = min(batch, args.limit - total_imported)
        rows = fetch_all(f"SELECT * FROM `so` ORDER BY id ASC LIMIT %s OFFSET %s", (cur_batch, offset))
        if not rows:
            print(f"no more rows at offset {offset}")
            break
        offset += len(rows)
        for so in rows:
            fid = str(so["id"])
            cid = str(so["customerId"])
            # account lookup
            account_id = account_map.get(cid)
            if not account_id:
                # fallback API
                acc = search_by_fishbowl_id("Account", cid)
                if acc:
                    account_id = acc["id"]
                    account_map[cid] = account_id
            # import items first to build summary
            items = fetch_all("SELECT * FROM soitem WHERE soId=%s", (so["id"],))
            summary_parts = []
            for it in items:
                prod_name = _product_name(it)
                qty_str = _fmt_qty(it["qtyOrdered"])
                summary_parts.append(f"{prod_name} x{qty_str}")
            item_summary = "; ".join(summary_parts)[:4000] if summary_parts else None
            payload = so_to_payload(so, account_id, item_summary)
            if args.dry_run:
                print(f"DRY SO {so['num']} id={fid} -> {payload['name']} amount {payload['amount']} account {account_id} summary {item_summary[:80] if item_summary else ''}")
                total_imported += 1
                continue
            try:
                res, created = upsert_salesorder(payload)
                if created: total_created += 1
                else: total_updated += 1
                total_imported += 1
                for it in items:
                    prod_name = _product_name(it)
                    qty_str = _fmt_qty(it["qtyOrdered"])
                    qty_f = float(it["qtyOrdered"] or 0)
                    qty_ful = float(it["qtyFulfilled"] or 0)
                    ipayload = {
                        "name": f"{prod_name} x{qty_str}",
                        "fishbowlId": str(it["id"]),
                        "fishbowlSoId": str(it["soId"]),
                        "productNum": it["productNum"],
                        "qtyOrdered": qty_f,
                        "qtyFulfilled": qty_ful,
                        "totalPrice": float(it["totalPrice"] or 0),
                        "totalPriceCurrency": "USD",
                        "salesOrderId": res["id"]
                    }
                    try:
                        upsert_item(ipayload)
                        total_items += 1
                    except Exception as e:
                        print(f" item fail {it['id']}: {e}")
                if total_imported % 100 == 0:
                    print(f"progress {total_imported} (created {total_created} updated {total_updated}) items {total_items}")
            except Exception as e:
                print(f"SO fail {fid}: {e}")
                if "409" in str(e):
                    # try to find existing and update with name suffix?
                    print(f"  409 conflict for SO {fid}, maybe duplicate name")
        if len(rows) < cur_batch:
            break
    print(f"done: imported {total_imported} (created {total_created} updated {total_updated}) items {total_items}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
