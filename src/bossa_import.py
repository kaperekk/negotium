"""
bossa_import.py — BOSSA broker statement importer

Parses "Historia finansowa" CSV exports from BOSSA (Polish broker) and
converts rows into Negotium transaction format.

CSV format (semicolon-separated):
  data;tytuł operacji;szczegóły;kwota;waluta

Trade details format:
  {Name} ({ISIN}) {qty} x {price} {ccy} nr {order}

Operation types:
  Rozliczenie transakcji kupna:     → buy  (kwota < 0)
  Rozliczenie transakcji sprzedaży: → sell (kwota > 0)
  Wymiana waluty {src}/{tgt} {rate} → FX swap (two entries)
  Przelew do DM BOŚ                 → deposit (account_operation)
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import storage
import config as cfg_module
from transactions import get_all_transactions
from isin_resolve import resolve_isins_with_names

DETAILS_RE = re.compile(
    r"^(.+?)\s*\(([A-Z0-9]{12})\)\s+"
    r"([\d.,]+)\s*x\s*([\d.,]+)\s+(\w{3})\s+nr\s+\S+$"
)
FX_RE = re.compile(r"Wymiana waluty (\w{3})/(\w{3})\s+([\d.,]+)")


def _read_csv_text(file_path: str | Path) -> str:
    raw = Path(file_path).read_bytes()
    for enc in ("utf-8", "windows-1250", "iso-8859-2", "cp1252"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def validate_bossa_file(file_path: str | Path) -> tuple[bool, str]:
    try:
        text = _read_csv_text(file_path)
    except Exception as e:
        return False, f"Cannot open file: {e}"

    lines = text.strip().splitlines()
    if not lines:
        return False, "Empty file."

    header = lines[0]
    actual = {col.strip().lower() for col in header.split(";")}
    has_data = any("data" in col for col in actual)
    has_kwota = any("kwota" in col for col in actual)
    has_waluta = any("waluta" in col for col in actual)
    if not (has_data and has_kwota and has_waluta):
        return False, "Missing required columns (data, kwota, waluta)."

    return True, "Valid BOSSA statement."


def _parse_float(val: str) -> float | None:
    if not val:
        return None
    val = val.strip().replace(",", ".")
    try:
        return float(val)
    except ValueError:
        return None


def parse_bossa_csv(file_path: str | Path, currency: str, progress_cb=None) -> list[dict]:
    currency = currency.upper()

    text = _read_csv_text(file_path)
    reader = csv.reader(io.StringIO(text), delimiter=";")

    header = next(reader, None)
    if not header:
        return [], {}

    raw_rows: list[list[str]] = []
    isin_to_papier: dict[str, str] = {}
    for row in reader:
        if len(row) < 5:
            continue
        raw_rows.append(row)
        details = row[2].strip() if len(row) > 2 else ""
        m = DETAILS_RE.match(details)
        if m:
            papier, isin = m.group(1).strip(), m.group(2)
            isin_to_papier[isin] = papier

    resolved, still_unresolved = resolve_isins_with_names(isin_to_papier, progress_cb=progress_cb)

    transactions: list[dict] = []

    for row in raw_rows:
        date_str = row[0].strip()
        op_title = row[1].strip() if len(row) > 1 else ""
        details = row[2].strip() if len(row) > 2 else ""
        kwota_str = row[3].strip() if len(row) > 3 else ""
        waluta = row[4].strip().upper() if len(row) > 4 else ""

        kwota = _parse_float(kwota_str)
        if kwota is None:
            continue

        entries: list[dict] = []

        if "kupna" in op_title.lower():
            m = DETAILS_RE.match(details)
            if not m:
                continue
            isin = m.group(2)
            qty = _parse_float(m.group(3))
            ticker = resolved.get(isin)
            if not ticker:
                continue
            if qty is not None:
                entries.append({"ticker": ticker, "amount": round(qty, 8)})
            entries.append({"ticker": waluta or currency, "amount": round(kwota, 8)})

        elif "sprzeda" in op_title.lower():
            m = DETAILS_RE.match(details)
            if not m:
                continue
            isin = m.group(2)
            qty = _parse_float(m.group(3))
            ticker = resolved.get(isin)
            if not ticker:
                continue
            if qty is not None:
                entries.append({"ticker": ticker, "amount": round(-qty, 8)})
            entries.append({"ticker": waluta or currency, "amount": round(abs(kwota), 8)})

        elif "wymiana waluty" in op_title.lower():
            entries.append({"ticker": waluta or currency, "amount": round(kwota, 8),
                            "account_operation": True})

        elif "przelew" in op_title.lower() or "zwrot" in op_title.lower():
            entries.append({"ticker": waluta or currency, "amount": round(kwota, 8),
                            "account_operation": True})

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

    return merged, still_unresolved


def _fix_negative_positions(transactions: list[dict], currency: str) -> None:
    balance: dict[str, float] = {}
    for rec in transactions:
        for e in rec["entries"]:
            ticker = e["ticker"].upper()
            if ticker in storage.SUPPORTED_CURRENCIES:
                continue
            balance[ticker] = balance.get(ticker, 0.0) + float(e["amount"])

    for ticker, amt in balance.items():
        if amt < -1e-9:
            buy_shares = round(abs(amt), 8)
            transactions.append({
                "date": transactions[0]["date"] if transactions else "2000-01-01",
                "entries": [
                    {"ticker": ticker, "amount": buy_shares},
                    {"ticker": currency, "amount": -0.01},
                ],
            })


def _existing_keys() -> set[tuple[str, str, float]]:
    keys: set[tuple[str, str, float]] = set()
    for rec in get_all_transactions():
        for e in rec["entries"]:
            keys.add((rec["date"], e["ticker"].upper(), round(e["amount"], 8)))
    return keys


def import_bossa(file_path: str | Path, currency: str, progress_cb=None) -> dict:
    valid, msg = validate_bossa_file(file_path)
    if not valid:
        return {"success": False, "error": msg}

    transactions, unresolved = parse_bossa_csv(file_path, currency, progress_cb=progress_cb)
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

    result = {"success": True, "imported": imported, "skipped": skipped}
    if unresolved:
        lines = [f"  {isin} ({name})" for isin, name in sorted(unresolved.items())]
        result["error"] = "Could not resolve ticker for:\n" + "\n".join(lines)
    return result
