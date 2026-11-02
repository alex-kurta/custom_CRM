"""
EspoCRM REST client — uses requests + X-Api-Key.
Prefers API for audit trails (AGENTS.md §7), never direct DB writes.

Base URL: ESPOCRM_API_URL (default https://crm.example.com/api/v1)
Auth: header X-Api-Key: ESPOCRM_API_KEY
"""

from __future__ import annotations

import json
from typing import Any

import requests

from src.config import espocrm

TIMEOUT = 15  # seconds


def _headers(extra: dict | None = None) -> dict[str, str]:
    h: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if espocrm.api_key:
        h["X-Api-Key"] = espocrm.api_key
    if extra:
        h.update(extra)
    return h


def _url(path: str) -> str:
    base = espocrm.api_url.rstrip("/")
    path = "/" + path.lstrip("/")
    return base + path


def check_connection() -> dict[str, Any]:
    """
    Probe EspoCRM liveness.
    GET /api/v1/Settings — 200 with API key, 401 without, but still 'live'.
    Returns {ok, status, data, version}
    Mirrors Node behavior: 401 = live but unauthenticated.
    """
    url = _url("/Settings")
    try:
        resp = requests.get(url, headers=_headers(), timeout=TIMEOUT)
        data = None
        try:
            data = resp.json()
        except Exception:
            data = resp.text[:500]
        version = None
        if isinstance(data, dict):
            version = data.get("version") or data.get("appVersion")
        ok = 200 <= resp.status_code < 300
        return {
            "ok": ok,
            "status": resp.status_code,
            "data": data,
            "version": version,
            "url": url,
        }
    except requests.exceptions.RequestException as e:
        return {"ok": False, "status": 0, "data": str(e)[:500], "version": None, "url": url}


def list_entities(entity: str, params: dict | None = None) -> dict[str, Any]:
    """GET /{entity}?maxSize=...&offset=..."""
    url = _url(f"/{entity}")
    resp = requests.get(url, headers=_headers(), params=params or {}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_entity(entity: str, entity_id: str) -> dict[str, Any]:
    url = _url(f"/{entity}/{entity_id}")
    resp = requests.get(url, headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def create_entity(entity: str, data: dict[str, Any]) -> dict[str, Any]:
    url = _url(f"/{entity}")
    resp = requests.post(url, headers=_headers(), data=json.dumps(data), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def update_entity(entity: str, entity_id: str, data: dict[str, Any]) -> dict[str, Any]:
    url = _url(f"/{entity}/{entity_id}")
    resp = requests.put(url, headers=_headers(), data=json.dumps(data), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def search_by_fishbowl_id(entity: str, fishbowl_id: Any) -> dict[str, Any] | None:
    """
    Search EspoCRM for entity with custom field cFishbowlId == fishbowl_id.
    Discovered via /Metadata: Account {cFishbowlId,cFishbowlLastModified}, Opportunity {cFishbowlId}
    Fallback to fishbowlId for backward compat if cFishbowlId search 400s.
    """
    # Primary: cFishbowlId (EspoCRM 10+ with prefix c)
    for attr in ("cFishbowlId", "fishbowlId"):
        params = {
            "where[0][type]": "equals",
            "where[0][attribute]": attr,
            "where[0][value]": str(fishbowl_id),
            "maxSize": 1,
        }
        try:
            result = list_entities(entity, params=params)
            lst = result.get("list") or []
            if lst:
                return lst[0]
            return None
        except requests.HTTPError as e:
            # If field doesn't exist, API returns 400 — try next attr
            if e.response is not None and e.response.status_code == 400:
                continue
            raise
    return None


def upsert_entity(entity: str, fishbowl_id: Any, data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """
    Idempotent upsert by fishbowlId:
      - Search by fishbowlId
      - If found: PUT /{entity}/{id}
      - Else: POST /{entity}
    Returns (entity_data, created: bool)
    data should already include fishbowlId and fishbowlLastModified.
    """
    existing = search_by_fishbowl_id(entity, fishbowl_id)
    if existing and existing.get("id"):
        updated = update_entity(entity, existing["id"], data)
        return updated, False
    # Ensure cFishbowlId in payload (primary), keep fishbowlId alias for fallback
    payload = dict(data)
    if "cFishbowlId" not in payload:
        payload["cFishbowlId"] = str(fishbowl_id)
    if "fishbowlId" not in payload:
        payload["fishbowlId"] = str(fishbowl_id)
    created = create_entity(entity, payload)
    return created, True
