"""
config.py — single global config shared by all projects

Global config:  data/config.json
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent.parent

GLOBAL_CONFIG_PATH = ROOT / "data" / "config.json"

DEFAULTS: dict = {
    "name": "My Portfolio",
    "start_day": "2020-01-01",
    "default_currency": "PLN",
    "graph_precision": "1D",   # "1D" or "1W"
    "ticker_rules": [],
    "isin_tickers": [],
    "theme": "dark",
}


def _load_global() -> dict:
    if not GLOBAL_CONFIG_PATH.exists():
        _save_file(GLOBAL_CONFIG_PATH, DEFAULTS.copy())
        return DEFAULTS.copy()
    with GLOBAL_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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


def get_start_date(cfg: dict) -> date:
    return date.fromisoformat(cfg["start_day"])


def get_precision(cfg: dict) -> str:
    """Return pandas resample rule: 'D' or 'W-FRI'."""
    p = cfg.get("graph_precision", "1D")
    return "D" if p == "1D" else "W-FRI"


SUPPORTED_CURRENCIES = {"USD", "EUR", "PLN"}


def get_theme(cfg: dict) -> str:
    return cfg.get("theme", "dark")


def save_theme(theme: str) -> None:
    cfg = load()
    cfg["theme"] = theme
    save(cfg)
