"""
xtb_import.py — Structured XTB broker statement importer

Parses Cash Operations, Open Positions, and Closed Positions from XTB Excel exports
using typed domain models (Transaction, LedgerEntry) and a modular parsing & reconciliation pipeline.
"""
from __future__ import annotations

import logging
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd

import config as cfg_module
import storage
from domain.models import LedgerEntry, Transaction
from ticker_translate import translate_ticker

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

SHARE_RE = re.compile(r"(?:OPEN|CLOSE)\s+BUY\s+([\d.]+)")

_OPENPYXL_NO_DEFAULT_STYLE = "Workbook contains no default style, apply openpyxl's default"

_POLAND_TZ = ZoneInfo("Europe/Warsaw")


def _parse_shares(comment: str | None) -> float | None:
    if not comment:
        return None
    m = SHARE_RE.search(comment)
    return float(m.group(1)) if m else None


def _open_workbook(file_path: str | Path):
    """Try openpyxl first, fall back to pandas/calamine if the sheet is unreadable.

    The returned object (an openpyxl ``Workbook`` or a pandas ``ExcelFile``)
    is owned by the caller, which must always close it.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=_OPENPYXL_NO_DEFAULT_STYLE)
        try:
            return openpyxl.load_workbook(file_path, data_only=True), "openpyxl"
        except Exception:
            pass
        try:
            return pd.ExcelFile(file_path, engine="openpyxl"), "pandas"
        except Exception:
            pass
        return pd.ExcelFile(file_path, engine="calamine"), "calamine"


def _iter_sheet_rows(wb: Any, engine: str, sheet_name: str) -> list[tuple] | None:
    """Safely extracts all rows from a sheet as a list of tuples, or returns None if missing."""
    if engine == "openpyxl":
        if sheet_name not in wb.sheetnames:
            return None
        ws = wb[sheet_name]
        return [tuple(row) for row in ws.iter_rows(values_only=True)]
    else:
        if sheet_name not in wb.sheet_names:
            return None
        df = wb.parse(sheet_name, header=None)
        return [tuple(row) for _, row in df.iterrows()]


def _parse_datetime(time_val: Any, assume_utc: bool = False, to_local: bool = False) -> datetime | None:
    """Helper to parse datetime from str, datetime, or timestamp.

    If assume_utc=True, naive datetimes are treated as UTC.
    If to_local=True, converts the result to Poland local time (Europe/Warsaw).
    """
    if time_val is None or (isinstance(time_val, float) and pd.isna(time_val)):
        return None
    if isinstance(time_val, str):
        time_str = time_val.strip()
        if not time_str:
            return None
        try:
            dt = datetime.fromisoformat(time_str)
        except ValueError:
            return None
    elif isinstance(time_val, datetime):
        dt = time_val
    else:
        return None

    if dt.tzinfo is None and assume_utc:
        dt = dt.replace(tzinfo=timezone.utc)

    if to_local and dt.tzinfo is not None:
        dt = dt.astimezone(_POLAND_TZ)

    return dt


def _to_float(val: Any, default: float = 0.0) -> float:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.strip())
        except ValueError:
            return default
    return default


# ─────────────────────────────────────────────────────────────────────────────
# 1. Sheet Extraction & Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_xtb_file(file_path: str | Path) -> tuple[bool, str]:
    """Validate that the file can be opened and contains a valid 'Cash Operations' sheet."""
    try:
        wb, engine = _open_workbook(file_path)
    except Exception as e:
        return False, f"Cannot open file: {e}"

    try:
        rows = _iter_sheet_rows(wb, engine, "Cash Operations")
        if rows is None:
            return False, "Missing 'Cash Operations' sheet."

        header_row = None
        for row in rows[:15]:
            if row and any(str(c).strip().lower() == "type" for c in row if c is not None):
                header_row = row
                break

        if not header_row:
            return False, "Cannot find column headers (Type, Ticker, ...) in Cash Operations."

        required = {"Type", "Ticker", "Amount", "Time"}
        actual = {str(c).strip() for c in header_row if c and str(c).strip() != "nan"}
        missing = required - actual
        if missing:
            return False, f"Missing columns: {', '.join(missing)}"

        return True, "Valid XTB statement."
    except Exception as e:
        return False, f"Error reading file: {e}"
    finally:
        try:
            wb.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 2. Individual Sheet Parsers (returning structured Transaction / DateEntry objects)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_cash_operations_raw(file_path: str | Path, currency: str) -> list[Transaction]:
    """Parse the 'Cash Operations' sheet into a list of daily Transaction objects."""
    currency = currency.upper()
    rules = cfg_module.load().get("ticker_rules", [])

    wb, engine = _open_workbook(file_path)
    try:
        rows = _iter_sheet_rows(wb, engine, "Cash Operations")
    finally:
        try:
            wb.close()
        except Exception:
            pass

    if not rows:
        return []

    header: list[str] = []
    raw: list[tuple] = []
    for row in rows:
        if not header and any(str(c).strip().lower() == "type" for c in row if c is not None):
            header = [str(c).strip() if c is not None else "" for c in row]
            continue
        if header:
            raw.append(row)

    col = {name.lower(): i for i, name in enumerate(header) if name}
    idx_type = col.get("type")
    idx_ticker = col.get("ticker")
    idx_time = col.get("time")
    idx_amount = col.get("amount")
    idx_comment = col.get("comment")

    date_entries: list[Transaction] = []

    for row in raw:
        op_type = row[idx_type] if idx_type is not None and idx_type < len(row) else None
        ticker = row[idx_ticker] if idx_ticker is not None and idx_ticker < len(row) else None
        time_val = row[idx_time] if idx_time is not None and idx_time < len(row) else None
        amount_val = row[idx_amount] if idx_amount is not None and idx_amount < len(row) else None
        comment = row[idx_comment] if idx_comment is not None and idx_comment < len(row) else None

        if not op_type or str(op_type).strip() == "Total":
            continue
        if amount_val is None or (isinstance(amount_val, float) and pd.isna(amount_val)):
            continue

        dt = _parse_datetime(time_val)
        if not dt:
            continue

        date_str = dt.strftime("%Y-%m-%d")
        amount = _to_float(amount_val)
        op_type_str = str(op_type).strip()

        entries: list[LedgerEntry] = []

        if op_type_str == "Stock purchase":
            shares = _parse_shares(str(comment) if comment else None)
            if shares and shares > 0:
                entries.append(LedgerEntry(ticker=translate_ticker(str(ticker), rules), amount=round(shares, 8)))
                entries.append(LedgerEntry(ticker=currency, amount=round(amount, 8)))

        elif op_type_str == "Stock sell":
            shares = _parse_shares(str(comment) if comment else None)
            if shares and shares > 0:
                entries.append(LedgerEntry(ticker=translate_ticker(str(ticker), rules), amount=round(-shares, 8)))
                entries.append(LedgerEntry(ticker=currency, amount=round(amount, 8)))

        elif op_type_str in ("Deposit", "Withdrawal", "IKE deposit", "IKE withdrawal"):
            entries.append(LedgerEntry(ticker=currency, amount=round(amount, 8), account_operation=True))

        elif op_type_str == "Transfer":
            # Transfer is typically internal account transfer or currency conversion (FX swap)
            # Not a deposit/withdrawal — doesn't count toward invested capital
            entries.append(LedgerEntry(ticker=currency, amount=round(amount, 8)))

        elif op_type_str in ("Dividend", "Dividend from foreign company on PL market"):
            entries.append(LedgerEntry(ticker=currency, amount=round(amount, 8)))

        elif op_type_str in (
            "Free funds interest", "Free funds interest tax",
            "Withholding tax", "Commission", "Fractional shares",
        ):
            if amount != 0:
                entries.append(LedgerEntry(ticker=currency, amount=round(amount, 8)))

        elif amount != 0:
            log.warning(
                "XTB row type not recognised — skipped: %r (%.2f %s on %s, comment: %s)",
                op_type_str, amount, currency, date_str, str(comment)[:80],
            )

        if entries:
            date_entries.append(Transaction(date=date_str, entries=entries))

    date_entries.sort(key=lambda t: t.date)
    return date_entries


def parse_xtb_excel(file_path: str | Path, currency: str) -> list[dict]:
    """Parse the 'Cash Operations' sheet from XTB Excel and return merged daily transactions as dicts."""
    currency = currency.upper()
    log.info("Parsing %s (currency=%s)", file_path, currency)

    txns = _parse_cash_operations_raw(file_path, currency)

    # Merge entries occurring on the exact same date
    merged: list[Transaction] = []
    for tx in txns:
        if merged and merged[-1].date == tx.date:
            merged[-1].entries.extend(tx.entries)
        else:
            merged.append(Transaction(date=tx.date, entries=list(tx.entries)))

    log.info("Parsed %d raw transactions, merged to %d daily records", len(txns), len(merged))
    return [t.to_dict() for t in merged]


def parse_closed_positions(file_path: str | Path, currency: str) -> list[dict]:
    """Parse the 'Closed Positions' sheet into transactions.

    Each BUY row becomes an acquisition transaction with the open date,
    volume (shares), and purchase value. SELL rows are skipped.
    Rows with "spinoff" in the comment are marked as spinoffs.
    """
    currency = currency.upper()
    rules = cfg_module.load().get("ticker_rules", [])
    log.info("Parsing closed positions from %s", file_path)

    wb, engine = _open_workbook(file_path)
    try:
        rows = _iter_sheet_rows(wb, engine, "Closed Positions")
    finally:
        try:
            wb.close()
        except Exception:
            pass

    if not rows:
        return []

    header: list[str] = []
    raw: list[tuple] = []
    for row in rows:
        if not header and any(str(c).strip().lower() == "instrument" for c in row if c is not None):
            header = [str(c).strip() if c is not None else "" for c in row]
            continue
        if header:
            raw.append(row)

    if not header:
        return []

    col = {name.lower(): i for i, name in enumerate(header) if name}
    idx_ticker = col.get("ticker")
    idx_type = col.get("type")
    idx_volume = col.get("volume")
    idx_open_time = col.get("open time (utc)")
    idx_purchase_value = col.get("purchase value")
    idx_open_price = col.get("open price")
    # Comment column may not have a header name; find the last column with data
    idx_comment = max((i for i, name in enumerate(header) if name), default=None)
    if idx_comment is not None and idx_comment not in col.values():
        # Use the rightmost column as comment if it's not already mapped
        pass

    transactions: list[dict] = []
    for row in raw:
        ticker = row[idx_ticker] if idx_ticker is not None and idx_ticker < len(row) else None
        op_type = row[idx_type] if idx_type is not None and idx_type < len(row) else None
        volume_val = row[idx_volume] if idx_volume is not None and idx_volume < len(row) else None
        open_time_val = row[idx_open_time] if idx_open_time is not None and idx_open_time < len(row) else None
        purchase_val = row[idx_purchase_value] if idx_purchase_value is not None and idx_purchase_value < len(row) else None
        open_price_val = row[idx_open_price] if idx_open_price is not None and idx_open_price < len(row) else None
        comment = row[idx_comment] if idx_comment is not None and idx_comment < len(row) else None

        if not ticker or not op_type or str(op_type).strip().upper() != "BUY":
            continue

        volume = _to_float(volume_val)
        if volume <= 0:
            continue

        open_time = _parse_datetime(open_time_val, assume_utc=True, to_local=True)
        if not open_time:
            continue

        purchase = _to_float(purchase_val)
        open_price = _to_float(open_price_val)
        translated = translate_ticker(str(ticker), rules)

        # Detect spinoff: near-zero open price (per-share) OR "spinoff" in comment
        is_spinoff = (open_price > 0 and open_price < 0.01) or (comment and "spinoff" in str(comment).lower())

        entries = [
            LedgerEntry(ticker=translated, amount=round(volume, 8)),
            LedgerEntry(ticker=currency, amount=round(-abs(purchase), 8)),
        ]
        tx = Transaction(date=open_time.strftime("%Y-%m-%d"), entries=entries)
        d = tx.to_dict()
        d["_source"] = "closed_positions"
        d["_ticker_raw"] = str(ticker).upper()
        if is_spinoff:
            d["_is_spinoff"] = True
        transactions.append(d)

    transactions.sort(key=lambda r: r["date"])
    log.info("Parsed %d closed position BUY entries", len(transactions))
    return transactions


def parse_open_positions(file_path: str | Path, currency: str) -> list[dict]:
    """Parse the 'Open Positions' sheet into acquisition transactions.

    Each BUY row with a valid open date becomes an acquisition transaction.
    """
    currency = currency.upper()
    rules = cfg_module.load().get("ticker_rules", [])
    log.info("Parsing open positions from %s", file_path)

    wb, engine = _open_workbook(file_path)
    try:
        rows = _iter_sheet_rows(wb, engine, "Open Positions")
    finally:
        try:
            wb.close()
        except Exception:
            pass

    if not rows:
        return []

    header: list[str] = []
    raw: list[tuple] = []
    for row in rows:
        if not header and (
            str(row[0]).strip().lower() == "product"
            and len(row) > 1 and str(row[1]).strip().lower() == "instrument/position"
        ):
            header = [str(c).strip() if c is not None else "" for c in row]
            continue
        if header:
            raw.append(row)

    if not header:
        return []

    col = {name.lower(): i for i, name in enumerate(header) if name}
    idx_ticker = col.get("ticker")
    idx_type = col.get("type")
    idx_volume = col.get("volume")
    idx_open_price = col.get("open price")
    idx_open_time = col.get("open time (utc)")

    transactions: list[dict] = []
    for row in raw:
        ticker = row[idx_ticker] if idx_ticker is not None and idx_ticker < len(row) else None
        op_type = row[idx_type] if idx_type is not None and idx_type < len(row) else None
        volume_val = row[idx_volume] if idx_volume is not None and idx_volume < len(row) else None
        open_price_val = row[idx_open_price] if idx_open_price is not None and idx_open_price < len(row) else None
        open_time_val = row[idx_open_time] if idx_open_time is not None and idx_open_time < len(row) else None

        if not ticker or not op_type or str(op_type).strip().upper() != "BUY":
            continue

        volume = _to_float(volume_val)
        if volume <= 0:
            continue

        open_time = _parse_datetime(open_time_val, assume_utc=True, to_local=True)
        if not open_time:
            continue

        price = _to_float(open_price_val)
        translated = translate_ticker(str(ticker), rules)
        purchase = round(volume * price, 8) if price > 0 else 0.0

        # Detect spinoff: near-zero open price (e.g., 0.0 or 0.001) indicates zero-cost acquisition
        is_spinoff = price >= 0 and price < 0.01

        entries = [
            LedgerEntry(ticker=translated, amount=round(volume, 8)),
            LedgerEntry(ticker=currency, amount=round(-abs(purchase), 8)),
        ]
        tx = Transaction(date=open_time.strftime("%Y-%m-%d"), entries=entries)
        d = tx.to_dict()
        if is_spinoff:
            d["_is_spinoff"] = True
        transactions.append(d)

    transactions.sort(key=lambda r: r["date"])
    log.info("Parsed %d open position BUY entries", len(transactions))
    return transactions


# ─────────────────────────────────────────────────────────────────────────────
# 3. Position Aggregation & Balance VWAP Price Update
# ─────────────────────────────────────────────────────────────────────────────

def fix_avg_prices_from_open_positions(file_path: str | Path, currency: str) -> None:
    """Override avg_price in balance.json with real broker values from Open Positions.

    Computes volume-weighted average open price per ticker from the Open Positions sheet.
    """
    currency = currency.upper()
    rules = cfg_module.load().get("ticker_rules", [])

    wb, engine = _open_workbook(file_path)
    try:
        rows = _iter_sheet_rows(wb, engine, "Open Positions")
    finally:
        try:
            wb.close()
        except Exception:
            pass

    if not rows:
        return

    header: list[str] = []
    raw: list[tuple] = []
    for row in rows:
        if not header and (
            str(row[0]).strip().lower() == "product"
            and len(row) > 1 and str(row[1]).strip().lower() == "instrument/position"
        ):
            header = [str(c).strip() if c is not None else "" for c in row]
            continue
        if header:
            raw.append(row)

    if not header:
        return

    col = {name.lower(): i for i, name in enumerate(header) if name}
    idx_ticker = col.get("ticker")
    idx_type = col.get("type")
    idx_volume = col.get("volume")
    idx_open_price = col.get("open price")

    agg: dict[str, dict[str, float]] = {}
    for row in raw:
        ticker = row[idx_ticker] if idx_ticker is not None and idx_ticker < len(row) else None
        op_type = row[idx_type] if idx_type is not None and idx_type < len(row) else None
        volume_val = row[idx_volume] if idx_volume is not None and idx_volume < len(row) else None
        open_price_val = row[idx_open_price] if idx_open_price is not None and idx_open_price < len(row) else None

        if not ticker or not op_type or str(op_type).strip().upper() != "BUY":
            continue

        volume = _to_float(volume_val)
        if volume <= 0:
            continue

        price = _to_float(open_price_val)
        translated = translate_ticker(str(ticker), rules)
        if translated.upper() in storage.SUPPORTED_CURRENCIES:
            continue

        if translated not in agg:
            agg[translated] = {"total_cost": 0.0, "total_vol": 0.0}
        agg[translated]["total_cost"] += volume * price
        agg[translated]["total_vol"] += volume

    if not agg:
        return

    balance = storage.load_balance()
    updated = 0
    for ticker, data in agg.items():
        if data["total_vol"] <= 0:
            continue
        real_avg = data["total_cost"] / data["total_vol"]
        if ticker in balance and balance[ticker]["amount"] > 1e-9:
            old_avg = balance[ticker]["avg_price"]
            balance[ticker]["avg_price"] = round(real_avg, 6)
            if abs(old_avg - real_avg) > 0.01:
                log.info(
                    "Fixed avg_price for %s: %.4f -> %.4f (from open positions)",
                    ticker, old_avg, real_avg,
                )
            updated += 1

    if updated:
        storage.save_balance(balance)
        log.info("Updated avg_price for %d tickers from open positions", updated)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Multi-Sheet Reconciliation & Import Flow
# ─────────────────────────────────────────────────────────────────────────────

def _reconcile_corporate_actions(
    cash_transactions: list[dict],
    positions: list[dict],
    label: str,
    spinoff_shares: dict[tuple[str, str], float] | None = None,
) -> tuple[list[dict], dict[tuple[str, str], float]]:
    """Reconciles position buys against cash operations.

    Deduplicates regular buys; keeps corporate actions (splits, spinoffs)
    where position share volume exceeds cash operations volume.

    Also handles sells of spinoff shares: if Cash Operations has a "Stock sell"
    for shares that were added as zero-cost spinoff, remove the share leg
    from that sell (keep only cash proceeds) to avoid negative share balances.

    Args:
        spinoff_shares: Mutable dict tracking spinoff shares added from PREVIOUS
                       sources only. Key: (date, ticker) -> shares added.
                       Pass the same dict across multiple calls to prevent
                       duplicate spinoffs from different sources (Closed + Open).
                       This function will update it with spinoffs from this source.
    """
    if spinoff_shares is None:
        spinoff_shares = {}

    cash_volumes: dict[tuple[str, str], float] = {}
    cash_sells: dict[tuple[str, str], float] = {}
    for rec in cash_transactions:
        for e in rec["entries"]:
            ticker = e["ticker"].upper()
            if ticker in storage.SUPPORTED_CURRENCIES:
                continue
            amt = float(e["amount"])
            if amt > 0:
                key = (rec["date"], ticker)
                cash_volumes[key] = cash_volumes.get(key, 0.0) + amt
            elif amt < 0:
                key = (rec["date"], ticker)
                cash_sells[key] = cash_sells.get(key, 0.0) + abs(amt)

    reconciled_transactions = list(cash_transactions)
    # Track spinoffs added in THIS source (not yet in spinoff_shares)
    source_spinoffs: dict[tuple[str, str], float] = {}

    for rec in positions:
        share_entry = rec["entries"][0]
        share_ticker = share_entry["ticker"].upper()
        position_volume = float(share_entry["amount"])
        date_key = rec["date"]
        cash_vol = cash_volumes.get((date_key, share_ticker), 0.0)
        # Subtract spinoff shares from PREVIOUS sources only (for spinoff dedup).
        # Splits are not tracked in spinoff_shares, so they can be added from both sources.
        spinoff_already = spinoff_shares.get((date_key, share_ticker), 0.0)
        
        # Only dedup cross-source if volumes are nearly equal (same lot in both sources).
        # If volumes differ significantly, they're different lots — don't subtract.
        if spinoff_already > 0 and abs(position_volume - spinoff_already) / max(position_volume, spinoff_already) > 0.1:
            spinoff_already = 0.0
            
        diff = position_volume - cash_vol - spinoff_already
        if diff < 1e-6:
            continue

        # Detect spinoff: near-zero price (spinoff) or explicit comment
        is_spinoff = rec.get("_is_spinoff", False)

        if is_spinoff:
            log.warning(
                "Corporate action detected: %s has %s shares with no buy "
                "in cash operations — auto-inserting zero-cost acquisition "
                "of %s shares on %s (source: %s). "
                "Adjust cost basis later if needed.",
                share_ticker, round(position_volume, 4), round(diff, 4),
                rec["date"], label,
            )
        else:
            log.info(
                "Split adjustment detected: %s has %s shares vs %.4f in Cash Ops "
                "— adding %.4f shares on %s (source: %s).",
                share_ticker, round(position_volume, 4), round(cash_vol, 4),
                round(diff, 4), rec["date"], label,
            )

        entries = []
        for e in rec["entries"]:
            if e["ticker"].upper() == share_ticker:
                entries.append({"ticker": e["ticker"], "amount": round(diff, 8)})
            elif e["ticker"].upper() in storage.SUPPORTED_CURRENCIES:
                entries.append({"ticker": e["ticker"], "amount": 0.0})
            else:
                entries.append({"ticker": e["ticker"], "amount": e["amount"]})

        reconciled_transactions.append({"date": rec["date"], "entries": entries})
        # Track spinoffs in source_spinoffs for cross-source dedup.
        # Splits are NOT tracked, so they can be added from both sources if needed.
        if is_spinoff:
            source_spinoffs[(date_key, share_ticker)] = source_spinoffs.get((date_key, share_ticker), 0.0) + diff

    # Merge this source's spinoffs into the shared dict for next source
    for key, val in source_spinoffs.items():
        spinoff_shares[key] = spinoff_shares.get(key, 0.0) + val

    return reconciled_transactions, spinoff_shares


def import_xtb(file_path: str | Path, currency: str) -> dict:
    """Validate, parse all sheets, reconcile corporate actions, and persist into the ledger."""
    log.info("=== XTB import: %s (currency=%s) ===", file_path, currency)
    valid, msg = validate_xtb_file(file_path)
    if not valid:
        log.error("Validation failed: %s", msg)
        return {"success": False, "error": msg}

    transactions = parse_xtb_excel(file_path, currency)
    closed_buys = parse_closed_positions(file_path, currency)
    open_buys = parse_open_positions(file_path, currency)

    # Pass spinoff_shares between calls to prevent duplicate spinoffs
    # from Closed + Open Positions (same spinoff can appear in both).
    # Key: (date, ticker) -> shares added.
    spinoff_shares: dict[tuple[str, str], float] = {}
    transactions, spinoff_shares = _reconcile_corporate_actions(
        transactions, closed_buys, "closed positions", spinoff_shares
    )
    transactions, _ = _reconcile_corporate_actions(
        transactions, open_buys, "open positions", spinoff_shares
    )

    from services.importers.base import ingest_transactions

    result = ingest_transactions(transactions)
    return result.to_dict()
