#!/usr/bin/env python3
"""
Past-Due Excel Import — parses accounting Excel files and updates EspoCRM Accounts.

Usage:
  python3 -m src.past_due_import /path/to/past-due-invoices.xlsx
  python3 -m src.past_due_import /path/to/file.xlsx --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

BASE_URL = os.environ.get("ESPOCRM_API_URL", "https://crm.example.com/api/v1")
API_KEY = os.environ.get("ESPOCRM_API_KEY", "")
HEADERS = {"X-Api-Key": API_KEY}

DATE_PATTERNS = [
    r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*,?\s*(\d{4})\b",
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})\s*(?:st|nd|rd|th)?\s*,?\s*(\d{4})\b",
    r"\b(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?[- ](\d{4})\b",
    r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
    r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b",
]

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_filename_date(filename: str) -> str | None:
    """Extract YYYY-MM-DD from a filename like 'Past due invoices January 1, 2025.xlsx'."""
    if not filename:
        return None
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, filename, re.IGNORECASE)
        if not m:
            continue
        groups = m.groups()
        if groups[0].isalpha() or groups[1].isalpha():
            if groups[0].isalpha():
                month_name, day, year = MONTHS[groups[0][:3].lower()], int(groups[1]), int(groups[2])
            else:
                day, month_name, year = int(groups[0]), MONTHS[groups[1][:3].lower()], int(groups[2])
        else:
            a, b, c = int(groups[0]), int(groups[1]), int(groups[2])
            if a > 31:
                year, month_name, day = a, b, c
            else:
                month_name, day, year = a, b, c
        try:
            return datetime(year, month_name, day).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_xlsx(filepath: str) -> list[dict]:
    """Parse Excel: col B=customer, col C=SO#, col D=order_date, col E=due_date, col F=aging, col G=amount, col H=balance"""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active

    records = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        if not row or all(cell is None for cell in row):
            continue

        customer = row[1] if len(row) > 1 else None
        so_num = row[2] if len(row) > 2 else None
        order_date = row[3] if len(row) > 3 else None
        due_date = row[4] if len(row) > 4 else None
        aging = row[5] if len(row) > 5 else None
        amount = row[6] if len(row) > 6 else None
        balance = row[7] if len(row) > 7 else None

        if not so_num and not customer:
            continue

        if order_date and hasattr(order_date, "strftime"):
            order_date = order_date.strftime("%Y-%m-%d")
        elif order_date:
            order_date = str(order_date)

        if due_date and hasattr(due_date, "strftime"):
            due_date = due_date.strftime("%Y-%m-%d")
        elif due_date:
            due_date = str(due_date)

        try:
            amount = float(amount) if amount else 0.0
        except (ValueError, TypeError):
            amount = 0.0
        try:
            balance = float(balance) if balance else 0.0
        except (ValueError, TypeError):
            balance = 0.0

        try:
            aging_int = int(float(aging)) if aging else 0
        except (ValueError, TypeError):
            aging_int = 0

        records.append({
            "customer": str(customer).strip() if customer else "",
            "so_num": str(so_num).strip() if so_num else "",
            "order_date": str(order_date) if order_date else "",
            "due_date": str(due_date) if due_date else "",
            "aging": aging_int,
            "amount": amount,
            "balance": balance,
        })

    wb.close()
    return records


def lookup_account_by_so(so_num: str) -> dict | None:
    """Look up CSalesOrder by fishbowlNum, then get the linked Account."""
    try:
        r = requests.get(
            f"{BASE_URL}/CSalesOrder",
            headers=HEADERS,
            params={
                "where[0][type]": "equals",
                "where[0][attribute]": "fishbowlNum",
                "where[0][value]": so_num,
                "select": "id,account,accountId",
                "maxSize": 1,
            },
        )
        d = r.json()
        if d.get("list"):
            so = d["list"][0]
            account_id = so.get("accountId") or so.get("account", {}).get("id")
            if account_id:
                r2 = requests.get(
                    f"{BASE_URL}/Account/{account_id}",
                    headers=HEADERS,
                    params={"select": "id,name,cFishbowlId,cPastDue,cPastDueData,cPastDueAmount,cDaysOverdue"},
                )
                return r2.json()
    except Exception as e:
        print(f"  lookup by SO# {so_num} failed: {e}")
    return None


def lookup_account_by_name(name: str) -> dict | None:
    """Fallback: look up Account by name (case-insensitive search)."""
    try:
        r = requests.get(
            f"{BASE_URL}/Account",
            headers=HEADERS,
            params={
                "q": name,
                "select": "id,name,cFishbowlId,cPastDue,cPastDueData,cPastDueAmount,cDaysOverdue",
                "maxSize": 5,
            },
        )
        d = r.json()
        for a in d.get("list", []):
            if (a.get("name") or "").strip().lower() == name.strip().lower():
                return a
        if d.get("list"):
            return d["list"][0]
    except Exception as e:
        print(f"  lookup by name '{name}' failed: {e}")
    return None


