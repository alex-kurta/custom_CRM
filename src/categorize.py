#!/usr/bin/env python3
"""
Categorize EspoCRM accounts into industry categories.

The classifier algorithm is generic. All supplier/competitor domains,
category keywords, and name rules live in a local config file that is
intentionally not tracked by the repository:

    data/categorize-config.json

Override the path with CATEGORIZE_CONFIG=/path/to/config.json.

Required config keys:
    distributor_domains, supplier_domains, pharma_domains, cro_domains,
    personal_domains, priority, category_keywords, name_rules

Categories (Account.cCategory enum):
    Distributor, University, Small Biotech, Government, CRO,
    Cancer Research, Stem Cell, Neuroscience, Pharmaceutical,
    Molecular Genomics, Hospital, Other

Classification pipeline (fast -> slow):
    1. Deterministic domain rules (TLD + configured domains)
    2. Account name keyword matching
    3. OSINT (website fetch + DuckDuckGo search) keyword scoring

Usage:
    python3 -m src.categorize --phase1                # rules + name only (fast)
    python3 -m src.categorize --osint --limit 50       # OSINT on leftovers, 50 at a time
    python3 -m src.categorize --apply                  # write all state results to EspoCRM
    python3 -m src.categorize --phase1 --apply         # classify + write in one pass
    python3 -m src.categorize --single example.com     # test one domain
    python3 -m src.categorize --stats                  # show current distribution
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests not installed: pip install requests")
    sys.exit(1)

from src.config import espocrm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CATEGORIES = [
    "Distributor", "University", "Small Biotech", "Government", "CRO",
    "Cancer Research", "Stem Cell", "Neuroscience", "Pharmaceutical",
    "Molecular Genomics", "Hospital", "Other",
]

STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "categorize-state.json"

_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "data" / "categorize-config.json"
CONFIG_PATH = Path(os.environ.get("CATEGORIZE_CONFIG", _DEFAULT_CONFIG))

_REQUIRED_KEYS = (
    "distributor_domains",
    "supplier_domains",
    "pharma_domains",
    "cro_domains",
    "personal_domains",
    "priority",
    "category_keywords",
    "name_rules",
)


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        print(f"Missing local categorizer config: {CONFIG_PATH}", file=sys.stderr)
        print(
            "Create it locally; it is intentionally not tracked in the repo. "
            "See README.md for the expected keys.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    missing = [key for key in _REQUIRED_KEYS if key not in cfg]
    if missing:
        print(f"Invalid categorizer config; missing keys: {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(1)
    return cfg


CONFIG = load_config()

PERSONAL_DOMAINS = set(CONFIG["personal_domains"])
DISTRIBUTOR_DOMAINS = set(CONFIG["distributor_domains"])
SUPPLIER_DOMAINS = set(CONFIG["supplier_domains"])
PHARMA_DOMAINS = set(CONFIG["pharma_domains"])
CRO_DOMAINS = set(CONFIG["cro_domains"])
PRIORITY = CONFIG["priority"]
CATEGORY_KEYWORDS = CONFIG["category_keywords"]
NAME_RULES = CONFIG["name_rules"]


# ---------------------------------------------------------------------------
# Deterministic classification (no network)
# ---------------------------------------------------------------------------

def classify_by_domain(domain: str) -> str | None:
    """Fast domain rules. Returns category or None."""
    if not domain or domain in PERSONAL_DOMAINS:
        return None
    domain = domain.lower().strip(".")

    for known in DISTRIBUTOR_DOMAINS:
        if domain == known or domain.endswith("." + known):
            return "Distributor"
    for known in PHARMA_DOMAINS:
        if domain == known or domain.endswith("." + known):
            return "Pharmaceutical"
    for known in CRO_DOMAINS:
        if domain == known or domain.endswith("." + known):
            return "CRO"

    if domain.endswith(".gov") or domain.endswith(".mil") or ".gov." in domain or ".mil." in domain:
        return "Government"
    if domain.endswith(".edu") or ".edu." in domain:
        return "University"

    return None


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def classify_by_name(name: str) -> str | None:
    """Fast account-name rules. Returns category or None."""
    if not name:
        return None
    n = name.lower()

    if _matches(NAME_RULES.get("government", []), n):
        return "Government"
    if _matches(NAME_RULES.get("distributor", []), n):
        return "Distributor"
    if _matches(NAME_RULES.get("hospital", []), n):
        return "Hospital"

    cancer_place = NAME_RULES.get("focus_cancer_place", "")
    if _matches(NAME_RULES.get("focus_cancer", []), n) and (
        not cancer_place or re.search(cancer_place, n)
    ):
        return "Cancer Research"
    if _matches(NAME_RULES.get("focus_stem", []), n):
        return "Stem Cell"
    neuro_place = NAME_RULES.get("focus_neuro_place", "")
    if _matches(NAME_RULES.get("focus_neuro", []), n) and (
        not neuro_place or re.search(neuro_place, n)
    ):
        return "Neuroscience"

    if _matches(NAME_RULES.get("cro", []), n):
        return "CRO"
    if _matches(NAME_RULES.get("pharma", []), n):
        return "Pharmaceutical"
    if _matches(NAME_RULES.get("molecular", []), n):
        return "Molecular Genomics"
    if _matches(NAME_RULES.get("university", []), n):
        return "University"
    if _matches(NAME_RULES.get("focus_biotech", []), n):
        return "Small Biotech"

    return None


# ---------------------------------------------------------------------------
# OSINT scoring
# ---------------------------------------------------------------------------

def fetch_page_text(url: str, timeout: int = 10) -> str:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; categorize-bot/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        }
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        text = re.sub(r"<script[^>]*>.*?</script>", "", resp.text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text[:15000]
    except Exception:
        return ""


def score_category(text: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        total = 0.0
        for pattern, weight in keywords:
            matches = len(re.findall(pattern, text_lower))
            total += matches * weight
        scores[category] = total
    return scores


def web_search_snippets(query: str, max_results: int = 5) -> list[str]:
    """Web search snippets. Prefers ddgs package, falls back to DDG HTML scrape."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)
        snippets = []
        for r in results or []:
            body = r.get("body") or r.get("description") or ""
            title = r.get("title") or ""
            if body or title:
                snippets.append(f"{title} {body}".strip())
        if snippets:
            return snippets
    except ImportError:
        pass
    except Exception:
        pass

    try:
        search_url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; categorize-bot/1.0)"}
        resp = requests.get(search_url, headers=headers, timeout=10)
        if resp.ok:
            raw = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
            return [re.sub(r"<[^>]+>", "", s) for s in raw[:max_results]]
    except Exception:
        pass
    return []


