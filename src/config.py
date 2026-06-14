"""
config.py — global + per-project config

Global config:  data/config.json         (defaults for all projects)
Project config: data/{project}/config.json (overrides, only non-default values)
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
}


def _load_global() -> dict:
    if not GLOBAL_CONFIG_PATH.exists():
        _save_file(GLOBAL_CONFIG_PATH, DEFAULTS.copy())
        return DEFAULTS.copy()
    with GLOBAL_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_project() -> dict:
    from storage import project_config_path
    p = project_config_path()
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load() -> dict:
    """Return merged config: global defaults → per-project overrides."""
    global_cfg = _load_global()
    project_cfg = _load_project()
    merged = {**global_cfg, **project_cfg}
    # Fill missing keys from defaults
    changed = False
    for k, v in DEFAULTS.items():
        if k not in merged:
            merged[k] = v
            changed = True
    if changed and not project_cfg:
        _save_file(GLOBAL_CONFIG_PATH, merged)
    return merged


def save(cfg: dict) -> None:
    """Save config to the current project's config file."""
    from storage import project_config_path
    p = project_config_path()
    _save_file(p, cfg)


def save_global(cfg: dict) -> None:
    """Save to the global config file."""
    _save_file(GLOBAL_CONFIG_PATH, cfg)


def get_start_date(cfg: dict) -> date:
    return date.fromisoformat(cfg["start_day"])


def get_precision(cfg: dict) -> str:
    """Return pandas resample rule: 'D' or 'W-FRI'."""
    p = cfg.get("graph_precision", "1D")
    return "D" if p == "1D" else "W-FRI"


SUPPORTED_CURRENCIES = {"USD", "EUR", "PLN"}
