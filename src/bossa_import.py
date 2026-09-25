"""
bossa_import.py — Structured BOSSA broker statement importer

Parses "Historia finansowa" CSV exports from BOSSA (Polish broker) and
converts rows into Negotium Transaction/LedgerEntry domain models.

CSV format (semicolon-separated):
  data;tytuł operacji;szczegóły;kwota;waluta

Trade details format:
  {Name} ({ISIN}) {qty} x {price} {ccy} nr {order}

Operation types:
  Rozliczenie transakcji kupna:     → buy  (kwota < 0)
  Rozliczenie transakcji sprzedaży: → sell (kwota > 0)
  Wymiana waluty {src}/{tgt} {rate} → FX swap (account_operation)
  Przelew do DM BOŚ / zwrot         → deposit/withdrawal (account_operation)
  Dywidenda                         → dividend cash credit
"""
from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path
from typing import Any, Callable

import storage
from domain.models import LedgerEntry, Transaction
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
    """Validate that the file can be opened and has required BOSSA CSV header columns."""
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


def _parse_float(val: str | None) -> float | None:
    if not val:
        return None
    val = val.strip().replace(",", ".")
    try:
        return float(val)
    except ValueError:
        return None


def _parse_bossa_raw_transactions(
    raw_rows: list[list[str]],
    resolved_isins: dict[str, str],
    currency: str,
) -> list[Transaction]:
    """Parse raw CSV rows into a list of structured Transaction objects."""
    transactions: list[Transaction] = []

    for row in raw_rows:
        date_str = row[0].strip()
        op_title = row[1].strip() if len(row) > 1 else ""
        details = row[2].strip() if len(row) > 2 else ""
        kwota_str = row[3].strip() if len(row) > 3 else ""
        waluta = row[4].strip().upper() if len(row) > 4 else ""

        kwota = _parse_float(kwota_str)
        if kwota is None:
            continue

        entries: list[LedgerEntry] = []
        op_title_lower = op_title.lower()
        effective_currency = waluta or currency

        if "kupna" in op_title_lower:
            m = DETAILS_RE.match(details)
            if not m:
                continue
            isin = m.group(2)
            qty = _parse_float(m.group(3))
            ticker = resolved_isins.get(isin)
            if not ticker:
                continue
            if qty is not None:
                entries.append(LedgerEntry(ticker=ticker, amount=round(qty, 8)))
            entries.append(LedgerEntry(ticker=effective_currency, amount=round(kwota, 8)))

        elif "sprzeda" in op_title_lower:
            m = DETAILS_RE.match(details)
            if not m:
                continue
            isin = m.group(2)
            qty = _parse_float(m.group(3))
            ticker = resolved_isins.get(isin)
            if not ticker:
                continue
            if qty is not None:
                entries.append(LedgerEntry(ticker=ticker, amount=round(-qty, 8)))
            entries.append(LedgerEntry(ticker=effective_currency, amount=round(abs(kwota), 8)))

        elif "wymiana waluty" in op_title_lower:
            entries.append(LedgerEntry(ticker=effective_currency, amount=round(kwota, 8), account_operation=True))

        elif "przelew" in op_title_lower or "zwrot" in op_title_lower:
            entries.append(LedgerEntry(ticker=effective_currency, amount=round(kwota, 8), account_operation=True))

        elif "dywidenda" in op_title_lower:
            entries.append(LedgerEntry(ticker=effective_currency, amount=round(abs(kwota), 8)))

        if entries:
            transactions.append(Transaction(date=date_str, entries=entries))

    transactions.sort(key=lambda t: t.date)
    return transactions


def parse_bossa_csv(
    file_path: str | Path,
    currency: str,
    progress_cb: Callable[[float, str], None] | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """Parse BOSSA CSV file and return merged daily transactions (as dicts) and unresolved ISINs."""
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

    # Dynamic lookup via isin_resolve module (allows mock injection in tests)
    import bossa_import
    resolve_fn = getattr(bossa_import, "resolve_isins_with_names", resolve_isins_with_names)
    resolved, still_unresolved = resolve_fn(isin_to_papier, progress_cb=progress_cb)

    raw_txns = _parse_bossa_raw_transactions(raw_rows, resolved, currency)

    # Merge entries occurring on the same date
    merged: list[Transaction] = []
    for tx in raw_txns:
        if merged and merged[-1].date == tx.date:
            merged[-1].entries.extend(tx.entries)
        else:
            merged.append(Transaction(date=tx.date, entries=list(tx.entries)))

    log.info("Parsed %d raw transactions, merged to %d daily records", len(raw_txns), len(merged))
    log.info("Unresolved ISINs: %d", len(still_unresolved))

    return [t.to_dict() for t in merged], still_unresolved


def import_bossa(
    file_path: str | Path,
    currency: str,
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Validate, parse, deduplicate, and ingest BOSSA CSV transactions into the active ledger."""
    log.info("=== BOSSA import: %s (currency=%s) ===", file_path, currency)
    valid, msg = validate_bossa_file(file_path)
    if not valid:
        log.error("Validation failed: %s", msg)
        return {"success": False, "error": msg}

    transactions, unresolved = parse_bossa_csv(file_path, currency, progress_cb=progress_cb)

    from services.importers.base import ingest_transactions

    result = ingest_transactions(transactions)
    res_dict = result.to_dict()
    if unresolved:
        lines = [f"  {isin} ({name})" for isin, name in sorted(unresolved.items())]
        res_dict["error"] = "Could not resolve ticker for:\n" + "\n".join(lines)
    return res_dict
