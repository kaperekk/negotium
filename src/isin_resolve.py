"""
isin_resolve.py — ISIN to ticker resolver

Resolves ISIN identifiers against user-configured mappings in config.json.
Format: "ISIN=TICKER" (e.g. "IE00B4L5Y983=IWDA.L")
"""
from __future__ import annotations

from typing import Callable
import config as cfg_module


def resolve_isins_with_names(
    isin_to_papier: dict[str, str],
    progress_cb: Callable[[float, str], None] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve a mapping of {ISIN: name} to {ISIN: ticker}.

    Returns:
        tuple[resolved, unresolved]:
            - resolved: dict mapping ISIN -> translated ticker
            - unresolved: dict mapping unmapped ISIN -> original paper name
    """
    cfg = cfg_module.load()
    rules: dict[str, str] = {}
    for rule in cfg.get("isin_tickers", []):
        if "=" in rule:
            isin, ticker = rule.split("=", 1)
            rules[isin.strip().upper()] = ticker.strip()

    resolved: dict[str, str] = {}
    unresolved: dict[str, str] = {}

    for isin_raw, papier_name in isin_to_papier.items():
        isin_key = isin_raw.strip().upper()
        if isin_key in rules:
            resolved[isin_raw] = rules[isin_key]
        else:
            unresolved[isin_raw] = papier_name

    return resolved, unresolved