def update_account(account: dict, orders: list[dict], days_since_file: int, dry_run: bool = False) -> bool:
    """Update an Account with past-due data.

    Days Overdue = max(aging per order) + days elapsed since filename date
    """
    account_id = account.get("id")
    account_name = account.get("name", "")

    total_balance = sum(o["balance"] for o in orders)

    max_aging = 0
    for o in orders:
        aging = o["aging"]
        if aging > max_aging:
            max_aging = aging

    days_overdue = max_aging + days_since_file

    payload = {
        "cPastDue": True,
        "cDaysOverdue": days_overdue,
        "cPastDueAmount": round(total_balance, 2),
        "cPastDueAmountCurrency": "USD",
        "cPastDueData": json.dumps(orders),
    }

    if dry_run:
        print(f"  DRY-RUN: {account_name} ({account_id}) — {len(orders)} orders, ${total_balance:.2f}, max_aging={max_aging}, days_overdue={days_overdue}")
        return True

    try:
        r = requests.put(
            f"{BASE_URL}/Account/{account_id}",
            headers=HEADERS,
            json=payload,
        )
        if r.status_code in (200, 204):
            return True
        else:
            print(f"  FAILED: {account_name} — {r.status_code} {r.text[:200]}")
            return False
    except Exception as e:
        print(f"  FAILED: {account_name} — {e}")
        return False


def clear_past_due(dry_run: bool = False) -> int:
    """Clear cPastDue on all accounts that currently have it set."""
    try:
        r = requests.get(
            f"{BASE_URL}/Account",
            headers=HEADERS,
            params={
                "where[0][type]": "equals",
                "where[0][attribute]": "cPastDue",
                "where[0][value]": "true",
                "select": "id,name",
                "maxSize": 500,
            },
        )
        d = r.json()
        accounts = d.get("list", [])
        cleared = 0
        for a in accounts:
            if dry_run:
                print(f"  DRY-RUN clear: {a.get('name')}")
                cleared += 1
                continue
            try:
                requests.put(
                    f"{BASE_URL}/Account/{a['id']}",
                    headers=HEADERS,
                    json={"cPastDue": False, "cPastDueData": None, "cPastDueAmount": None, "cDaysOverdue": 0},
                )
                cleared += 1
            except Exception:
                pass
        return cleared
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import past-due Excel into EspoCRM")
    parser.add_argument("file", help="Path to past-due Excel file (.xlsx)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writes")
    args = parser.parse_args()

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        return 1

    if not filepath.suffix.lower() == ".xlsx":
        print(f"ERROR: Expected .xlsx file, got {filepath.suffix}")
        return 1

    filename_date = parse_filename_date(filepath.name)
    if not filename_date:
        print(f"WARNING: Could not extract date from filename '{filepath.name}', using today")
        filename_date = datetime.now().strftime("%Y-%m-%d")

    # Days elapsed since filename date (in PST)
    pst = ZoneInfo("America/Los_Angeles")
    today_pst = datetime.now(pst).date()
    filename_dt = datetime.strptime(filename_date, "%Y-%m-%d").date()
    days_since_file = (today_pst - filename_dt).days

    print(f"=== Past-Due Excel Import ===")
    print(f"File: {filepath.name}")
    print(f"Filename date: {filename_date}")
    print(f"Today (PST): {today_pst.isoformat()}")
    print(f"Days elapsed: {days_since_file}")
    print(f"Dry run: {args.dry_run}")

    print(f"\nParsing Excel...")
    records = parse_xlsx(str(filepath))
    print(f"Found {len(records)} past-due orders")

    if not records:
        print("No records found, exiting")
        return 0

    print(f"\nLooking up accounts...")
    account_orders: dict[str, dict] = {}
    unmatched = []

    for rec in records:
        so_num = rec["so_num"]
        account = None

        if so_num:
            account = lookup_account_by_so(so_num)

        if not account and rec["customer"]:
            account = lookup_account_by_name(rec["customer"])

        if account:
            aid = account["id"]
            if aid not in account_orders:
                account_orders[aid] = {"account": account, "orders": []}
            account_orders[aid]["orders"].append(rec)
        else:
            unmatched.append(rec)

    print(f"Matched {len(account_orders)} accounts, {len(unmatched)} unmatched orders")

    if unmatched:
        print(f"\nUnmatched orders (first 10):")
        for rec in unmatched[:10]:
            print(f"  SO#{rec['so_num']} — {rec['customer']}")

    print(f"\nClearing existing past-due flags...")
    cleared = clear_past_due(dry_run=args.dry_run)
    print(f"Cleared {cleared} accounts")

    print(f"\nUpdating accounts...")
    updated = 0
    failed = 0
    for aid, data in account_orders.items():
        if update_account(data["account"], data["orders"], days_since_file, dry_run=args.dry_run):
            updated += 1
        else:
            failed += 1

    print(f"\n=== Summary ===")
    print(f"Orders imported: {len(records)}")
    print(f"Accounts updated: {updated}")
    print(f"Failed: {failed}")
    print(f"Unmatched orders: {len(unmatched)}")
    print(f"Filename date: {filename_date}, days elapsed: {days_since_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
