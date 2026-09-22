"""
xtb_import.py — XTB broker statement importer

Parses the "Cash Operations" sheet from XTB Excel exports and converts
rows into Negotium transaction format.

Comment patterns:
  Stock purchase: "OPEN BUY 4/4.138 @ 48.3060"  → 4 shares
                  "OPEN BUY 0.1367 @ 1462.60"   → 0.1367 shares
  Stock sell:     "CLOSE BUY 3.9657/14.7171 @ 123.3700" → 3.9657 shares
"""
from __future__ import annotations

import logging
import re
import warnings
from datetime import datetime
from pathlib import Path

import openpyxl

import storage
import pandas as pd

import config as cfg_module
from ledger_core import get_all_transactions
from ticker_translate import translate_ticker

log = logging.getLogger(__name__)

SHARE_RE = re.compile(r"(?:OPEN|CLOSE)\s+BUY\s+([\d.]+)")


def _parse_shares(comment: str | None) -> float | None:
    if not comment:
        return None
    m = SHARE_RE.search(comment)
    return float(m.group(1)) if m else None


# XTB statements occasionally ship with a minimal stylesheet that lacks the
# default ("Normal") cell style. openpyxl warns about it and falls back to its
# own defaults — harmless, so we filter just that message to keep the terminal
# (and the app log) clean. The warning is identical under all supported
# openpyxl versions; anchored to the exact wording openpyxl 3.1.x emits.
_OPENPYXL_NO_DEFAULT_STYLE = "Workbook contains no default style, apply openpyxl's default"


