"""
isin_resolve.py — ISIN to ticker resolver

Reads ISIN→ticker mappings from data/config.json "isin_tickers" list.
Format: "ISIN=TICKER" (e.g. "IE00B4L5Y983=IWDA.L")
"""
from __future__ import annotations

import config as cfg_module


def resolve_isins_with_names(
    isin_to_papier: dict[str, str],
    progress_cb=None,
) -> tuple[dict[str, str], dict[str, str]]:
    cfg = cfg_module.load()
    cache: dict[str, str] = {}
    for rule in cfg.get("isin_tickers", []):
        if "=" in rule:
            isin, ticker = rule.split("=", 1)
            cache[isin.strip()] = ticker.strip()

    resolved = {isin: cache.get(isin) for isin in isin_to_papier}
    unresolved = {isin: isin_to_papier[isin] for isin in isin_to_papier if not resolved.get(isin)}
    return resolved, unresolved
