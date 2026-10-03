"""
config.py — configuration with global defaults and per-user overrides.

Global defaults:  data/config.json (committed to git)
User config:      data/users/<username>/config.json (in storage/R2)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from storage.context import get_current_user
from storage.backends import get_backend

ROOT = Path(__file__).parent.parent
LOCAL_GLOBAL_CONFIG = ROOT / "data" / "config.json"

DEFAULTS: dict = {
    "default_currency": "PLN",
    "ticker_rules": [],
    "isin_tickers": [],
    "theme": "dark",
    "log_scale": False,
}

GLOBAL_CONFIG_KEY = "config.json"


def _load_global() -> dict:
    """Load global default config from local file (git) or storage."""
    # Try local file first (committed defaults)
    if LOCAL_GLOBAL_CONFIG.exists():
        try:
            with LOCAL_GLOBAL_CONFIG.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logging.getLogger(__name__).warning(
                "Local config.json unreadable (%s)", exc
            )

    # Fallback to storage (R2 or local backend)
    backend = get_backend()
    if backend.exists(GLOBAL_CONFIG_KEY):
        try:
            data = backend.read_bytes(GLOBAL_CONFIG_KEY)
            return json.loads(data)
        except (json.JSONDecodeError, OSError) as exc:
            logging.getLogger(__name__).warning(
                "Remote config.json unreadable (%s)", exc
            )

    # Final fallback to DEFAULTS
    return DEFAULTS.copy()


def _save_global(data: dict) -> None:
    """Save global config to storage (not local file)."""
    backend = get_backend()
    backend.write_bytes(GLOBAL_CONFIG_KEY, json.dumps(data, indent=2, ensure_ascii=False).encode())


def _user_config_key(user: str | None = None) -> str:
    """Get the config storage key for a specific user."""
    user = user or get_current_user()
    return f"users/{user}/config.json"


def _load_user(user: str | None = None) -> dict:
    """Load user-specific config from storage."""
    key = _user_config_key(user)
    backend = get_backend()
    if not backend.exists(key):
        return {}
    try:
        data = backend.read_bytes(key)
        return json.loads(data)
    except (json.JSONDecodeError, OSError) as exc:
        logging.getLogger(__name__).warning(
            "User config unreadable (%s) — using defaults", exc
        )
        return {}


def _save_user(user: str | None, data: dict) -> None:
    """Save user config to storage."""
    key = _user_config_key(user)
    backend = get_backend()
    backend.write_bytes(key, json.dumps(data, indent=2, ensure_ascii=False).encode())


def _ensure_user_config(user: str | None = None) -> dict:
    """Ensure user config exists, creating from global if needed."""
    user_cfg = _load_user(user)
    if user_cfg:
        return user_cfg

    # Create user config from global
    global_cfg = _load_global()
    _save_user(user, global_cfg.copy())
    return global_cfg.copy()


_config_cache: dict | None = None
_config_user: str | None = None


def load(user: str | None = None) -> dict:
    """Return config merged from global defaults and user overrides."""
    global _config_cache, _config_user

    if user is None:
        user = get_current_user()

    if _config_cache is not None and _config_user == user:
        return _config_cache

    # Load global config (from local file or storage)
    cfg = _load_global()

    # Ensure user config exists (create from global if not)
    user_cfg = _ensure_user_config(user)

    # Merge: global + user overrides
    cfg = {**cfg, **user_cfg}

    # Fill missing keys from DEFAULTS
    changed = False
    for k, v in DEFAULTS.items():
        if k not in cfg:
            cfg[k] = v
            changed = True

    _config_cache = cfg
    _config_user = user
    return cfg


def invalidate_config_cache() -> None:
    """Clear the in-memory config cache (call after save)."""
    global _config_cache, _config_user
    _config_cache = None
    _config_user = None


def save(cfg: dict, user: str | None = None) -> None:
    """Save config to user-specific config file in storage."""
    _save_user(user, cfg)
    invalidate_config_cache()


def get_theme(cfg: dict) -> str:
    return cfg.get("theme", "dark")


def save_theme(theme: str, user: str | None = None) -> None:
    cfg = load(user)
    cfg["theme"] = theme
    save(cfg, user)


def get_log_scale(cfg: dict) -> bool:
    return bool(cfg.get("log_scale", False))


def save_log_scale(log_scale: bool, user: str | None = None) -> None:
    cfg = load(user)
    cfg["log_scale"] = bool(log_scale)
    save(cfg, user)