#!/usr/bin/env python3
"""
Check Account names in EspoCRM for truncation / casing / abbreviation issues.
Reads ESPOCRM_API_KEY from .env via src.config (dotenv).
GET /api/v1/Account?maxSize=200 (API key limited to 200 per page)
"""

from __future__ import annotations

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import espocrm
from src.espocrm.client import list_entities

# ---------------------------------------------------------------------------
# Heuristics — only flag TRULY problematic names
# ---------------------------------------------------------------------------
# Normal business suffixes — do NOT flag these
NORMAL_SUFFIXES = re.compile(
    r"(?:,\s*(?:Inc|LLC|Ltd|Corp|Co|Lab|LLP|PLC|GmbH|SA|AG|BV|NV|Pty|Pte|SAS|SARL|SL)\.?)\s*$",
    re.IGNORECASE,
)

# Truncated / abbreviated words (not normal suffixes)
TRUNCATED_WORDS = re.compile(
    r"\b(univ|dept|inst|assn|assoc|ctr|bldg|ste|natl|intl|chem|bio|tech|pharm|med|res|sci|eng|math|phys|psych|surg|path|dent|nurs|physio|anat|micro|immun|genet|molec|cell|neuro|oncol|hemat|cardio|endo|pulm|renal|hepato|derm|ophth|radio|oncol|pediat|ob\/gyn|anesthes|emerg|intens|radiol|lab|diag|therap|vaccin|diagn|biotech)\.?\b",
    re.IGNORECASE,
)


def is_lower_only(name: str) -> bool:
    letters = [c for c in name if c.isalpha()]
    return bool(letters) and all(c.islower() for c in letters)


def classify(name: str) -> list[str]:
    issues: list[str] = []
    stripped = name.strip()
    if not stripped:
        issues.append("EMPTY")
        return issues

    # Numeric-only name
    if stripped.replace("-", "").replace(" ", "").isdigit():
        issues.append("NUMERIC-ONLY")

    # All lowercase
    if is_lower_only(stripped) and len(stripped) > 2:
        issues.append("ALL-LOWERCASE")

    # Lowercase first letter (proper noun expected)
    if stripped and stripped[0].islower() and not stripped.startswith(("UC", "UW")):
        issues.append("lowercase-start")

    # Very short (under 8 chars) — likely truncated or abbreviated
    if len(stripped) < 8:
        issues.append(f"very-short({len(stripped)}chars)")

    # Truncated words — e.g. "university of ill", "wayne sta"
    # Check for patterns: word at end is 1-4 chars after "of "
    m = re.search(r"\bof\s+([A-Z][a-z]{0,3})$", stripped)
    if m:
        issues.append(f"truncated-state('of {m.group(1)}')")

    # Truncated university/institute names
    if re.search(r"\b(University of|Univ of|Inst of|Inst for)\s+\w{1,5}$", stripped, re.IGNORECASE):
        issues.append("truncated-institution")

    # Backslash or weird chars
    if '\\' in stripped or '/' in stripped and '\\' in stripped:
        issues.append("contains-backslash")

    return issues


def main() -> None:
    if not espocrm.api_key:
        print("ERROR: ESPOCRM_API_KEY not set.")
        sys.exit(1)

    print(f"EspoCRM API: {espocrm.api_url}\n")

    # Fetch all accounts (paginate with maxSize=200)
    all_records: list[dict] = []
    offset = 0
    page_size = 200
    while True:
        result = list_entities("Account", params={"maxSize": page_size, "offset": offset})
        batch = result.get("list", [])
        all_records.extend(batch)
        total = result.get("total", None)
        print(f"  Fetched {len(all_records)} / {total}", end="\r")
        if len(batch) < page_size:
            break
        offset += page_size
    print()

    total = len(all_records)
    print(f"\n{'='*70}")
    print(f"TOTAL ACCOUNTS: {total}")
    print(f"{'='*70}\n")

    # Sort alphabetically by name (case-insensitive)
    all_records.sort(key=lambda r: (r.get("name") or "").lower())

    # Classify all
    problematic: list[tuple[str, str, list[str]]] = []
    for rec in all_records:
        name = rec.get("name", "")
        fb_id = rec.get("cFishbowlId") or rec.get("fishbowlId") or ""
        issues = classify(name)
        if issues:
            problematic.append((name, fb_id, issues))

    # --- Problematic names ---
    print(f"PROBLEMATIC NAMES: {len(problematic)} / {total}\n")
    for name, fb_id, issues in problematic:
        print(f"  [{fb_id}] {name!r}  -->  {', '.join(issues)}")

    # --- First 20 ---
    print(f"\n{'='*70}")
    print("FIRST 20 (alphabetical)")
    print(f"{'='*70}")
    for i, rec in enumerate(all_records[:20], 1):
        name = rec.get("name", "(no name)")
        fb_id = rec.get("cFishbowlId") or rec.get("fishbowlId") or ""
        print(f"  {i:3d}. [{fb_id}] {name}")

    # --- Last 20 ---
    print(f"\n{'='*70}")
    print("LAST 20 (alphabetical)")
    print(f"{'='*70}")
    start = max(0, total - 20)
    for i, rec in enumerate(all_records[start:], start + 1):
        name = rec.get("name", "(no name)")
        fb_id = rec.get("cFishbowlId") or rec.get("fishbowlId") or ""
        print(f"  {i:3d}. [{fb_id}] {name}")

    # --- Full alphabetical list ---
    print(f"\n{'='*70}")
    print(f"FULL LIST ({total} accounts, alphabetical)")
    print(f"{'='*70}")
    for i, rec in enumerate(all_records, 1):
        name = rec.get("name", "(no name)")
        fb_id = rec.get("cFishbowlId") or rec.get("fishbowlId") or ""
        print(f"  {i:4d}. [{fb_id}] {name}")


if __name__ == "__main__":
    main()
