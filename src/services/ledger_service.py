"""
ledger_service.py — domain transaction ledger service.

Provides thread-safe transaction recording, replaying, editing, and financial
performance metric calculations using domain models and typed repositories.
"""
from __future__ import annotations

import functools
import logging
import os
import threading
from datetime import date
from typing import Callable

import config as cfg_module
from domain.currencies import CURRENCY_SUFFIXES, SUPPORTED_CURRENCIES, TRIANGULATE_VIA_USD
from domain.models import LedgerEntry, Transaction
from market_data.provider import MarketDataProvider
from storage.context import ProjectContext
from storage.repositories import BalanceRepository, SnapshotRepository, TransactionRepository
from ticker_translate import translate_ticker

log = logging.getLogger(__name__)
_ledger_lock = threading.RLock()
_tx_cache_lock = threading.Lock()


def locked(fn):
    """Decorator to serialize ledger mutators under the process-wide lock."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _ledger_lock:
            return fn(*args, **kwargs)
    return wrapper


class LedgerService:
    """Core ledger operations service."""

    def __init__(
        self,
        context: ProjectContext | None = None,
        market_data: MarketDataProvider | None = None,
    ):
        self.context = context or ProjectContext()
        self.tx_repo = TransactionRepository(self.context)
        self.snap_repo = SnapshotRepository(self.context)
        self.bal_repo = BalanceRepository(self.context)
        self.market_data = market_data or MarketDataProvider()

    @locked
    def add_transaction(
        self,
        tx_date: date | str,
        entries: list[dict] | list[LedgerEntry],
        account_operation: bool = False,
    ) -> None:
        """Add a transaction for a given date, normalize tickers, update balance, and invalidate cache."""
        date_str = tx_date.isoformat() if isinstance(tx_date, date) else tx_date
        rules = cfg_module.load().get("ticker_rules", [])

        normalized_entries: list[dict] = []
        for e in entries:
            raw = e.to_dict() if isinstance(e, LedgerEntry) else e
            t = translate_ticker(raw["ticker"], rules)
            amt = round(float(raw["amount"]), 8)
            is_op = account_operation or raw.get("account_operation", False)
            entry_dict: dict = {"ticker": t, "amount": amt}
            if is_op:
                entry_dict["account_operation"] = True
            normalized_entries.append(entry_dict)

        records = self.tx_repo.get_all_dicts()

        if not records:
            records = [{"date": date_str, "entries": normalized_entries}]
            self.tx_repo.save_all(records)
        else:
            last_date = records[-1]["date"]
            if date_str > last_date:
                records.append({"date": date_str, "entries": normalized_entries})
                self.tx_repo.save_all(records)
            elif date_str == last_date:
                records[-1]["entries"].extend(normalized_entries)
                self.tx_repo.save_all(records)
            else:
                new_records: list[dict] = []
                inserted = False
                for rec in records:
                    if not inserted:
                        if rec["date"] == date_str:
                            rec = dict(rec)
                            rec["entries"] = rec["entries"] + normalized_entries
                            new_records.append(rec)
                            inserted = True
                            continue
                        elif rec["date"] > date_str:
                            new_records.append({"date": date_str, "entries": normalized_entries})
                            inserted = True
                    new_records.append(rec)
                if not inserted:
                    new_records.append({"date": date_str, "entries": normalized_entries})
                records = new_records
                self.tx_repo.save_all(records)

        self.rebuild_balance(records)
        self.snap_repo.invalidate_portfolio_from(date_str)

    @locked
    def set_account_operation(self, date_str: str, entry_idx: int, value: bool) -> None:
        """Set or clear account_operation flag on a specific entry."""
        records = self.tx_repo.get_all_dicts()
        for rec in records:
            if rec["date"] == date_str:
                entries = rec["entries"]
                if 0 <= entry_idx < len(entries):
                    if value:
                        entries[entry_idx]["account_operation"] = True
                    else:
                        entries[entry_idx].pop("account_operation", None)
                    self.tx_repo.save_all(records)
                    self.snap_repo.invalidate_portfolio_from(date_str)
                break

    @locked
    def delete_transaction(self, date_str: str, entry_idx: int) -> None:
        """Remove a single entry from a transaction; remove record if empty."""
        records = self.tx_repo.get_all_dicts()
        new_records: list[dict] = []
        for rec in records:
            if rec["date"] == date_str:
                if 0 <= entry_idx < len(rec["entries"]):
                    rec["entries"].pop(entry_idx)
                    if rec["entries"]:
                        new_records.append(rec)
                else:
                    new_records.append(rec)
            else:
                new_records.append(rec)
        self.tx_repo.save_all(new_records)
        self.rebuild_balance(new_records)
        self.snap_repo.invalidate_portfolio_from(date_str)

    @locked
    def update_transaction(
        self,
        date_str: str,
        entry_idx: int,
        ticker: str,
        amount: float,
        account_operation: bool = False,
    ) -> None:
        """Replace a single entry's ticker, amount, and flag."""
        rules = cfg_module.load().get("ticker_rules", [])
        records = self.tx_repo.get_all_dicts()
        for rec in records:
            if rec["date"] == date_str:
                if 0 <= entry_idx < len(rec["entries"]):
                    new_entry: dict = {
                        "ticker": translate_ticker(ticker.upper(), rules),
                        "amount": round(float(amount), 8),
                    }
                    if account_operation:
                        new_entry["account_operation"] = True
                    rec["entries"][entry_idx] = new_entry
                    self.tx_repo.save_all(records)
                    self.rebuild_balance(records)
                    self.snap_repo.invalidate_portfolio_from(date_str)
                break

    @locked
    def remap_tickers(self) -> int:
        """Re-apply ticker translation rules across all entries."""
        rules = cfg_module.load().get("ticker_rules", [])
        records = self.tx_repo.get_all_dicts()
        changed = 0
        for rec in records:
            for i, e in enumerate(rec["entries"]):
                new_ticker = translate_ticker(e["ticker"], rules)
                if new_ticker != e["ticker"]:
                    rec["entries"][i] = {**e, "ticker": new_ticker}
                    changed += 1
        if changed:
            self.tx_repo.save_all(records)
            self.rebuild_balance(records)
            if records:
                self.snap_repo.invalidate_portfolio_from(records[0]["date"])
        return changed

    @locked
    def rebuild_balance(self, records: list[dict] | None = None) -> None:
        """Replay ledger to calculate and persist holdings and avg_price."""
        if records is None:
            records = self.tx_repo.get_all_dicts()
        base_ccy = cfg_module.load().get("default_currency", "PLN")
        today_str = date.today().isoformat()

        balance: dict[str, dict] = {}
        for rec in records:
            if rec["date"] > today_str:
                continue
            self._update_avg_prices(balance, rec, base_ccy)
            self._apply_entries(balance, rec["entries"])
        self.bal_repo.save_balance(balance)

    def _apply_entries(self, balance: dict[str, dict], entries: list[dict]) -> None:
        for e in entries:
            ticker = e["ticker"].upper()
            amount = float(e["amount"])
            if ticker not in balance:
                balance[ticker] = {"amount": 0.0, "avg_price": 0.0}
            balance[ticker]["amount"] += amount
            if abs(balance[ticker]["amount"]) < 1e-9:
                balance[ticker]["amount"] = 0.0
                balance[ticker]["avg_price"] = 0.0

    def _update_avg_prices(self, balance: dict[str, dict], rec: dict, base_ccy: str) -> None:
        entries = rec["entries"]
        tx_date = rec["date"]
        yr = int(tx_date[:4])

        ticker_cost: dict[str, float] = {}
        ticker_shares: dict[str, float] = {}

        for e in entries:
            ticker = e["ticker"].upper()
            amt = float(e["amount"])
            if ticker in SUPPORTED_CURRENCIES or amt <= 0:
                continue
            close = self.market_data.get_price(ticker, tx_date, yr)
            if close is None:
                continue
            ticker_cost[ticker] = ticker_cost.get(ticker, 0.0) + amt * close
            ticker_shares[ticker] = ticker_shares.get(ticker, 0.0) + amt

        all_tickers = set(ticker_shares.keys())
        for e in entries:
            t = e["ticker"].upper()
            if t not in SUPPORTED_CURRENCIES:
                all_tickers.add(t)

        for ticker in all_tickers:
            pre = balance.get(ticker, {}).get("amount", 0.0)
            old_avg = balance.get(ticker, {}).get("avg_price", 0.0)
            net_change = sum(float(e["amount"]) for e in entries if e["ticker"].upper() == ticker)
            new_amount = pre + net_change
            if new_amount > 0:
                old_cost = pre * old_avg
                if ticker in ticker_cost:
                    new_cost = old_cost + ticker_cost[ticker]
                else:
                    new_cost = old_avg * new_amount
                new_avg = new_cost / new_amount
            else:
                new_avg = 0.0

            if ticker not in balance:
                balance[ticker] = {"amount": 0.0, "avg_price": new_avg}
            else:
                balance[ticker]["avg_price"] = new_avg
