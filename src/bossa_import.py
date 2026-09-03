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
import logging
import re
from pathlib import Path

import storage
import config as cfg_module
from ledger_core import get_all_transactions
from isin_resolve import resolve_isins_with_names

log = logging.getLogger(__name__)

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
    log.info("Parsing %s (currency=%s)", file_path, currency)

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

        elif "dywidenda" in op_title.lower():
            # Dividend payment — credit cash, no stock leg
            entries.append({"ticker": waluta or currency, "amount": round(abs(kwota), 8)})

        if entries:
            transactions.append({"date": date_str, "entries": entries})

    transactions.sort(key=lambda r: r["date"])

    merged: list[dict] = []
    for rec in transactions:
        if merged and merged[-1]["date"] == rec["date"]:
            merged[-1]["entries"].extend(rec["entries"])
        else:
            merged.append({"date": rec["date"], "entries": list(rec["entries"])})

    log.info("Parsed %d raw transactions, merged to %d daily records", len(transactions), len(merged))
    log.info("Unresolved ISINs: %d", len(still_unresolved))

    return merged, still_unresolved


def import_bossa(file_path: str | Path, currency: str, progress_cb=None) -> dict:
    log.info("=== BOSSA import: %s (currency=%s) ===", file_path, currency)
    valid, msg = validate_bossa_file(file_path)
    if not valid:
        log.error("Validation failed: %s", msg)
        return {"success": False, "error": msg}

    transactions, unresolved = parse_bossa_csv(file_path, currency, progress_cb=progress_cb)

    # Include existing ledger balance so manually-added corporate-action
    # entries (split/spin-off) cover sells from the broker statement
    starting: dict[str, float] = {}
    for rec in get_all_transactions():
        for e in rec["entries"]:
            t = e["ticker"].upper()
            if t in storage.SUPPORTED_CURRENCIES:
                continue
            starting[t] = starting.get(t, 0.0) + float(e["amount"])

    # Auto-fix negative positions (e.g. corporate actions where the broker
    # statement doesn't record the acquisition of new shares).
    # Inserts a zero-cost buy on the date the position first went negative.
    from ledger_core import auto_fix_negative_positions
    fixed = auto_fix_negative_positions(transactions, starting_balance=starting)
    if fixed:
        log.info(
            "Auto-fixed %d negative position(s) from corporate action: %s",
            len(fixed),
            ", ".join(f"{t} ({n} shares)" for t, n, _ in fixed),
        )

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
    result = {"success": True, "imported": imported, "skipped": skipped}
    if unresolved:
        lines = [f"  {isin} ({name})" for isin, name in sorted(unresolved.items())]
        result["error"] = "Could not resolve ticker for:\n" + "\n".join(lines)
    return result
