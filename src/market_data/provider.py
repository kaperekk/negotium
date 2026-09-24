"""
provider.py — unified market data provider and price/FX cache engine.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from domain.currencies import CURRENCY_SUFFIXES, SUFFIX_CURRENCY, SUPPORTED_CURRENCIES, TRIANGULATE_VIA_USD
from market_data.downloader import FX_YAHOO, download_year, suppress_output, yahoo_symbol
from storage import (
    has_price_year,
    load_dividends,
    load_price_year,
    load_ticker_meta,
    load_ticker_names,
    save_dividends,
    save_price_year,
    save_ticker_meta,
    save_ticker_names,
)

log = logging.getLogger(__name__)


def classify_asset_class(quote_type: str, sector: str, name: str) -> str:
    """Map Yahoo quoteType + name heuristics to a coarse asset class."""
    qt = (quote_type or "").upper()
    name_u = (name or "").upper()
    if qt == "CRYPTOCURRENCY":
        return "Crypto"
    if "BOND" in name_u or "TREASURY" in name_u or "OBLIGAC" in name_u:
        return "Bond"
    if any(k in name_u for k in ("GOLD", "SILVER", "OIL", "COMMODIT", "COPPER")):
        return "Commodity"
    if qt in ("ETF", "MUTUALFUND", "EQUITY", "INDEX", ""):
        return "Equity"
    return "Equity"


class MarketDataProvider:
    """Unified interface for price lookups, FX conversion, and ticker metadata."""

    def __init__(self):
        # RAM price slabs: cache[ticker][year] -> {date_str: price}
        self._cache: dict[str, dict[int, dict[str, float]]] = {}
        self._adj_cache: dict[str, dict[int, dict[str, float]]] = {}

    def get_price(
        self,
        ticker: str,
        on_date: str,
        year: int | None = None,
        adjusted: bool = False,
    ) -> float | None:
        """Return close price for ticker on on_date (YYYY-MM-DD)."""
        t = ticker.upper()
        if t in SUPPORTED_CURRENCIES:
            return 1.0

        if year is None:
            year = int(on_date[:4])

        store = self._adj_cache if adjusted else self._cache
        if t not in store:
            store[t] = {}
        if year not in store[t]:
            store[t][year] = load_price_year(t, year, adjusted=adjusted)

        year_prices = store[t][year]
        if on_date in year_prices:
            return year_prices[on_date]

        # Walk back up to 7 calendar days
        check = date.fromisoformat(on_date)
        for _ in range(7):
            s = check.isoformat()
            if s in year_prices:
                return year_prices[s]
            check -= timedelta(days=1)
            if check.year != year:
                prev = check.year
                if prev not in store[t]:
                    store[t][prev] = load_price_year(t, prev, adjusted=adjusted)
                year_prices = store[t][prev]
                year = prev

        return None

    def get_fx_rate(
        self,
        from_ccy: str,
        to_ccy: str,
        on_date: str,
        year: int | None = None,
    ) -> float:
        """Return exchange rate to convert 1 unit of from_ccy to to_ccy on on_date."""
        from_c = from_ccy.upper()
        to_c = to_ccy.upper()

        if from_c == to_c:
            return 1.0

        if year is None:
            year = int(on_date[:4])

        # Base currency is PLN
        if to_c == "PLN":
            if from_c in TRIANGULATE_VIA_USD:
                rate_usd = self.get_price(f"{from_c}USD", on_date, year) or 1.0
                usd_pln = self.get_price("USDPLN", on_date, year) or 1.0
                return rate_usd * usd_pln

            rate = self.get_price(f"{from_c}PLN", on_date, year)
            if rate is not None:
                return rate

            rate_inv = self.get_price(f"PLN{from_c}", on_date, year)
            if rate_inv is not None and rate_inv > 0:
                return 1.0 / rate_inv

            rate_usd = self.get_price(f"{from_c}USD", on_date, year)
            usd_pln = self.get_price("USDPLN", on_date, year)
            if rate_usd is not None and usd_pln is not None:
                return rate_usd * usd_pln

            return 1.0

        # Base currency is EUR or USD
        fx_from = self.get_fx_rate(from_c, "PLN", on_date, year)
        fx_to = self.get_fx_rate(to_c, "PLN", on_date, year)
        return fx_from / fx_to if fx_to > 0 else 1.0
