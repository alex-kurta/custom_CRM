#!/usr/bin/env python3
"""
Follow-up reminder system — sends digest emails with .ics calendar attachments.

Triggers:
  1. cFollowUpDate due/overdue
  2. cOutstandingOrders > 0 (aging orders)
  3. Stale accounts (no contact in X days)

Features:
  - Priority scoring (overdue days × order amount × staleness)
  - Batch limiting per salesperson (default: 10/day)
  - Dedup via cLastReminderSent field
  - .ics calendar attachments for Outlook
  - Dry-run mode for testing

Usage:
  python3 -m src.followup_reminders --dry-run
  python3 -m src.followup_reminders --limit 5
  python3 -m src.followup_reminders
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Any
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    load_dotenv()
except ImportError:
    pass

import requests

# --- Configuration ---
API_URL = os.environ.get("ESPOCRM_API_URL", "https://crm.example.com/api/v1").rstrip("/")
API_KEY = os.environ.get("ESPOCRM_API_KEY", "")

# SMTP config (from env)
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

# Test mode
TEST_EMAIL = os.environ.get("TEST_EMAIL", "")

# Reminder config
MAX_REMINDERS_PER_SALESREP = int(os.environ.get("MAX_REMINDERS_PER_SALESREP", "10"))
STALE_DAYS = int(os.environ.get("STALE_ACCOUNT_DAYS", "90"))
REMINDER_COOLDOWN_DAYS = int(os.environ.get("REMINDER_COOLDOWN_DAYS", "7"))
ADVANCE_WARNING_DAYS = int(os.environ.get("ADVANCE_WARNING_DAYS", "3"))
SITE_URL = os.environ.get("ESPOCRM_SITE_URL", "https://crm.example.com")

# Dry run
DRY_RUN = False


def api_get(endpoint: str, params: dict = None) -> dict:
    """GET request to EspoCRM API."""
    headers = {"X-Api-Key": API_KEY}
    resp = requests.get(f"{API_URL}/{endpoint}", headers=headers, params=params or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_put(endpoint: str, data: dict) -> dict:
    """PUT request to EspoCRM API."""
    headers = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}
    resp = requests.put(f"{API_URL}/{endpoint}", headers=headers, json=data, timeout=30)
    resp.raise_for_status()
    return resp.json() if resp.text else {}


def score_account(account: dict, now: datetime) -> float:
    """
    Priority score — higher = more urgent.
    Factors:
      - Follow-up overdue days (weighted heavily)
      - Outstanding order amount
      - Days since last contact (staleness)
      - Total order count
    """
    score = 0.0

    # 1. Follow-up date overdue
    followup_str = account.get("cFollowUpDate")
    if followup_str:
        try:
            followup_date = datetime.fromisoformat(followup_str.replace("Z", "+00:00"))
            overdue_days = (now - followup_date).days
            if overdue_days > 0:
                score += overdue_days * 10  # Heavy weight for overdue
            elif overdue_days >= -ADVANCE_WARNING_DAYS:
                score += (ADVANCE_WARNING_DAYS + overdue_days + 1) * 5  # approaching
        except (ValueError, TypeError):
            pass

    # 2. Outstanding orders
    outstanding = account.get("cOutstandingOrders", 0) or 0
    if outstanding > 0:
        score += outstanding * 2

    # 3. Total order amount (logarithmic scale)
    total = account.get("cTotalOrderAmount", 0) or 0
    if total > 0:
        import math
        score += math.log10(max(total, 1)) * 3

    # 4. Days since last contact
    last_contacted_str = account.get("cLastContacted")
    if last_contacted_str:
        try:
            last_contacted = datetime.fromisoformat(last_contacted_str.replace("Z", "+00:00"))
            days_since = (now - last_contacted).days
            if days_since > STALE_DAYS:
                score += (days_since - STALE_DAYS) * 0.5
        except (ValueError, TypeError):
            pass
    else:
        # Never contacted — high staleness
        score += 50

    return round(score, 2)


def generate_ics(account: dict, followup_date: str = None) -> str:
    """Generate .ics calendar event for follow-up."""
    name = account.get("name", "Unknown Account")
    account_id = account.get("id", "")
    total = account.get("cTotalOrderAmount", 0) or 0
    outstanding = account.get("cOutstandingOrders", 0) or 0

    # Determine event date
    if followup_date:
        try:
            event_date = datetime.fromisoformat(followup_date.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            event_date = datetime.now(timezone.utc) + timedelta(days=1)
    else:
        event_date = datetime.now(timezone.utc) + timedelta(days=1)

    # Format for .ics (UTC)
    dtstart = event_date.strftime("%Y%m%dT%H%M%SZ")
    dtend = (event_date + timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ")
    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"followup-{account_id}-{now_str}@crm.example.com"

    summary = f"Follow-up: {name}"
    description = (
        f"Follow-up needed for {name}\\n"
        f"Total Orders: ${total:,.2f}\\n"
        f"Outstanding Orders: {outstanding}\\n"
        f"\\n"
        f"View in CRM: {SITE_URL}/#Account/view/{account_id}"
    )

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//FishbowlEspo//FollowUpReminder//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:REQUEST\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART:{dtstart}\r\n"
        f"DTEND:{dtend}\r\n"
        f"DTSTAMP:{now_str}\r\n"
        f"UID:{uid}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{description}\r\n"
        f"LOCATION:{SITE_URL}/#Account/view/{account_id}\r\n"
        "STATUS:CONFIRMED\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-PT15M\r\n"
        "ACTION:DISPLAY\r\n"
        f"DESCRIPTION:Follow-up reminder: {name}\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return ics


def build_email_html(salesrep_name: str, accounts: list[dict], now: datetime) -> str:
    """Build HTML digest email body."""
    rows = ""
    for i, acct in enumerate(accounts, 1):
        name = acct.get("name", "Unknown")
        account_id = acct.get("id", "")
        total = acct.get("cTotalOrderAmount", 0) or 0
        outstanding = acct.get("cOutstandingOrders", 0) or 0
        followup = acct.get("cFollowUpDate", "N/A")
        score = acct.get("_score", 0)
        reason = acct.get("_reason", "")

        if followup and followup != "N/A":
            try:
                fd = datetime.fromisoformat(followup.replace("Z", "+00:00"))
                followup_display = fd.strftime("%b %d, %Y")
                overdue = (now - fd).days
                if overdue > 0:
                    followup_display += f' <span style="color:red">({overdue}d overdue)</span>'
            except (ValueError, TypeError):
                followup_display = followup
        else:
            followup_display = "N/A"

        link = f"{SITE_URL}/#Account/view/{account_id}"
        rows += f"""
        <tr style="border-bottom:1px solid #eee">
            <td style="padding:8px"><a href="{link}">{name}</a></td>
            <td style="padding:8px;text-align:right">${total:,.2f}</td>
            <td style="padding:8px;text-align:center">{outstanding}</td>
            <td style="padding:8px">{followup_display}</td>
            <td style="padding:8px;font-size:12px;color:#666">{reason}</td>
        </tr>"""

    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;font-size:14px">
        <h2 style="color:#333">Daily Follow-up Reminders</h2>
        <p>Hello {salesrep_name},</p>
        <p>You have <strong>{len(accounts)}</strong> accounts requiring follow-up:</p>

        <table style="width:100%;border-collapse:collapse;margin:16px 0">
            <thead>
                <tr style="background:#f5f5f5;border-bottom:2px solid #ddd">
                    <th style="padding:8px;text-align:left">Account</th>
                    <th style="padding:8px;text-align:right">Total Orders</th>
                    <th style="padding:8px;text-align:center">Outstanding</th>
                    <th style="padding:8px;text-align:left">Follow-up Date</th>
                    <th style="padding:8px;text-align:left">Reason</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>

        <p style="color:#666;font-size:12px">
            This is an automated reminder from the CRM integration.<br>
            Each account has a .ics calendar attachment — click to add to your Outlook calendar.
        </p>
    </body>
    </html>
    """
    return html