def classify_osint(domain: str, name: str = "") -> dict:
    """Full OSINT classification for one domain. Returns result dict."""
    result = {
        "domain": domain,
        "category": "Other",
        "scores": {},
        "evidence": "",
        "method": "osint",
    }

    det = classify_by_domain(domain)
    if det and domain not in SUPPLIER_DOMAINS:
        result["category"] = det
        result["method"] = "domain-rule"
        result["evidence"] = f"Domain rule: {domain} -> {det}"
        return result

    domain_unusable = (not domain) or domain in PERSONAL_DOMAINS or domain in SUPPLIER_DOMAINS
    if domain_unusable and not name.strip():
        result["evidence"] = f"Unusable domain ({domain}), no name"
        result["method"] = "skip"
        return result

    all_text = name + " "

    fetchable = not domain_unusable
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    if fetchable:
        urls = []
        if tld in ("edu", "ac", "gov"):
            urls.append(f"https://{domain}")
        else:
            urls.append(f"https://www.{domain}")
            urls.append(f"https://{domain}")
        for url in urls:
            text = fetch_page_text(url)
            if text:
                all_text += " " + text
                break

    query = f"{name} company" if (name.strip() and domain_unusable) else f"{domain} company"
    try:
        for snippet in web_search_snippets(query, max_results=5):
            all_text += " " + snippet
    except Exception:
        pass

    if not all_text.strip():
        result["evidence"] = f"No web content for {domain}"
        return result

    scores = score_category(all_text)

    if tld == "edu":
        scores["University"] = scores.get("University", 0) + 50.0
    if tld in ("gov", "mil"):
        scores["Government"] = scores.get("Government", 0) + 50.0

    result["scores"] = {k: round(v, 1) for k, v in scores.items() if v > 0}

    ranked = sorted(
        ((cat, sc) for cat, sc in scores.items() if sc > 0),
        key=lambda x: (-x[1], PRIORITY.get(x[0], 99)),
    )
    if ranked:
        result["category"] = ranked[0][0]
        top = ranked[0]
        evidence_parts = []
        for pattern, weight in CATEGORY_KEYWORDS.get(top[0], []):
            m = re.findall(pattern, all_text.lower())
            if m:
                evidence_parts.append(f"{pattern[:30]}: {len(m)}x")
        result["evidence"] = f"{top[0]} ({top[1]:.0f}pts) | " + ", ".join(evidence_parts[:5])
    else:
        result["category"] = "Other"
        result["evidence"] = "No keyword matches"

    return result


