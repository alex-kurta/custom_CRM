#!/usr/bin/env python3
"""
Import Fishbowl contacts -> Espo Contact (under Customers)
Source: contact (datus, contactName, typeId) + customercontactview
Target: Contact with accountId, email/phone, cFishbowlId

typeId: 50=phone, 60=email (from observed)
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import requests
from src.config import espocrm
from src.fishbowl.client import fetch_all
from src.espocrm.client import search_by_fishbowl_id

def _normalize_phone(raw: str) -> str | None:
    """Fishbowl datus phone -> Espo E.164. Espo validates phoneNumber, requires +country."""
    if not raw:
        return None
    s = raw.strip()
    # Remove common separators
    # If already in E.164, keep
    if s.startswith("+"):
        # keep but remove spaces/dashes
        cleaned = "+" + "".join(ch for ch in s if ch.isdigit())
        if len(cleaned) >= 8:
            return cleaned
        return None
    # Remove all non-digits
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None
    # Heuristic: French "33 1 ..." -> 10-11 digits starting with 33
    # US: 10 digits -> +1, 11 digits starting with 1 -> +1...
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if len(digits) >= 10 and digits.startswith("33"):
        return "+" + digits
    if len(digits) >= 7:
        # Fallback: assume US
        if len(digits) == 10:
            return "+1" + digits
        return "+" + digits
    return None

def contact_to_payload(contact, account_id):
    name = (contact.get("contactName") or "").strip()
    parts = name.split()
    if len(parts) >= 2:
        first = " ".join(parts[:-1])
        last = parts[-1]
    elif len(parts) == 1:
        first = ""
        last = parts[0]
    else:
        first = ""
        last = "Unknown"
    datus = (contact.get("datus") or "").strip()
    payload = {
        "firstName": first[:100],
        "lastName": last[:100] or "Contact",
        "cFishbowlId": str(contact["id"]),
        "accountId": account_id,
    }
    if "@" in datus:
        payload["emailAddress"] = datus[:100]
    elif datus:
        norm = _normalize_phone(datus)
        if norm:
            payload["phoneNumber"] = norm
        else:
            # Fallback: put raw in description if not valid phone
            payload["description"] = f"Phone (raw): {datus}"
    return payload

def upsert_contact(payload):
    fid = payload["cFishbowlId"]
    # search Contact by cFishbowlId
    url = f"{espocrm.api_url.rstrip('/')}/Contact"
    h = {"X-Api-Key": espocrm.api_key, "Content-Type":"application/json"}
    params = {"where[0][type]":"equals","where[0][attribute]":"cFishbowlId","where[0][value]": fid, "maxSize":1}
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
    args = parser.parse_args()
    print(f"=== Contact bulk import dryRun={args.dry_run} limit={args.limit} ===")
    # Build account map
    from src.espocrm.client import list_entities
    # Use search_by_fishbowl_id for each contact's accountId
    rows = fetch_all("SELECT * FROM contact ORDER BY id ASC")
    print(f"Fishbowl contacts {len(rows)}")
    # Also check distinct customers with contacts
    total = 0
    created = 0
    updated = 0
    skipped = 0
    for idx, contact in enumerate(rows):
        if args.limit and total >= args.limit:
            break
        # skip empty datus? Keep but maybe skip Unknown with empty
        if not contact.get("datus") and contact.get("contactName") in ("Unknown", ""):
            skipped += 1
            continue
        account_fishbowl_id = str(contact["accountId"])
        # find Espo Account
        acc = search_by_fishbowl_id("Account", account_fishbowl_id)
        if not acc:
            skipped += 1
            if skipped < 5:
                print(f"skip contact {contact['id']} - Account {account_fishbowl_id} not found in Espo")
            continue
        payload = contact_to_payload(contact, acc["id"])
        if args.dry_run:
            print(f"DRY Contact {contact['id']} {payload['firstName']} {payload['lastName']} -> {payload.get('emailAddress') or payload.get('phoneNumber')} account {acc['name'][:30]}")
            total += 1
            continue
        try:
            res, is_created = upsert_contact(payload)
            if is_created: created += 1
            else: updated += 1
            total += 1
            if total % 100 == 0:
                print(f"progress {total} created {created} updated {updated} skipped {skipped}")
        except Exception as e:
            print(f"fail contact {contact['id']}: {e}")
            skipped += 1
    print(f"done: total {total} created {created} updated {updated} skipped {skipped}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