def send_email(to_addr: str, subject: str, html_body: str, ics_attachments: list[tuple[str, str]]) -> bool:
    """
    Send email with optional .ics attachments.
    ics_attachments: list of (filename, ics_content) tuples
    """
    if DRY_RUN:
        print(f"  [DRY RUN] Would send email to {to_addr}")
        print(f"  Subject: {subject}")
        print(f"  Attachments: {len(ics_attachments)} .ics files")
        return True

    if not SMTP_HOST or not SMTP_FROM:
        print(f"  [SKIP] SMTP not configured, cannot send to {to_addr}")
        return False

    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM
    msg["To"] = to_addr
    msg["Subject"] = subject

    # HTML body
    msg.attach(MIMEText(html_body, "html"))

    # .ics attachments
    for filename, ics_content in ics_attachments:
        part = MIMEBase("text", "calendar", method="REQUEST")
        part.set_payload(ics_content.encode("utf-8"))
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) if SMTP_PORT == 465 else smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_PORT != 465 and SMTP_USE_TLS:
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_addr], msg.as_string())
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to send to {to_addr}: {e}")
        return False


def get_salesrep_email(user_id: str) -> str:
    """Get salesperson email from EspoCRM User record."""
    try:
        user = api_get(f"User/{user_id}")
        email = user.get("emailAddress", "")
        if email:
            return email
        # Try email address list
        for ea in user.get("emailAddressList", []):
            if ea.get("emailAddress"):
                return ea["emailAddress"]
    except Exception:
        pass
    return ""