# ---------------------------------------------------------------------------
# State management (resume support)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"results": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1))


# ---------------------------------------------------------------------------
# EspoCRM integration
# ---------------------------------------------------------------------------

def _espo_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if espocrm.api_key:
        headers["X-Api-Key"] = espocrm.api_key
    return headers


def fetch_accounts_with_state() -> list[dict]:
    """Fetch all accounts: id, name, emailAddress, cCategory."""
    api_url = espocrm.api_url
    headers = _espo_headers()
    accounts = []
    offset = 0
    while True:
        r = requests.get(
            f"{api_url}/Account",
            headers=headers,
            params={"maxSize": 200, "offset": offset, "select": "id,name,emailAddress,cCategory"},
            timeout=30,
        )
        r.raise_for_status()
        d = r.json()
        accounts.extend(d.get("list", []))
        offset += 200
        if offset >= d.get("total", 0):
            break
    return accounts


def extract_work_domain(account: dict) -> str:
    em = account.get("emailAddress") or ""
    if "@" in em:
        dom = em.split("@", 1)[1].lower().strip(".")
        if dom not in PERSONAL_DOMAINS:
            return dom
    return ""


def apply_category(account_id: str, category: str) -> bool:
    api_url = espocrm.api_url
    r = requests.put(
        f"{api_url}/Account/{account_id}",
        headers=_espo_headers(),
        json={"cCategory": category},
        timeout=15,
    )
    return r.ok


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_phase1(accounts: list[dict], state: dict, apply: bool) -> None:
    """Deterministic rules only — no network. Fast."""
    results = state["results"]
    stats: dict[str, int] = {}
    new_count = 0
    for acc in accounts:
        aid = acc["id"]
        if aid in results and results[aid].get("category"):
            continue
        name = acc.get("name") or ""
        domain = extract_work_domain(acc)

        cat = None
        method = None
        cat = classify_by_name(name)
        method = "name-rule" if cat else None
        if not cat and domain:
            if domain in SUPPLIER_DOMAINS and name.strip():
                pass
            else:
                cat = classify_by_domain(domain)
                method = "domain-rule" if cat else None

        if cat:
            results[aid] = {
                "name": name, "domain": domain,
                "category": cat, "method": method,
            }
            stats[cat] = stats.get(cat, 0) + 1
            new_count += 1
            if apply:
                ok = apply_category(aid, cat)
                if not ok:
                    print(f"  API FAIL: {name} -> {cat}")
                time.sleep(0.05)

    save_state(state)
    print(f"Phase 1: classified {new_count} new accounts")
    for cat in CATEGORIES:
        if stats.get(cat):
            print(f"  {cat}: {stats[cat]}")


