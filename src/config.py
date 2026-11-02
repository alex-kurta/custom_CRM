"""
Config loader — never logs secrets.
Loads .env via python-dotenv and exports validated config.
Per AGENTS.md §0: NEVER read .env as file, only via os.environ.

Usage:
    from src.config import fishbowl, espocrm, sync, has_fishbowl_config, has_espo_config, diagnostics

Env schema (see .env.example):
    FISHBOWL_DB_HOST / PORT / NAME / USER / PASSWORD / SSL
    ESPOCRM_API_URL / ESPOCRM_API_KEY / ESPOCRM_ADMIN_USERNAME / PASSWORD
    SYNC_INTERVAL_MINUTES / SYNC_BATCH_SIZE
"""

import os
import sys
from dataclasses import dataclass

# Load .env if present — never log values
try:
    from dotenv import load_dotenv

    # load_dotenv searches cwd and parents; explicit path to working dir
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    load_dotenv()  # fallback to default search
except ImportError:
    # dotenv not installed — will rely on shell env
    pass


def _optional(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _required(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


@dataclass(frozen=True)
class _FishbowlConfig:
    @property
    def host(self) -> str:
        return _optional("FISHBOWL_DB_HOST", "")

    @property
    def port(self) -> int:
        try:
            return int(_optional("FISHBOWL_DB_PORT", "3306"))
        except ValueError:
            return 3306

    @property
    def database(self) -> str:
        return _optional("FISHBOWL_DB_NAME", "")

    @property
    def user(self) -> str:
        return _optional("FISHBOWL_DB_USER", "")

    @property
    def password(self) -> str:
        return _optional("FISHBOWL_DB_PASSWORD", "")

    @property
    def ssl(self) -> bool:
        return _optional("FISHBOWL_DB_SSL", "false").lower() == "true"


@dataclass(frozen=True)
class _EspoConfig:
    @property
    def api_url(self) -> str:
        return _optional("ESPOCRM_API_URL", "https://crm.example.com/api/v1").rstrip("/")

    @property
    def api_key(self) -> str:
        return _optional("ESPOCRM_API_KEY", "")

    @property
    def admin_username(self) -> str:
        return _optional("ESPOCRM_ADMIN_USERNAME", "admin")

    @property
    def admin_password(self) -> str:
        return _optional("ESPOCRM_ADMIN_PASSWORD", "")


@dataclass(frozen=True)
class _SyncConfig:
    @property
    def interval_minutes(self) -> int:
        try:
            return int(_optional("SYNC_INTERVAL_MINUTES", "30"))
        except ValueError:
            return 30

    @property
    def batch_size(self) -> int:
        try:
            return int(_optional("SYNC_BATCH_SIZE", "500"))
        except ValueError:
            return 500

    @property
    def dry_run(self) -> bool:
        return "--dry-run" in sys.argv


fishbowl = _FishbowlConfig()
espocrm = _EspoConfig()
sync = _SyncConfig()


def has_fishbowl_config() -> bool:
    return bool(fishbowl.host and fishbowl.database and fishbowl.user and fishbowl.password)


def has_espo_config() -> bool:
    return bool(espocrm.api_url and espocrm.api_key)


def diagnostics() -> dict:
    """Safe diagnostics — never expose secrets, only presence/boolean."""
    return {
        "fishbowl": {
            "hostSet": bool(fishbowl.host),
            "port": fishbowl.port,
            "databaseSet": bool(fishbowl.database),
            "userSet": bool(fishbowl.user),
            "passwordSet": bool(fishbowl.password),
            "ssl": fishbowl.ssl,
        },
        "espocrm": {
            "apiUrl": espocrm.api_url,
            "apiKeySet": bool(espocrm.api_key),
            "adminUsernameSet": bool(espocrm.admin_username),
        },
        "sync": {
            "intervalMinutes": sync.interval_minutes,
            "batchSize": sync.batch_size,
        },
    }
