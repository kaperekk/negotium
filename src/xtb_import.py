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

import re
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl
import pandas as pd

import storage
import config as cfg_module
from transactions import get_all_transactions
from ticker_translate import translate_ticker

SHARE_RE = re.compile(r"(?:OPEN|CLOSE)\s+BUY\s+([\d.]+)")
TRANSFER_RATE_RE = re.compile(r"Exchange rate:\s*([\d.]+)")
TRANSFER_CURRENCY_RE = re.compile(r"Currency conversion,\s*\w+\s+to\s+(\w+)")


def _parse_shares(comment: str | None) -> float | None:
    if not comment:
        return None
    m = SHARE_RE.search(comment)
    return float(m.group(1)) if m else None


def _parse_transfer_rate(comment: str | None) -> float | None:
    if not comment:
        return None
    m = TRANSFER_RATE_RE.search(comment)
    return float(m.group(1)) if m else None


def _parse_transfer_target(comment: str | None) -> str | None:
    if not comment:
        return None
    m = TRANSFER_CURRENCY_RE.search(comment)
    return m.group(1).upper() if m else None


def _open_workbook(file_path: str | Path):
    """Try openpyxl first, fall back to pandas/xlrd if stylesheet is corrupt."""
    try:
        return openpyxl.load_workbook(file_path, data_only=True), "openpyxl"
    except Exception:
        pass
    try:
        xls = pd.ExcelFile(file_path, engine="openpyxl")
        return xls, "pandas"
    except Exception:
        pass
    xls = pd.ExcelFile(file_path, engine="calamine")
    return xls, "calamine"


def validate_xtb_file(file_path: str | Path) -> tuple[bool, str]:
    try:
        wb, engine = _open_workbook(file_path)
    except Exception as e:
        return False, f"Cannot open file: {e}"

    try:
        if engine == "openpyxl":
            if "Cash Operations" not in wb.sheetnames:
                wb.close()
                return False, "Missing 'Cash Operations' sheet."
            ws = wb["Cash Operations"]
            header_row = None
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if row[0] == "Type":
                    header_row = row
                    break
            wb.close()
        else:
            if "Cash Operations" not in wb.sheet_names:
                wb.close()
                return False, "Missing 'Cash Operations' sheet."
            df = wb.parse("Cash Operations", header=None, nrows=10)
            wb.close()
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


def parse_xtb_excel(file_path: str | Path, currency: str) -> list[dict]:
    currency = currency.upper()
    rules = cfg_module.load().get("ticker_rules", [])

    wb, engine = _open_workbook(file_path)

    raw: list[dict] = []

    if engine == "openpyxl":
        ws = wb["Cash Operations"]
        rows_iter = ws.iter_rows(values_only=True)
        for i, row in enumerate(rows_iter):
            if i < 5:
                continue
            raw.append(row)
        wb.close()
    else:
        df = wb.parse("Cash Operations", header=None)
        wb.close()
        # Find header row to skip metadata rows
        header_idx = 0
        for idx, row in df.iterrows():
            if row.iloc[0] == "Type":
                header_idx = idx + 1
                break
        df.columns = df.iloc[header_idx - 1].values
        df = df.iloc[header_idx:].reset_index(drop=True)
        raw = [tuple(row) for _, row in df.iterrows()]

    transactions: list[dict] = []
    for row in raw:
        op_type = row[0]
        ticker = row[1]
        time_val = row[3]
        amount = row[4]
        comment = row[6] if len(row) > 6 else None

        if not op_type or op_type == "Total":
            continue
        if amount is None or (isinstance(amount, float) and pd.isna(amount)):
            continue

        if isinstance(time_val, str):
            try:
                time_val = datetime.fromisoformat(time_val)
            except ValueError:
                continue
        if not isinstance(time_val, datetime):
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

        elif op_type in ("Deposit", "Withdrawal"):
            entries.append({"ticker": currency, "amount": round(float(amount), 8),
                            "account_operation": True})

        elif op_type == "Transfer":
            entries.append({"ticker": currency, "amount": round(float(amount), 8),
                            "account_operation": True})

        elif op_type == "Dividend":
            entries.append({"ticker": currency, "amount": round(float(amount), 8)})

        elif op_type in ("Free funds interest", "Free funds interest tax",
                          "Withholding tax"):
            entries.append({"ticker": currency, "amount": round(float(amount), 8)})

        if entries:
            transactions.append({"date": date_str, "entries": entries})

    transactions.sort(key=lambda r: r["date"])

    merged: list[dict] = []
    for rec in transactions:
        if merged and merged[-1]["date"] == rec["date"]:
            merged[-1]["entries"].extend(rec["entries"])
        else:
            merged.append({"date": rec["date"], "entries": list(rec["entries"])})

    _fix_negative_positions(merged, currency)

    return merged


def _fix_negative_positions(transactions: list[dict], currency: str) -> None:
    """If any stock/ETF ends negative, insert a buy of X shares for 0.01 cash."""
    from transactions import fix_negative_positions
    fix_negative_positions(transactions, currency)


def _existing_keys() -> set[tuple[str, str, float]]:
    from transactions import existing_keys
    return existing_keys()


def import_xtb(file_path: str | Path, currency: str) -> dict:
    valid, msg = validate_xtb_file(file_path)
    if not valid:
        return {"success": False, "error": msg}

    transactions = parse_xtb_excel(file_path, currency)
    existing = _existing_keys()

    imported = 0
    skipped = 0
    for rec in transactions:
        new_entries = [
            e for e in rec["entries"]
            if (rec["date"], e["ticker"].upper(), round(e["amount"], 8)) not in existing
        ]
        if new_entries:
            from transactions import add_transaction
            add_transaction(rec["date"], new_entries)
            imported += 1
        else:
            skipped += 1

    return {"success": True, "imported": imported, "skipped": skipped}
