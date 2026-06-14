"""
transactions.py — transaction ledger management

transactions.jsonl schema (one object per line, chronological):
  {"date": "YYYY-MM-DD", "entries": [
      {"ticker": STR, "amount": FLOAT, "account_operation": BOOL}, ...
  ]}

  account_operation (optional, per entry): marks deposits/withdrawals
  that count toward invested capital.

balance.json schema:
  {"AAPL": 10.0, "PLN": 5000.0, ...}

Rules:
- File must stay chronological (ascending date).
- Inserting a transaction for an existing date: merge entries into that line.
- Inserting for a date earlier than the last line: find the correct position,
  insert, rewrite file, then invalidate portfolio cache from that date.
- Inserting for a new date after all existing: append.
"""
from __future__ import annotations

from datetime import date

import storage
import config as cfg_module
from ticker_translate import translate_ticker
from ticker_data import get_price


def _apply_entries(balance: dict[str, dict], entries: list[dict]) -> None:
    for e in entries:
        ticker = e["ticker"].upper()
        amount = float(e["amount"])
        if ticker not in balance:
            balance[ticker] = {"amount": 0.0, "avg_price": 0.0}
        balance[ticker]["amount"] = balance[ticker]["amount"] + amount
        if abs(balance[ticker]["amount"]) < 1e-9:
            balance[ticker]["amount"] = 0.0
            balance[ticker]["avg_price"] = 0.0


def add_transaction(
    tx_date: date | str,
    entries: list[dict],
    account_operation: bool = False,
) -> None:
    """
    Add a transaction for the given date.

    entries: [{"ticker": "AAPL", "amount": 10.0}, {"ticker": "USD", "amount": -1710.0}]
    account_operation: if True, every entry gets account_operation=True
                       (marks deposits/withdrawals that count as invested).
    """
    if isinstance(tx_date, date):
        date_str = tx_date.isoformat()
    else:
        date_str = tx_date

    # Normalise
    rules = cfg_module.load().get("ticker_rules", [])
    entries = [
        {"ticker": translate_ticker(e["ticker"], rules), "amount": round(float(e["amount"]), 8),
         **({"account_operation": True} if account_operation or e.get("account_operation") else {})}
        for e in entries
    ]

    records = storage.read_jsonl(storage.TRANSACTIONS_PATH)

    if not records:
        storage.append_jsonl(storage.TRANSACTIONS_PATH, {"date": date_str, "entries": entries})
        _rebuild_balance([{"date": date_str, "entries": entries}])
        storage.invalidate_portfolio_from(date_str)
        return

    last_date = records[-1]["date"]

    if date_str > last_date:
        # Fast append — new date after everything
        rec = {"date": date_str, "entries": entries}
        storage.append_jsonl(storage.TRANSACTIONS_PATH, rec)
        bal = storage.load_balance()
        base_ccy = cfg_module.load().get("default_currency", "PLN")
        _update_avg_prices(bal, rec, base_ccy)
        _apply_entries(bal, entries)
        storage.save_balance(bal)
        storage.invalidate_portfolio_from(date_str)
        return

    if date_str == last_date:
        # Merge into the last record
        records[-1]["entries"].extend(entries)
        storage.write_jsonl(storage.TRANSACTIONS_PATH, records)
        _rebuild_balance(records)
        storage.invalidate_portfolio_from(date_str)
        return

    # Past date — find insertion point, rewrite whole file
    new_records: list[dict] = []
    inserted = False
    for rec in records:
        if not inserted:
            if rec["date"] == date_str:
                # Merge into existing entry for this date
                rec = dict(rec)  # shallow copy to avoid mutating original
                rec["entries"] = rec["entries"] + entries
                new_records.append(rec)
                inserted = True
                continue
            elif rec["date"] > date_str:
                # Insert before this record
                new_records.append({"date": date_str, "entries": entries})
                inserted = True
        new_records.append(rec)

    if not inserted:
        new_records.append({"date": date_str, "entries": entries})

    storage.write_jsonl(storage.TRANSACTIONS_PATH, new_records)
    _rebuild_balance(new_records)
    storage.invalidate_portfolio_from(date_str)


def set_account_operation(date_str: str, entry_idx: int, value: bool) -> None:
    """Set or clear the account_operation flag on a specific entry.

    entry_idx: index of the entry within the transaction's entries list.
    """
    records = storage.read_jsonl(storage.TRANSACTIONS_PATH)
    for rec in records:
        if rec["date"] == date_str:
            entries = rec["entries"]
            if 0 <= entry_idx < len(entries):
                if value:
                    entries[entry_idx]["account_operation"] = True
                else:
                    entries[entry_idx].pop("account_operation", None)
                storage.write_jsonl(storage.TRANSACTIONS_PATH, records)
                storage.invalidate_portfolio_from(date_str)
            break


def delete_transaction(date_str: str, entry_idx: int) -> None:
    """Remove a single entry from a transaction. Removes the record if empty."""
    records = storage.read_jsonl(storage.TRANSACTIONS_PATH)
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
    storage.write_jsonl(storage.TRANSACTIONS_PATH, new_records)
    _rebuild_balance(new_records)
    storage.invalidate_portfolio_from(date_str)


