"""
config.py — load and manage config.json
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent.parent  # investment_tracker/

CONFIG_PATH = ROOT / "data" / "config.json"

DEFAULTS: dict = {
    "name": "My Portfolio",
    "start_day": "2020-01-01",
    "default_currency": "PLN",
    "graph_precision": "1D",   # "1D" or "1W"
    "ticker_rules": [],
    "isin_tickers": [],
}


def load() -> dict:
    """Return config dict, creating config.json with defaults if missing."""
    if not CONFIG_PATH.exists():
        save(DEFAULTS.copy())
        return DEFAULTS.copy()
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # Fill in any missing keys from defaults
    changed = False
    for k, v in DEFAULTS.items():
        if k not in data:
            data[k] = v
            changed = True
    if changed:
        save(data)
    return data


def save(cfg: dict) -> None:
    """Write config dict to config.json."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_start_date(cfg: dict) -> date:
    return date.fromisoformat(cfg["start_day"])


def get_precision(cfg: dict) -> str:
    """Return pandas resample rule: 'D' or 'W-FRI'."""
    p = cfg.get("graph_precision", "1D")
    return "D" if p == "1D" else "W-FRI"


SUPPORTED_CURRENCIES = {"USD", "EUR", "PLN"}
