"""
Fishbowl MySQL client — pure Python via mysql-connector-python.
All connections use env vars via src.config (never log secrets).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

from src.config import fishbowl

try:
    import mysql.connector  # type: ignore
    from mysql.connector import pooling  # type: ignore
except ImportError as e:
    mysql = None  # type: ignore
    pooling = None  # type: ignore
    _import_error = e
else:
    _import_error = None

_pool = None  # lazy pool


def _require_driver():
    if _import_error is not None:
        raise RuntimeError(
            "mysql-connector-python not installed. Run: /path/to/project/.venv/bin/pip install -r requirements.txt"
        ) from _import_error


def _conn_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "host": fishbowl.host,
        "port": fishbowl.port,
        "database": fishbowl.database,
        "user": fishbowl.user,
        "password": fishbowl.password,
        "connection_timeout": 10,
        "autocommit": True,
    }
    if fishbowl.ssl:
        # mysql-connector-python uses ssl_ca / ssl_verify_cert; for Fishbowl
        # a simple SSL enable without verification matches previous Node behavior.
        kwargs["ssl_disabled"] = False
    else:
        kwargs["ssl_disabled"] = True
    return kwargs


def get_pool(pool_size: int = 5):
    """Lazy MySQLConnectionPool — created on first call."""
    global _pool
    _require_driver()
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="fishbowl_pool",
            pool_size=pool_size,
            **_conn_kwargs(),
        )
    return _pool


@contextmanager
def get_connection() -> Generator[Any, None, None]:
    """
    Context-manager yielding a pooled MySQL connection.
    Example:
        with get_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT 1")
    """
    _require_driver()
    pool = get_pool()
    conn = pool.get_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_single_connection():
    """Direct single connection (no pool) — useful for testConnection."""
    _require_driver()
    return mysql.connector.connect(**_conn_kwargs())


def test_connection() -> bool:
    """Run SELECT 1 — returns True on success, raises on failure."""
    _require_driver()
    conn = get_single_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        row = cur.fetchone()
        cur.close()
        return row is not None and row[0] == 1
    finally:
        conn.close()


def fetch_all(query: str, params: tuple | dict | None = None) -> list[dict]:
    """Execute query and return list of dict rows (no PII logging)."""
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params or ())
        rows = cur.fetchall()
        cur.close()
        return rows


def fetch_one(query: str, params: tuple | dict | None = None) -> dict | None:
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params or ())
        row = cur.fetchone()
        cur.close()
        return row
