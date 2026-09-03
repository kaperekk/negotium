"""
config.py — single global config shared by all projects

Global config:  data/config.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

ROOT = Path(__file__).parent.parent

GLOBAL_CONFIG_PATH = ROOT / "data" / "config.json"

DEFAULTS: dict = {
    "default_currency": "PLN",
    "ticker_rules": [],
    "isin_tickers": [],
    "theme": "dark",
}


def _load_global() -> dict:
    if not GLOBAL_CONFIG_PATH.exists():
        _save_file(GLOBAL_CONFIG_PATH, DEFAULTS.copy())
        return DEFAULTS.copy()
    try:
        with GLOBAL_CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        # Corrupt/unreadable config: keep the broken file for inspection
        # and start from defaults instead of crashing every launch.
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


def _save_file(path: Path, data: dict) -> None:
    """Atomically persist JSON config (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


_config_cache: dict | None = None


def load() -> dict:
    """Return the single global config shared by all projects."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    cfg = _load_global()
    # Fill missing keys from defaults
    changed = False
    for k, v in DEFAULTS.items():
        if k not in cfg:
            cfg[k] = v
            changed = True
    if changed:
        _save_file(GLOBAL_CONFIG_PATH, cfg)
    _config_cache = cfg
    return cfg


def invalidate_config_cache() -> None:
    """Clear the in-memory config cache (call after save)."""
    global _config_cache
    _config_cache = None


def save(cfg: dict) -> None:
    """Save config to the single global config file."""
    _save_file(GLOBAL_CONFIG_PATH, cfg)
    invalidate_config_cache()


def save_global(cfg: dict) -> None:
    """Save to the global config file (alias for save)."""
    save(cfg)


def get_theme(cfg: dict) -> str:
    return cfg.get("theme", "dark")


def save_theme(theme: str) -> None:
    cfg = load()
    cfg["theme"] = theme
    save(cfg)
