"""ISIN resolution — pytest suite (split from the original monolithic runner)."""

from __future__ import annotations

from pathlib import Path


def test_isin_resolve_from_config(tmp: Path):
    """resolve_isins_with_names resolves ISINs based on config rules."""
    import json as _json
    import config as cfg_module

    cfg = cfg_module.load()
    cfg["isin_tickers"] = [
        "IE00B4L5Y983=IWDA.L",
        "US5949181085=MSFT.US",
    ]
    cfg_module.save(cfg)

    from isin_resolve import resolve_isins_with_names

    isin_map = {
        "IE00B4L5Y983": "iShares Core MSCI World",
        "US5949181085": "Microsoft",
        "DE0005793303": "unknown fund",
    }

    resolved, unresolved = resolve_isins_with_names(isin_map)
    assert resolved["IE00B4L5Y983"] == "IWDA.L"
    assert resolved["US5949181085"] == "MSFT.US"
    assert "DE0005793303" in unresolved
    assert unresolved["DE0005793303"] == "unknown fund"
