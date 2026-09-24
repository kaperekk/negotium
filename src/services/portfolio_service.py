"""
portfolio_service.py — portfolio valuation time-series generation service.

Implements single-forward-pass valuation O(days + tx) using MarketDataProvider
and typed Repository persistence.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable, Iterator

from domain.currencies import SUFFIX_CURRENCY, SUPPORTED_CURRENCIES
from domain.models import AssetHolding, PortfolioSnapshot
from market_data.downloader import FX_YAHOO
from market_data.provider import MarketDataProvider
from storage.context import ProjectContext
from storage.repositories import SnapshotRepository, TransactionRepository

log = logging.getLogger(__name__)
FX_TICKERS = set(FX_YAHOO.keys())


def detect_ticker_currency(ticker: str, market_data: MarketDataProvider | None = None) -> str:
    """Determine trading currency for a ticker symbol."""
    t = ticker.upper()
    if t in SUPPORTED_CURRENCIES:
        return t
    ext = t[t.rfind("."):] if "." in t else ""
    ccy = SUFFIX_CURRENCY.get(ext)
    if ccy:
        return ccy
    if t in FX_TICKERS:
        return "PLN"
    return "USD"


def day_range_generator(start: date, end: date, precision: str) -> Iterator[date]:
    """Generate date sequence for daily (D) or weekly (W-FRI) precision."""
    if precision == "D":
        d = start
        while d <= end:
            yield d
            d += timedelta(days=1)
    else:
        d = start
        d += timedelta(days=(4 - d.weekday()) % 7)
        while d <= end:
            yield d
            d += timedelta(weeks=1)


class PortfolioService:
    """Service for building and maintaining portfolio valuation time series."""

    def __init__(
        self,
        context: ProjectContext | None = None,
        market_data: MarketDataProvider | None = None,
    ):
        self.context = context or ProjectContext()
        self.tx_repo = TransactionRepository(self.context)
        self.snap_repo = SnapshotRepository(self.context)
        self.market_data = market_data or MarketDataProvider()

    def build_portfolio(
        self,
        start_date: date,
        end_date: date,
        base_currency: str,
        precision: str = "D",
        progress_cb: Callable[[str, float], None] | None = None,
        use_cache: bool = True,
    ) -> list[PortfolioSnapshot]:
        """Build or resume the portfolio value time-series in a single forward pass."""
        base_currency = base_currency.upper()

        existing: list[PortfolioSnapshot] = []
        if use_cache:
            existing = [
                s for s in self.snap_repo.load_portfolio()
                if s.base_currency == base_currency
            ]

        if existing:
            last_cached = existing[-1].date
            resume_from = date.fromisoformat(last_cached) + timedelta(days=1)
            last_snap = existing[-1]
            balance: dict[str, float] = {a.ticker: a.amount for a in last_snap.assets}
            cumulative_contrib = last_snap.invested
        else:
            resume_from = start_date
            balance = {}
            cumulative_contrib = 0.0

        today_str = date.today().isoformat()
        all_tx = self.tx_repo.get_all_dicts()
        resume_str = resume_from.isoformat()
        pending_tx = [r for r in all_tx if resume_str <= r["date"] <= today_str]
        tx_idx = 0
        n_tx = len(pending_tx)

        all_days = list(day_range_generator(resume_from, end_date, precision))
        total_days = max(len(all_days), 1)
        new_snapshots: list[PortfolioSnapshot] = []

        for i, day in enumerate(all_days):
            day_str = day.isoformat()
            year = day.year

            if progress_cb and i % 10 == 0:
                progress_cb(day_str, i / total_days)

            while tx_idx < n_tx and pending_tx[tx_idx]["date"] <= day_str:
                rec = pending_tx[tx_idx]
                tx_year = int(rec["date"][:4])

                for e in rec["entries"]:
                    t = e["ticker"].upper()
                    amt = float(e["amount"])
                    balance[t] = balance.get(t, 0.0) + amt

                    if e.get("account_operation", False):
                        fx = self.market_data.get_fx_rate(t, base_currency, rec["date"], tx_year)
                        cumulative_contrib += amt * fx

                tx_idx += 1

            balance = {k: v for k, v in balance.items() if abs(v) > 1e-9}

            if not balance:
                new_snapshots.append(
                    PortfolioSnapshot(
                        date=day_str,
                        assets=[],
                        total_value=0.0,
                        invested=0.0,
                        base_currency=base_currency,
                    )
                )
                continue

            assets: list[AssetHolding] = []
            total_value = 0.0

            for ticker, amount in balance.items():
                t = ticker.upper()
                if t in FX_TICKERS:
                    continue

                if t in SUPPORTED_CURRENCIES:
                    rate = self.market_data.get_fx_rate(t, base_currency, day_str, year)
                    value_base = round(amount * rate, 2)
                    assets.append(
                        AssetHolding(
                            ticker=t,
                            amount=round(amount, 8),
                            price=1.0,
                            currency=t,
                            value_native=round(amount, 2),
                            value_base=value_base,
                        )
                    )
                    total_value += value_base
                else:
                    price = self.market_data.get_price(t, day_str, year)
                    if price is None:
                        continue
                    ticker_ccy = detect_ticker_currency(t, self.market_data)
                    value_native = round(amount * price, 2)
                    rate = self.market_data.get_fx_rate(ticker_ccy, base_currency, day_str, year)
                    value_base = round(value_native * rate, 2)
                    assets.append(
                        AssetHolding(
                            ticker=t,
                            amount=round(amount, 8),
                            price=round(price, 6),
                            currency=ticker_ccy,
                            value_native=value_native,
                            value_base=value_base,
                        )
                    )
                    total_value += value_base

            new_snapshots.append(
                PortfolioSnapshot(
                    date=day_str,
                    assets=assets,
                    total_value=round(total_value, 2),
                    invested=round(cumulative_contrib, 2),
                    base_currency=base_currency,
                )
            )

        if progress_cb:
            progress_cb(end_date.isoformat(), 1.0)

        merged = self._merge_snapshots(existing, new_snapshots)
        self.snap_repo.save_portfolio(merged)
        return merged

    def _merge_snapshots(
        self,
        existing: list[PortfolioSnapshot],
        new: list[PortfolioSnapshot],
    ) -> list[PortfolioSnapshot]:
        if not existing:
            return new
        if not new:
            return existing
        seen: dict[str, PortfolioSnapshot] = {s.date: s for s in existing}
        for s in new:
            seen[s.date] = s
        return sorted(seen.values(), key=lambda x: x.date)
