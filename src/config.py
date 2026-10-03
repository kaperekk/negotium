"""
config.py — configuration with global defaults and per-user overrides.

Global defaults:  data/config.json
User config:      data/users/<username>/config.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from storage.context import get_user_root

ROOT = Path(__file__).parent.parent

GLOBAL_CONFIG_PATH = ROOT / "data" / "config.json"

DEFAULTS: dict = {
    "default_currency": "PLN",
    "ticker_rules": [],
    "isin_tickers": [],
    "theme": "dark",
    "log_scale": False,
}


def _load_global() -> dict:
    """Load global default config."""
    if not GLOBAL_CONFIG_PATH.exists():
        _save_file(GLOBAL_CONFIG_PATH, DEFAULTS.copy())
        return DEFAULTS.copy()
    try:
        with GLOBAL_CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        backup = GLOBAL_CONFIG_PATH.with_suffix(".json.corrupt")
        logging.getLogger(__name__).warning(
            "config.json unreadable (%s) — backed up to %s, using defaults",
            exc, backup.name,
        )
        try:
            GLOBAL_CONFIG_PATH.replace(backup)
        except OSError:
            pass
        _save_file(GLOBAL_CONFIG_PATH, DEFAULTS.copy())
        return DEFAULTS.copy()


def _user_config_path(user: str | None = None) -> Path:
    """Get the config path for a specific user."""
    return get_user_root(user) / "config.json"


def _load_user(user: str | None = None) -> dict:
    """Load user-specific config."""
    path = _user_config_path(user)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logging.getLogger(__name__).warning(
            "User config unreadable (%s) — using defaults", exc
        )
        return {}


def _save_file(path: Path, data: dict) -> None:
    """Atomically persist JSON config (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


_config_cache: dict | None = None
_config_user: str | None = None


def load(user: str | None = None) -> dict:
    """Return config merged from global defaults and user overrides."""
    global _config_cache, _config_user

    # Resolve user if not provided
    if user is None:
        from storage.context import get_current_user
        user = get_current_user()

    if _config_cache is not None and _config_user == user:
        return _config_cache

    # Start with global defaults
    cfg = _load_global()
    # Apply user overrides
    user_cfg = _load_user(user)
    cfg = {**cfg, **user_cfg}

    # Fill missing keys from DEFAULTS
    changed = False
    for k, v in DEFAULTS.items():
        if k not in cfg:
            cfg[k] = v
            changed = True
    if changed:
        # Save merged config back to user config if it's missing keys
        if user_cfg:
            _save_file(_user_config_path(user), cfg)

    _config_cache = cfg
    _config_user = user
    return cfg


def invalidate_config_cache() -> None:
    """Clear the in-memory config cache (call after save)."""
    global _config_cache, _config_user
    _config_cache = None
    _config_user = None


def save(cfg: dict, user: str | None = None) -> None:
    """Save config to user-specific config file."""
    _save_file(_user_config_path(user), cfg)
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