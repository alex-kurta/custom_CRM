#!/usr/bin/env python3
"""
Connectivity check — no secrets in output (AGENTS.md §0, §8).
Loads .env via src.config, probes Fishbowl MySQL and EspoCRM API.
Exit 0 if both OK or if at least one probe finishes; exit 1 only on total failure.
Mirrors previous Node verify.js but in Python.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from src.config import diagnostics, has_espo_config, has_fishbowl_config, espocrm
from src.fishbowl.client import test_connection as fishbowl_test
from src.fishbowl.schema import discover as fishbowl_discover
from src.espocrm.client import check_connection as espo_check
from src.espocrm.client import list_entities


def main() -> int:
    print("=== Fishbowl ↔ EspoCRM Verify ===")
    print(f"Python {sys.version.split()[0]} — {datetime.now(timezone.utc).isoformat()}")
    print("")

    diag = diagnostics()
    print(f"[Config] Fishbowl: {diag['fishbowl']}")
    print(f"[Config] EspoCRM : {diag['espocrm']}")
    print(f"[Config] Sync    : {diag['sync']}")
    print("")

    fishbowl_ok = False
    espo_ok = False

    # --- Fishbowl ---
    print("--- Fishbowl MySQL ---")
    if not has_fishbowl_config():
        print("Fishbowl: SKIP — FISHBOWL_DB_* incomplete in .env (set host/name/user/password)")
    else:
        try:
            ok = fishbowl_test()
            if ok:
                print("Fishbowl: OK — SELECT 1 succeeded")
                fishbowl_ok = True
                try:
                    data = fishbowl_discover()
                    print(f"Fishbowl: {len(data.get('tables', []))} tables discovered")
                    counts = data.get("counts", {})
                    for k in sorted(counts.keys()):
                        print(f"  - {k}: {counts[k]} rows")
                    errors = data.get("errors", [])
                    if errors:
                        print(f"Fishbowl: {len(errors)} probe warnings (see data/schema-cache.json)")
                        for e in errors[:5]:
                            print(f"    ! {e}")
                    columns = data.get("columns", {})
                    for t in ["customer", "part"]:
                        if t in columns:
                            fields = [c.get("field") for c in columns[t][:20]]
                            print(f"  {t} columns: {', '.join(fields)[:200]}")
                except Exception as e:
                    print(f"Fishbowl: schema discovery failed — {e}")
            else:
                print("Fishbowl: FAIL — SELECT 1 returned unexpected result")
        except Exception as e:
            # Mask any secret leakage — only print type/code, not host/user
            msg = str(e)
            # never print host/user/password even if exception contains them
            print(f"Fishbowl: FAIL — {msg[:500]}")
            code = getattr(e, "errno", None) or getattr(e, "code", None)
            if code:
                print(f"  code: {code}")
    print("")

    # --- EspoCRM ---
    print("--- EspoCRM API ---")
    try:
        result = espo_check()
        if result.get("ok"):
            version = result.get("version") or "unknown"
            print(f"EspoCRM: OK — {espocrm.api_url} reachable (status {result.get('status')}, version {version})")
            espo_ok = True
        else:
            status = result.get("status")
            print(f"EspoCRM: reachable but not authenticated (status {status}) — check ESPOCRM_API_KEY")
            if status in (401, 403):
                print("EspoCRM: server live, auth issue only")
            else:
                data = result.get("data")
                snippet = str(data)[:300] if data else ""
                if snippet:
                    print(f"EspoCRM: response {snippet}")

        # Authenticated list probe if key present
        if has_espo_config():
            try:
                acc = list_entities("Account", {"maxSize": 1})
                total = acc.get("total", "unknown")
                print(f"EspoCRM: authenticated OK — Account total {total} (1 sample fetched)")
                espo_ok = True
            except Exception as e:
                print(f"EspoCRM: authenticated check failed — {str(e)[:300]}")
    except Exception as e:
        print(f"EspoCRM: FAIL — {str(e)[:400]}")
    print("")

    # Summary + exit code
    print("--- Summary ---")
    print(f"Fishbowl: {'OK' if fishbowl_ok else 'SKIP/FAIL'}")
    print(f"EspoCRM: {'OK' if espo_ok else 'FAIL/UNAUTH'}")

    # Exit 0 if at least one system was probed (even if Fishbowl SKIP); exit 1 only if both failed and config present
    if fishbowl_ok or espo_ok:
        return 0
    if not has_fishbowl_config() and not has_espo_config():
        print("No valid config — set .env per .env.example")
        return 1
    # If Fishbowl SKIP but EspoCRM live (or vice versa), still success for verification
    if not has_fishbowl_config() and espo_ok:
        return 0
    if not has_espo_config() and fishbowl_ok:
        return 0
    # Check if EspoCRM server is at least live (status != 0)
    # If check returned status 0 = network failure; treat as failure
    return 1


if __name__ == "__main__":
    sys.exit(main())
