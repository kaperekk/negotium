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
        storage.append_jsonl(storage.TRANSACTIONS_PATH, {"date": date_str, "entries": entries})
        bal = storage.load_balance()
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
    balance: dict[str, dict] = {}
    for rec in records:
        _apply_entries(balance, rec["entries"])
        _update_avg_prices(balance, rec)
    storage.save_balance(balance)


def _update_avg_prices(balance: dict[str, dict], rec: dict) -> None:
    """After applying entries, compute avg_price for stock buys."""
    entries = rec["entries"]
    stock_entries = [e for e in entries if e["ticker"].upper() not in storage.SUPPORTED_CURRENCIES]
    cash_entries = [e for e in entries if e["ticker"].upper() in storage.SUPPORTED_CURRENCIES]

    total_cash_spent = 0.0
    for ce in cash_entries:
        amt = float(ce["amount"])
        if amt < 0:
            total_cash_spent += abs(amt)

    total_shares_bought = 0.0
    for se in stock_entries:
        amt = float(se["amount"])
        if amt > 0:
            total_shares_bought += amt

    if total_shares_bought > 0 and total_cash_spent > 0:
        price_per_share = total_cash_spent / total_shares_bought
        for se in stock_entries:
            ticker = se["ticker"].upper()
            amt = float(se["amount"])
            if amt > 0 and ticker in balance:
                bal = balance[ticker]
                old_amount = bal["amount"] - amt
                old_avg = bal["avg_price"]
                new_amount = bal["amount"]
                if new_amount > 0:
                    bal["avg_price"] = (old_amount * old_avg + amt * price_per_share) / new_amount
    elif total_shares_bought > 0 and len(stock_entries) == 1:
        # Single stock buy without explicit cash pairing - try to find price from entries
        pass


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
    tickers = get_tickers(include_cash=False)
    if include_fx:
        cash_currencies: set[str] = set()
        for rec in get_all_transactions():
            for e in rec["entries"]:
                t = e["ticker"].upper()
                if t in storage.SUPPORTED_CURRENCIES:
                    cash_currencies.add(t)
        if "USD" in cash_currencies or tickers:
            tickers.add("USDPLN")
        if "EUR" in cash_currencies:
            tickers.add("EURPLN")
            tickers.add("EURUSD")
        # Add FX pairs for any currency whose suffix appears in a ticker
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