def cmd_osint(accounts: list[dict], state: dict, apply: bool, limit: int, delay: float) -> None:
    """OSINT on accounts not yet classified (domain or name based)."""
    results = state["results"]
    pending = [
        a for a in accounts
        if a["id"] not in results and (extract_work_domain(a) or (a.get("name") or "").strip())
    ]
    if limit:
        pending = pending[:limit]

    print(f"OSINT pending: {len(pending)} accounts (limit {limit or 'none'})")
    done = 0
    for acc in pending:
        aid = acc["id"]
        name = acc.get("name") or ""
        domain = extract_work_domain(acc)
        if not domain and not name.strip():
            continue

        res = classify_osint(domain, name)
        results[aid] = {
            "name": name, "domain": domain,
            "category": res["category"],
            "method": res["method"],
            "evidence": res.get("evidence", ""),
            "scores": res.get("scores", {}),
        }
        done += 1
        print(f"  [{done}/{len(pending)}] {name} ({domain}) -> {res['category']} | {res.get('evidence','')[:80]}")

        if apply:
            ok = apply_category(aid, res["category"])
            if not ok:
                print("    API FAIL")
            time.sleep(0.05)

        if done % 10 == 0:
            save_state(state)
        time.sleep(delay)

    save_state(state)
    print(f"OSINT done: {done} accounts processed")


def cmd_apply_state(accounts: list[dict], state: dict) -> None:
    """Push every state result to EspoCRM (skips records already matching)."""
    results = state["results"]
    current = {a["id"]: a.get("cCategory") for a in accounts}
    todo = [
        (aid, r) for aid, r in results.items()
        if r.get("category") and current.get(aid) != r["category"]
    ]
    print(f"Apply: {len(todo)} to write, "
          f"{len(results) - len(todo)} already in sync / no category")
    ok = fail = 0
    for i, (aid, r) in enumerate(todo, 1):
        if apply_category(aid, r["category"]):
            ok += 1
        else:
            fail += 1
            print(f"  API FAIL: {r.get('name')} -> {r['category']}")
        if i % 50 == 0:
            print(f"  [{i}/{len(todo)}]")
        time.sleep(0.05)
    print(f"Apply done: {ok} written, {fail} failed")


def cmd_stats(accounts: list[dict], state: dict) -> None:
    results = state["results"]
    by_cat: dict[str, int] = {}
    applied = 0
    for acc in accounts:
        cur = acc.get("cCategory")
        if cur:
            by_cat[cur] = by_cat.get(cur, 0) + 1
            applied += 1
    print(f"Applied in EspoCRM: {applied} / {len(accounts)}")
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {n}")

    pending = sum(1 for a in accounts if a["id"] not in results and extract_work_domain(a))
    print(f"State results: {len(results)}, still pending OSINT: {pending}")


def cmd_single(domain: str) -> None:
    domain = domain.strip().lower()
    if "@" in domain:
        domain = domain.split("@")[1]
    print(f"Classifying: {domain}")
    res = classify_osint(domain)
    print(f"  Category: {res['category']}")
    print(f"  Method:   {res['method']}")
    print(f"  Evidence: {res.get('evidence', '')}")
    if res.get("scores"):
        print(f"  Scores:   {res['scores']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Categorize accounts into industry categories")
    parser.add_argument("--phase1", action="store_true", help="Deterministic rules only (fast, no network)")
    parser.add_argument("--osint", action="store_true", help="OSINT web lookup for unclassified accounts")
    parser.add_argument("--apply", action="store_true", help="Write results to EspoCRM")
    parser.add_argument("--limit", type=int, default=0, help="Max accounts for OSINT run")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between OSINT requests")
    parser.add_argument("--stats", action="store_true", help="Show categorization stats")
    parser.add_argument("--single", metavar="DOMAIN", help="Classify a single domain")
    parser.add_argument("--reset", action="store_true", help="Clear state file")
    args = parser.parse_args()

    if args.reset:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
            print("State cleared")
        return 0

    if args.single:
        cmd_single(args.single)
        return 0

    accounts = fetch_accounts_with_state()
    state = load_state()

    if args.stats:
        cmd_stats(accounts, state)
        return 0

    if args.apply and not (args.phase1 or args.osint):
        cmd_apply_state(accounts, state)
        return 0

    if args.phase1:
        cmd_phase1(accounts, state, args.apply)
        return 0

    if args.osint:
        cmd_osint(accounts, state, args.apply, args.limit, args.delay)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
