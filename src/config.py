"""
config.py — user-scoped config (theme, currency, ticker rules, ISIN mappings).

Config stored per-user in data/users/<user_id>/config.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import storage

DEFAULTS: dict = {
    "default_currency": "PLN",
    "ticker_rules": [],
    "isin_tickers": [],
    "theme": "dark",
    "log_scale": False,
}


def _save_file(path: Path, data: dict) -> None:
    """Atomically persist JSON config (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


_config_cache: dict[str, dict] = {}  # user_id -> config


def _get_user_id() -> str:
    """Get current user_id, raise if not authenticated."""
    from storage.context import get_current_user
    user_id = get_current_user()
    if not user_id:
        raise RuntimeError("No authenticated user")
    return user_id


def load() -> dict:
    """Return the current user's config."""
    user_id = _get_user_id()
    if user_id in _config_cache:
        return _config_cache[user_id]

    cfg = storage.load_config()
    # Fill missing keys from defaults
    changed = False
    for k, v in DEFAULTS.items():
        if k not in cfg:
            cfg[k] = v
            changed = True
    if changed:
        storage.save_config(cfg)
    _config_cache[user_id] = cfg
    return cfg


def invalidate_config_cache(user_id: str | None = None) -> None:
    """Clear the in-memory config cache for a user (or all if None)."""
    if user_id is None:
        _config_cache.clear()
    else:
        _config_cache.pop(user_id, None)


def save(cfg: dict) -> None:
    """Save config to current user's config file."""
    storage.save_config(cfg)
    invalidate_config_cache()


def get_theme(cfg: dict) -> str:
    return cfg.get("theme", "dark")


def save_theme(theme: str) -> None:
    cfg = load()
    cfg["theme"] = theme
    save(cfg)


def get_log_scale(cfg: dict) -> bool:
    return bool(cfg.get("log_scale", False))


def save_log_scale(log_scale: bool) -> None:
    cfg = load()
    cfg["log_scale"] = bool(log_scale)
    save(cfg)