def _open_workbook(file_path: str | Path):
    """Try openpyxl first, fall back to pandas/calamine if the sheet is unreadable.

    The returned object (an openpyxl ``Workbook`` or a pandas ``ExcelFile``)
    is owned by the caller, which must always close it — see the ``finally``
    blocks in ``validate_xtb_file`` / ``parse_xtb_excel``.
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


def validate_xtb_file(file_path: str | Path) -> tuple[bool, str]:
    try:
        wb, engine = _open_workbook(file_path)
    except Exception as e:
        return False, f"Cannot open file: {e}"

    try:
        if engine == "openpyxl":
            if "Cash Operations" not in wb.sheetnames:
                return False, "Missing 'Cash Operations' sheet."
            ws = wb["Cash Operations"]
            header_row = None
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if row[0] == "Type":
                    header_row = row
                    break
        else:
            if "Cash Operations" not in wb.sheet_names:
                return False, "Missing 'Cash Operations' sheet."
            df = wb.parse("Cash Operations", header=None, nrows=10)
            header_row = None
            for _, row in df.iterrows():
                if row.iloc[0] == "Type":
                    header_row = tuple(row)
                    break

        if not header_row:
            return False, "Cannot find column headers (Type, Ticker, ...) in Cash Operations."

        required = {"Type", "Ticker", "Amount", "Time"}
        actual = {str(c) for c in header_row if c and str(c) != "nan"}
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


def parse_xtb_excel(file_path: str | Path, currency: str) -> list[dict]:
    currency = currency.upper()
    rules = cfg_module.load().get("ticker_rules", [])
    log.info("Parsing %s (currency=%s)", file_path, currency)

    wb, engine = _open_workbook(file_path)

    raw: list[dict] = []
    header: list[str] = []

    try:
        if engine == "openpyxl":
            ws = wb["Cash Operations"]
            rows_iter = ws.iter_rows(values_only=True)
            for i, row in enumerate(rows_iter):
                if not header and any(str(c).strip().lower() == "type" for c in row if c):
                    header = [str(c) if c else "" for c in row]
                    continue
                if header:
                    raw.append(row)
        else:
            df = wb.parse("Cash Operations", header=None)
            # Find header row to skip metadata rows
            header_idx = 0
            for idx, row in df.iterrows():
                if row.iloc[0] == "Type":
                    header_idx = idx + 1
                    header = [str(c) if c else "" for c in row]
                    break
            df.columns = df.iloc[header_idx - 1].values
            df = df.iloc[header_idx:].reset_index(drop=True)
            raw = [tuple(row) for _, row in df.iterrows()]
    finally:
        try:
            wb.close()
        except Exception:
            pass

    # Build column index map from header (handles different XTB export layouts)
    col = {name.strip().lower(): i for i, name in enumerate(header) if name.strip()}
    log.info("Columns detected: %s", list(col.keys()))

    def _col(name: str) -> int | None:
        return col.get(name.lower())

    idx_type     = _col("type")
    idx_ticker   = _col("ticker")
    idx_time     = _col("time")
    idx_amount   = _col("amount")
    idx_comment  = _col("comment")

    skipped_no_type = 0
    skipped_no_amount = 0
    skipped_no_time = 0
    skipped_unknown_type = 0
    transactions: list[dict] = []
    seen_types: dict[str, int] = {}
    for row in raw:
        op_type     = row[idx_type]     if idx_type     is not None and idx_type     < len(row) else None
        ticker      = row[idx_ticker]   if idx_ticker   is not None and idx_ticker   < len(row) else None
        time_val    = row[idx_time]     if idx_time     is not None and idx_time     < len(row) else None
        amount      = row[idx_amount]   if idx_amount   is not None and idx_amount   < len(row) else None
        comment     = row[idx_comment]  if idx_comment  is not None and idx_comment  < len(row) else None

        if not op_type or op_type == "Total":
            skipped_no_type += 1
            continue
        if amount is None or (isinstance(amount, float) and pd.isna(amount)):
            skipped_no_amount += 1
            continue

        seen_types[op_type] = seen_types.get(op_type, 0) + 1

        if isinstance(time_val, str):
            try:
                time_val = datetime.fromisoformat(time_val)
            except ValueError:
                skipped_no_time += 1
                continue
        if not isinstance(time_val, datetime):
            skipped_no_time += 1
            continue

        date_str = time_val.strftime("%Y-%m-%d")
        entries: list[dict] = []

        if op_type == "Stock purchase":
            shares = _parse_shares(comment)
            if shares and shares > 0:
                entries.append({"ticker": translate_ticker(str(ticker), rules), "amount": round(shares, 8)})
                entries.append({"ticker": currency, "amount": round(float(amount), 8)})

        elif op_type == "Stock sell":
            shares = _parse_shares(comment)
            if shares and shares > 0:
                entries.append({"ticker": translate_ticker(str(ticker), rules), "amount": round(-shares, 8)})
                entries.append({"ticker": currency, "amount": round(float(amount), 8)})

        elif op_type in ("Deposit", "Withdrawal", "IKE deposit", "IKE withdrawal"):
            entries.append({"ticker": currency, "amount": round(float(amount), 8),
                            "account_operation": True})

        elif op_type == "Transfer":
            entries.append({"ticker": currency, "amount": round(float(amount), 8),
                            "account_operation": True})

        elif op_type in ("Dividend", "Dividend from foreign company on PL market"):
            entries.append({"ticker": currency, "amount": round(float(amount), 8)})

        elif op_type in ("Free funds interest", "Free funds interest tax",
                          "Withholding tax", "Commission", "Fractional shares"):
            if float(amount) != 0:
                entries.append({"ticker": currency, "amount": round(float(amount), 8)})

        elif float(amount) != 0:
            log.warning(
                "XTB row type not recognised — skipped: %r (%.2f %s on %s, comment: %s)",
                op_type, float(amount), currency, date_str, str(comment)[:80],
            )

        if entries:
            transactions.append({"date": date_str, "entries": entries})

    log.info("Row types seen: %s", dict(seen_types))
    log.info("Skipped: %d no type/total, %d no amount, %d no valid time",
             skipped_no_type, skipped_no_amount, skipped_no_time)

    transactions.sort(key=lambda r: r["date"])

    merged: list[dict] = []
    for rec in transactions:
        if merged and merged[-1]["date"] == rec["date"]:
            merged[-1]["entries"].extend(rec["entries"])
        else:
            merged.append({"date": rec["date"], "entries": list(rec["entries"])})

    log.info("Parsed %d raw transactions, merged to %d daily records", len(transactions), len(merged))

    log.info("Final: %d records with %d total entries", len(merged), sum(len(r["entries"]) for r in merged))

    return merged



def _existing_entry_counts() -> dict[tuple[str, str, float], int]:
    from ledger_core import existing_entry_counts
    return existing_entry_counts()


def parse_closed_positions(file_path: str | Path, currency: str) -> list[dict]:
    """Parse the 'Closed Positions' sheet into transactions.

    Each BUY row becomes an acquisition transaction with the open date,
    volume (shares), and purchase value. SELL rows are skipped — they are
    already represented as 'Stock sell' entries in Cash Operations.
    """
    currency = currency.upper()
    rules = cfg_module.load().get("ticker_rules", [])
    log.info("Parsing closed positions from %s", file_path)

    wb, engine = _open_workbook(file_path)
    try:
        if engine == "openpyxl":
            if "Closed Positions" not in wb.sheetnames:
                log.info("No 'Closed Positions' sheet — skipping")
                return []
            ws = wb["Closed Positions"]
            rows_iter = ws.iter_rows(values_only=True)
        else:
            if "Closed Positions" not in wb.sheet_names:
                log.info("No 'Closed Positions' sheet — skipping")
                return []
            df = wb.parse("Closed Positions", header=None)
            header_idx = 0
            for idx, row in df.iterrows():
                if row.iloc[0] == "Instrument":
                    header_idx = idx + 1
                    break
            df.columns = df.iloc[header_idx - 1].values
            df = df.iloc[header_idx:].reset_index(drop=True)
            rows_iter = [tuple(row) for _, row in df.iterrows()]

        header: list[str] = []
        raw: list[tuple] = []
        for row in rows_iter:
            if not header and any(str(c).strip().lower() == "instrument" for c in row if c):
                header = [str(c) if c else "" for c in row]
                continue
            if header:
                raw.append(row)
    finally:
        try:
            wb.close()
        except Exception:
            pass

    if not header:
        log.warning("No header found in Closed Positions")
        return []

    col = {name.strip().lower(): i for i, name in enumerate(header) if name.strip()}
    idx_ticker = col.get("ticker")
    idx_type = col.get("type")
    idx_volume = col.get("volume")
    idx_open_price = col.get("open price")
    idx_open_time = col.get("open time (utc)")
    idx_purchase_value = col.get("purchase value")

    transactions: list[dict] = []
    for row in raw:
        ticker = row[idx_ticker] if idx_ticker is not None and idx_ticker < len(row) else None
        op_type = row[idx_type] if idx_type is not None and idx_type < len(row) else None
        volume = row[idx_volume] if idx_volume is not None and idx_volume < len(row) else None
        open_price = row[idx_open_price] if idx_open_price is not None and idx_open_price < len(row) else None
        open_time = row[idx_open_time] if idx_open_time is not None and idx_open_time < len(row) else None
        purchase_value = row[idx_purchase_value] if idx_purchase_value is not None and idx_purchase_value < len(row) else None

        if not ticker or not op_type or str(op_type).strip().upper() != "BUY":
            continue
        if volume is None or (isinstance(volume, float) and pd.isna(volume)):
            continue
        if open_time is None:
            continue

        if isinstance(open_time, str):
            try:
                open_time = datetime.fromisoformat(open_time)
            except ValueError:
                continue
        if not isinstance(open_time, datetime):
            continue

        volume = float(volume)
        if volume <= 0:
            continue

        purchase = float(purchase_value) if purchase_value is not None and not isinstance(purchase_value, str) else 0.0
        if isinstance(purchase_value, str):
            try:
                purchase = float(purchase_value)
            except ValueError:
                purchase = 0.0

        translated = translate_ticker(str(ticker), rules)
        entries: list[dict] = [
            {"ticker": translated, "amount": round(volume, 8)},
            {"ticker": currency, "amount": round(-abs(purchase), 8)},
        ]
        transactions.append({
            "date": open_time.strftime("%Y-%m-%d"),
            "entries": entries,
            "_source": "closed_positions",
            "_ticker_raw": str(ticker).upper(),
        })

    transactions.sort(key=lambda r: r["date"])
    log.info("Parsed %d closed position BUY entries", len(transactions))
    return transactions


def parse_open_positions(file_path: str | Path, currency: str) -> list[dict]:
    """Parse the 'Open Positions' sheet into acquisition transactions.

    Each BUY row with a valid open date becomes an acquisition transaction.
    Rows without an open time (summary rows, instrument headers) are skipped.
    """
    currency = currency.upper()
    rules = cfg_module.load().get("ticker_rules", [])
    log.info("Parsing open positions from %s", file_path)

    wb, engine = _open_workbook(file_path)
    try:
        if engine == "openpyxl":
            if "Open Positions" not in wb.sheetnames:
                log.info("No 'Open Positions' sheet — skipping")
                return []
            ws = wb["Open Positions"]
            rows_iter = ws.iter_rows(values_only=True)
        else:
            if "Open Positions" not in wb.sheet_names:
                log.info("No 'Open Positions' sheet — skipping")
                return []
            df = wb.parse("Open Positions", header=None)
            header_idx = 0
            for idx, row in df.iterrows():
                if row.iloc[0] == "Product" and row.iloc[1] == "Instrument/Position":
                    header_idx = idx + 1
                    break
            df.columns = df.iloc[header_idx - 1].values
            df = df.iloc[header_idx:].reset_index(drop=True)
            rows_iter = [tuple(row) for _, row in df.iterrows()]

        header: list[str] = []
        raw: list[tuple] = []
        for row in rows_iter:
            if not header and (
                str(row[0]).strip().lower() == "product"
                and str(row[1]).strip().lower() == "instrument/position"
            ):
                header = [str(c) if c else "" for c in row]
                continue
            if header:
                raw.append(row)
    finally:
        try:
            wb.close()
        except Exception:
            pass

    if not header:
        log.warning("No header found in Open Positions")
        return []

    col = {name.strip().lower(): i for i, name in enumerate(header) if name.strip()}
    idx_ticker = col.get("ticker")
    idx_type = col.get("type")
    idx_volume = col.get("volume")
    idx_open_price = col.get("open price")
    idx_open_time = col.get("open time (utc)")

    transactions: list[dict] = []
    for row in raw:
        ticker = row[idx_ticker] if idx_ticker is not None and idx_ticker < len(row) else None
        op_type = row[idx_type] if idx_type is not None and idx_type < len(row) else None
        volume = row[idx_volume] if idx_volume is not None and idx_volume < len(row) else None
        open_price = row[idx_open_price] if idx_open_price is not None and idx_open_price < len(row) else None
        open_time = row[idx_open_time] if idx_open_time is not None and idx_open_time < len(row) else None

        if not ticker or not op_type or str(op_type).strip().upper() != "BUY":
            continue
        if volume is None or (isinstance(volume, float) and pd.isna(volume)):
            continue
        if open_time is None:
            continue

        if isinstance(open_time, str):
            try:
                open_time = datetime.fromisoformat(open_time)
            except ValueError:
                continue
        if not isinstance(open_time, datetime):
            continue

        volume = float(volume)
        if volume <= 0:
            continue

        price = float(open_price) if open_price is not None and not isinstance(open_price, str) else 0.0
        if isinstance(open_price, str):
            try:
                price = float(open_price)
            except ValueError:
                price = 0.0

        translated = translate_ticker(str(ticker), rules)
        purchase = round(volume * price, 8) if price > 0 else 0.0
        entries: list[dict] = [
            {"ticker": translated, "amount": round(volume, 8)},
            {"ticker": currency, "amount": round(-abs(purchase), 8)},
        ]
        transactions.append({
            "date": open_time.strftime("%Y-%m-%d"),
            "entries": entries,
        })

    transactions.sort(key=lambda r: r["date"])
    log.info("Parsed %d open position BUY entries", len(transactions))
    return transactions


def fix_avg_prices_from_open_positions(file_path: str | Path, currency: str) -> None:
    """Override avg_price in balance.json with real broker values from Open Positions.

    Computes volume-weighted average open price per ticker from the Open Positions
    sheet and updates balance.json.  This replaces the approximated avg_price
    that _update_avg_prices() derives from Yahoo Finance closing prices.
    """
    currency = currency.upper()
    rules = cfg_module.load().get("ticker_rules", [])

    wb, engine = _open_workbook(file_path)
    try:
        if engine == "openpyxl":
            if "Open Positions" not in wb.sheetnames:
                return
            ws = wb["Open Positions"]
            rows_iter = ws.iter_rows(values_only=True)
        else:
            if "Open Positions" not in wb.sheet_names:
                return
            df = wb.parse("Open Positions", header=None)
            header_idx = 0
            for idx, row in df.iterrows():
                if row.iloc[0] == "Product" and row.iloc[1] == "Instrument/Position":
                    header_idx = idx + 1
                    break
            df.columns = df.iloc[header_idx - 1].values
            df = df.iloc[header_idx:].reset_index(drop=True)
            rows_iter = [tuple(row) for _, row in df.iterrows()]

        header: list[str] = []
        raw: list[tuple] = []
        for row in rows_iter:
            if not header and (
                str(row[0]).strip().lower() == "product"
                and str(row[1]).strip().lower() == "instrument/position"
            ):
                header = [str(c) if c else "" for c in row]
                continue
            if header:
                raw.append(row)
    finally:
        try:
            wb.close()
        except Exception:
            pass

    if not header:
        return

    col = {name.strip().lower(): i for i, name in enumerate(header) if name.strip()}
    idx_ticker = col.get("ticker")
    idx_type = col.get("type")
    idx_volume = col.get("volume")
    idx_open_price = col.get("open price")

    # Aggregate: total cost and total volume per translated ticker
    agg: dict[str, dict[str, float]] = {}
    for row in raw:
        ticker = row[idx_ticker] if idx_ticker is not None and idx_ticker < len(row) else None
        op_type = row[idx_type] if idx_type is not None and idx_type < len(row) else None
        volume = row[idx_volume] if idx_volume is not None and idx_volume < len(row) else None
        open_price = row[idx_open_price] if idx_open_price is not None and idx_open_price < len(row) else None

        if not ticker or not op_type or str(op_type).strip().upper() != "BUY":
            continue
        if volume is None or (isinstance(volume, float) and pd.isna(volume)):
            continue

        volume = float(volume)
        if volume <= 0:
            continue

        price = 0.0
        if open_price is not None:
            if isinstance(open_price, (int, float)):
                price = float(open_price)
            elif isinstance(open_price, str):
                try:
                    price = float(open_price)
                except ValueError:
                    pass

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


def import_xtb(file_path: str | Path, currency: str) -> dict:
    log.info("=== XTB import: %s (currency=%s) ===", file_path, currency)
    valid, msg = validate_xtb_file(file_path)
    if not valid:
        log.error("Validation failed: %s", msg)
        return {"success": False, "error": msg}

    transactions = parse_xtb_excel(file_path, currency)
    closed_buys = parse_closed_positions(file_path, currency)
    open_buys = parse_open_positions(file_path, currency)

    # Deduplicate position buys against cash operations.
    # Regular buys already appear in cash_ops; only keep corporate-action
    # acquisitions (spinoffs, splits) that cash_ops doesn't have.
    # Open/Closed Positions may show post-split quantities while Cash Ops
    # has pre-split quantities, so we compare volumes: only add the
    # difference when position volume exceeds cash ops volume.
    cash_volumes: dict[tuple[str, str], float] = {}
    for rec in transactions:
        for e in rec["entries"]:
            if e["ticker"].upper() in storage.SUPPORTED_CURRENCIES:
                continue
            if float(e["amount"]) > 0:
                key = (rec["date"], e["ticker"].upper())
                cash_volumes[key] = cash_volumes.get(key, 0.0) + float(e["amount"])

    def _add_uncovered(positions: list[dict], label: str) -> int:
        added = 0
        for rec in positions:
            share_entry = rec["entries"][0]
            share_ticker = share_entry["ticker"].upper()
            position_volume = float(share_entry["amount"])
            cash_vol = cash_volumes.get((rec["date"], share_ticker), 0.0)
            diff = position_volume - cash_vol
            if diff < 1e-6:
                continue
            log.warning(
                "Corporate action detected: %s has %s shares with no buy "
                "in cash operations — auto-inserting zero-cost acquisition "
                "of %s shares on %s (source: %s). "
                "Adjust cost basis later if needed.",
                share_ticker, round(position_volume, 4), round(diff, 4),
                rec["date"], label,
            )
            # Build entries: share entry gets the diff, currency entry is
            # zeroed out (split/spinoff shares have no cash leg).
            entries = []
            for e in rec["entries"]:
                if e["ticker"].upper() == share_ticker:
                    entries.append({"ticker": e["ticker"], "amount": round(diff, 8)})
                elif e["ticker"].upper() in storage.SUPPORTED_CURRENCIES:
                    entries.append({"ticker": e["ticker"], "amount": 0.0})
                else:
                    entries.append({"ticker": e["ticker"], "amount": e["amount"]})
            transactions.append({"date": rec["date"], "entries": entries})
            added += 1
        return added

    _add_uncovered(closed_buys, "closed positions")
    _add_uncovered(open_buys, "open positions")

    existing = _existing_entry_counts()

    imported = 0
    skipped = 0
    for rec in transactions:
        new_entries = []
        for e in rec["entries"]:
            key = (rec["date"], e["ticker"].upper(), round(float(e["amount"]), 8))
            if existing.get(key, 0) > 0:
                existing[key] -= 1
            else:
                new_entries.append(e)
        if new_entries:
            from ledger_core import add_transaction
            add_transaction(rec["date"], new_entries)
            imported += 1
        else:
            skipped += 1

    log.info("Result: %d imported, %d skipped (duplicates)", imported, skipped)
    return {"success": True, "imported": imported, "skipped": skipped}