def run_reminders(limit: int = None):
    """Main reminder logic."""
    now = datetime.now(timezone.utc)
    print(f"=== Follow-up Reminders — {now.strftime('%Y-%m-%d %H:%M UTC')} ===")

    # Calculate cooldown threshold
    cooldown_cutoff = (now - timedelta(days=REMINDER_COOLDOWN_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    # 1. Fetch all accounts (where clauses have permission issues with API user)
    print("\n[1/4] Fetching accounts...")
    all_accounts = []
    offset = 0
    batch_size = 200  # API limit for this user
    try:
        while True:
            data = api_get("Account", {
                "maxSize": batch_size,
                "offset": offset
            })
            batch = data.get("list", [])
            all_accounts.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size
        print(f"  Fetched {len(all_accounts)} total accounts")
    except Exception as e:
        print(f"  Error fetching accounts: {e}")

    # 2. Filter to accounts that need reminders
    print("\n[2/4] Filtering accounts with triggers...")
    accounts_by_id = {}
    for acct in all_accounts:
        aid = acct["id"]
        reasons = []
        has_trigger = False

        # Check follow-up trigger
        followup_str = acct.get("cFollowUpDate")
        if followup_str:
            try:
                fd = datetime.fromisoformat(followup_str.replace("Z", "+00:00"))
                if fd <= now:
                    reasons.append(f"Follow-up overdue by {(now - fd).days}d")
                    has_trigger = True
                elif (fd - now).days <= ADVANCE_WARNING_DAYS:
                    reasons.append(f"Follow-up due in {(fd - now).days}d")
                    has_trigger = True
            except (ValueError, TypeError):
                pass

        # Check outstanding orders trigger
        if (acct.get("cOutstandingOrders") or 0) > 0:
            reasons.append(f"{acct['cOutstandingOrders']} outstanding orders")
            has_trigger = True

        # Check stale contact trigger
        last_contacted_str = acct.get("cLastContacted")
        if last_contacted_str:
            try:
                lc = datetime.fromisoformat(last_contacted_str.replace("Z", "+00:00"))
                days_since = (now - lc).days
                if days_since > STALE_DAYS:
                    reasons.append(f"No contact for {days_since}d")
                    has_trigger = True
            except (ValueError, TypeError):
                pass
        else:
            reasons.append("Never contacted")
            has_trigger = True

        if has_trigger:
            acct["_reason"] = "; ".join(reasons)
            accounts_by_id[aid] = acct

    print(f"  Found {len(accounts_by_id)} accounts with active triggers")

    # 3. Score accounts
    print("\n[3/4] Scoring accounts...")
    for aid, acct in accounts_by_id.items():
        acct["_score"] = score_account(acct, now)

    # Filter out unassigned accounts and admin users
    filtered = {}
    for aid, acct in accounts_by_id.items():
        uid = acct.get("assignedUserId")
        uname = (acct.get("assignedUserName") or "").strip()
        # Skip unassigned accounts
        if not uid:
            continue
        # Skip admin users
        if uname.lower() in ("admin", "administrator"):
            continue
        filtered[aid] = acct

    accounts_by_id = filtered
    print(f"  {len(accounts_by_id)} accounts after filtering (unassigned/admin removed)")

    # Filter out recently reminded accounts
    filtered = {}
    for aid, acct in accounts_by_id.items():
        last_reminder = acct.get("cLastReminderSent")
        if last_reminder:
            try:
                lr = datetime.fromisoformat(last_reminder.replace("Z", "+00:00"))
                if (now - lr).days < REMINDER_COOLDOWN_DAYS:
                    continue  # Skip — too recently reminded
            except (ValueError, TypeError):
                pass
        filtered[aid] = acct

    accounts_by_id = filtered
    print(f"  {len(accounts_by_id)} accounts after dedup and cooldown filter")

    # Sort by score descending
    sorted_accounts = sorted(accounts_by_id.values(), key=lambda a: a["_score"], reverse=True)

    # 4. Group by salesperson and send
    print("\n[4/4] Grouping by salesperson and sending...")
    by_salesrep = {}
    for acct in sorted_accounts:
        uid = acct.get("assignedUserId")
        uname = acct.get("assignedUserName", "Unassigned")
        if uid not in by_salesrep:
            by_salesrep[uid] = {"name": uname, "accounts": []}
        by_salesrep[uid]["accounts"].append(acct)

    total_sent = 0
    for uid, data in by_salesrep.items():
        name = data["name"]
        accts = data["accounts"][:MAX_REMINDERS_PER_SALESREP]  # Limit batch
        if not accts:
            continue

        print(f"\n  Salesperson: {name} ({len(accts)} accounts)")

        # Get email
        email = ""
        # Override with test email if set
        if TEST_EMAIL:
            email = TEST_EMAIL
            print(f"    [TEST] Using test email: {email}")
        elif uid:
            email = get_salesrep_email(uid)
        if not email:
            print(f"    [SKIP] No email address for {name}")
            continue

        # Build email
        subject = f"Follow-up Reminders: {len(accts)} accounts need attention — {now.strftime('%b %d')}"
        html = build_email_html(name, accts, now)

        # Generate .ics attachments
        ics_files = []
        for acct in accts:
            ics_name = f"followup-{acct.get('name', 'unknown').replace(' ', '_')}.ics"
            ics_content = generate_ics(acct, acct.get("cFollowUpDate"))
            ics_files.append((ics_name, ics_content))

        # Send
        if send_email(email, subject, html, ics_files):
            total_sent += len(accts)
            print(f"    Sent to {email} with {len(ics_files)} .ics attachments")

            # Update cLastReminderSent for each account
            if not DRY_RUN:
                for acct in accts:
                    try:
                        api_put(f"Account/{acct['id']}", {
                            "cLastReminderSent": now.strftime("%Y-%m-%d %H:%M:%S")
                        })
                    except Exception as e:
                        print(f"    [WARN] Failed to update cLastReminderSent for {acct.get('name')}: {e}")

    print(f"\n=== Done: {total_sent} reminders processed ===")
    return total_sent


def main():
    global DRY_RUN

    parser = argparse.ArgumentParser(description="Follow-up reminder system")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending emails")
    parser.add_argument("--limit", type=int, default=None, help="Max accounts per salesperson")
    parser.add_argument("--max-per-rep", type=int, default=None, help="Override MAX_REMINDERS_PER_SALESREP")
    parser.add_argument("--test-email", type=str, default=None, help="Send all emails to this address instead")
    args = parser.parse_args()

    DRY_RUN = args.dry_run
    if args.max_per_rep:
        global MAX_REMINDERS_PER_SALESREP
        MAX_REMINDERS_PER_SALESREP = args.max_per_rep
    if args.test_email:
        global TEST_EMAIL
        TEST_EMAIL = args.test_email

    if not API_KEY:
        print("ERROR: ESPOCRM_API_KEY not set")
        sys.exit(1)

    print(f"Config: MAX_REMINDERS_PER_SALESREP={MAX_REMINDERS_PER_SALESREP}")
    print(f"Config: STALE_DAYS={STALE_DAYS}, REMINDER_COOLDOWN_DAYS={REMINDER_COOLDOWN_DAYS}")
    print(f"Config: ADVANCE_WARNING_DAYS={ADVANCE_WARNING_DAYS}")
    print(f"Config: SMTP_HOST={SMTP_HOST or '(not set)'}")
    print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")

    run_reminders(limit=args.limit)


if __name__ == "__main__":
    main()