def update_transaction(
    date_str: str,
    entry_idx: int,
    ticker: str,
    amount: float,
    account_operation: bool = False,
) -> None:
    """Replace a single entry's ticker, amount, and account_operation flag."""
    rules = cfg_module.load().get("ticker_rules", [])
    records = storage.read_jsonl(storage.TRANSACTIONS_PATH)
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
                storage.write_jsonl(storage.TRANSACTIONS_PATH, records)
                _rebuild_balance(records)
                storage.invalidate_portfolio_from(date_str)
            break


def _rebuild_balance(records: list[dict]) -> None:
    """Replay full ledger to recompute balance and avg_price from scratch."""
    base_ccy = cfg_module.load().get("default_currency", "PLN")
    balance: dict[str, dict] = {}
    for rec in records:
        _update_avg_prices(balance, rec, base_ccy)
        _apply_entries(balance, rec["entries"])
    storage.save_balance(balance)


def _update_avg_prices(balance: dict[str, dict], rec: dict, base_ccy: str) -> None:
    """After applying entries, compute avg_price in base currency for stock buys.

    Uses the ticker's close price on the transaction date to determine cost.
    """
    entries = rec["entries"]
    tx_date = rec["date"]
    yr = int(tx_date[:4])
    price_cache: dict = {}

    # Accumulate cost and shares per ticker for this transaction
    ticker_cost: dict[str, float] = {}
    ticker_shares: dict[str, float] = {}

    for e in entries:
        ticker = e["ticker"].upper()
        amt = float(e["amount"])
        if ticker in storage.SUPPORTED_CURRENCIES or amt <= 0:
            continue

        close = get_price(ticker, tx_date, price_cache, yr)
        if close is None:
            continue

        ticker_cost[ticker] = ticker_cost.get(ticker, 0.0) + amt * close
        ticker_shares[ticker] = ticker_shares.get(ticker, 0.0) + amt

    # Compute new avg_price = (old_cost + new_cost) / new_amount
    # balance still has pre-tx state since _apply_entries hasn't run yet
    for ticker, shares_bought in ticker_shares.items():
        pre = balance.get(ticker, {}).get("amount", 0.0)
        old_avg = balance.get(ticker, {}).get("avg_price", 0.0)

        # Net change to amount from this transaction (buys + sells)
        net_change = sum(float(e["amount"]) for e in entries
                         if e["ticker"].upper() == ticker)
        new_amount = pre + net_change
        if new_amount > 0:
            old_cost = pre * old_avg
            new_cost = old_cost + ticker_cost[ticker]
            new_avg = new_cost / new_amount
        else:
            new_avg = 0.0

        if ticker not in balance:
            balance[ticker] = {"amount": 0.0, "avg_price": new_avg}
        else:
            balance[ticker]["avg_price"] = new_avg


def get_all_transactions() -> list[dict]:
    """Return all transactions, chronologically."""
    return storage.read_jsonl(storage.TRANSACTIONS_PATH)


def get_transactions_up_to(as_of: str) -> list[dict]:
    """Return all transactions with date <= as_of."""
    return [r for r in get_all_transactions() if r["date"] <= as_of]


def compute_holdings_at(as_of: str) -> dict[str, float]:
    """
    Compute {ticker: amount} by replaying all transactions up to as_of.
    Returns only non-zero holdings (|amount| > 1e-9).
    """
    balance: dict[str, dict] = {}
    for rec in get_all_transactions():
        if rec["date"] > as_of:
            break
        _apply_entries(balance, rec["entries"])
    return {k: v["amount"] for k, v in balance.items() if abs(v["amount"]) > 1e-9}


def get_tickers(include_cash: bool = False) -> set[str]:
    """Return all unique non-cash tickers present in the ledger."""
    tickers: set[str] = set()
    for rec in get_all_transactions():
        for e in rec["entries"]:
            t = e["ticker"].upper()
            if include_cash or t not in storage.SUPPORTED_CURRENCIES:
                tickers.add(t)
    return tickers


def get_all_tickers(include_fx: bool = True) -> set[str]:
    """Return all tickers including FX pairs needed for price data."""
    tickers: set[str] = set()
    cash_currencies: set[str] = set()
    for rec in get_all_transactions():
        for e in rec["entries"]:
            t = e["ticker"].upper()
            if t in storage.SUPPORTED_CURRENCIES:
                cash_currencies.add(t)
            else:
                tickers.add(t)
    if include_fx:
        if "USD" in cash_currencies or tickers:
            tickers.add("USDPLN")
        if "EUR" in cash_currencies:
            tickers.add("EURPLN")
            tickers.add("EURUSD")
        for ccy, suffixes in storage.CURRENCY_SUFFIXES.items():
            if ccy == "PLN":
                continue
            if not any(t.upper().endswith(s) for t in tickers for s in suffixes):
                continue
            if ccy in storage.TRIANGULATE_VIA_USD:
                tickers.add(f"{ccy}USD")
            else:
                tickers.add(f"{ccy}PLN")
    return tickers
