"""Compatibility layer for portfolio/time-series generation.

The implementation remains in portfolio_core.py so the runtime can import the
public module name without needing a monolithic file.
"""

from __future__ import annotations

from portfolio_core import (
    FX_TICKERS,
    _day_range,
    _merge_snapshots,
    _PriceCache,
    _ticker_currency,
    build_portfolio,
    snapshots_to_series,
)

__all__ = [
    "FX_TICKERS",
    "_PriceCache",
    "_ticker_currency",
    "build_portfolio",
    "snapshots_to_series",
    "_day_range",
    "_merge_snapshots",
]
