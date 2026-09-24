"""
market_data package initialization.
"""
from __future__ import annotations

from market_data.downloader import (
    FX_YAHOO,
    download_year,
    ensure_batch,
    suppress_output,
    yahoo_symbol,
)
from market_data.provider import MarketDataProvider, classify_asset_class

__all__ = [
    "FX_YAHOO",
    "suppress_output",
    "yahoo_symbol",
    "download_year",
    "ensure_batch",
    "MarketDataProvider",
    "classify_asset_class",
]
