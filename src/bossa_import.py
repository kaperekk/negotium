"""
bossa_import.py — Structured BOSSA broker statement importer

Parses "Historia finansowa" CSV exports from BOSSA (Polish broker) and
converts rows into Negotium Transaction/LedgerEntry domain models.

CSV format (semicolon-separated):
  data;tytuł operacji;szczegóły;kwota;waluta

The `data` column is normalised to ISO `YYYY-MM-DD` (BOSSA exports both
`2024-01-15` and `15.01.2024` depending on the account), and the `waluta`
column is authoritative for the cash leg of every row.

Trade details format:
  {Name} ({ISIN}) {qty} x {price} {ccy} nr {order}

Operation types:
  Rozliczenie transakcji kupna:      → buy  (qty > 0, cash < 0)
  Rozliczenie transakcji sprzedaży:  → sell (qty < 0, cash > 0)
  Wymiana waluty {src}/{tgt} {rate}  → FX swap: two unmarked cash legs
  Przelew do DM BOŚ                  → deposit (account_operation)
  Zwrot / Zwrot nadpłaty             → refund (account_operation)
  Dywidenda                          → dividend cash credit

Only real deposits and refunds are marked `account_operation`. Per the invested
rule (ARCHITECTURE.md), an FX swap is a conversion between two cash balances,
not new capital — marking it as a deposit would make the invested-capital
reference line jump by the traded amount and read the conversion as
performance.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from currencies import SUPPORTED_CURRENCIES
from domain.models import LedgerEntry, Transaction
from isin_resolve import resolve_isins_with_names
from services.importers.base import ingest_transactions

log = logging.getLogger(__name__)

# Amounts may group thousands with a regular, non-breaking or narrow space.
_NUM_CHARS = r"[\d.,  ]"
DETAILS_RE = re.compile(
    r"^(.+?)\s*\(([A-Z0-9]{12})\)\s+"
    rf"(\d{_NUM_CHARS}*?)\s*x\s*(\d{_NUM_CHARS}*?)\s+(\w{{3}})\s+nr\s+\S+\s*$"
)
FX_RE = re.compile(r"wymiana\s+waluty\s+(\w{3})\s*/\s*(\w{3})\s+([\d.,]+)", re.IGNORECASE)
CCY_RE = re.compile(r"^[A-Z]{3}$")

DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y")

# Reasons a row can be dropped, reported per file so nothing disappears silently.
SKIP_REASONS = (
    "short_row",
    "bad_date",
    "bad_amount",
    "no_currency",
    "unknown_operation",
    "unreadable_details",
    "unresolved_isin",
)


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
    # BOSSA groups thousands with spaces (or a non-breaking space) and uses a
    # comma for decimals; some exports mix both separators.
    s = re.sub(r"[\s  ]", "", val.strip())
    if not s:
        return None
    has_comma, has_dot = "," in s, "." in s
    if has_comma and has_dot:
        # Whichever separator comes last is the decimal one.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(val: str | None) -> str | None:
    """Normalise a BOSSA `data` cell to ISO `YYYY-MM-DD`, or None if unparseable."""
    if not val:
        return None
    s = val.strip()
    if not s:
        return None
    # Tolerate a timestamp suffix ("2024-01-15 10:22:31" / "…T10:22:31").
    s = re.split(r"[ T]", s, maxsplit=1)[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _resolve_row_currency(waluta: str, fallback: str) -> str:
    """Pick the cash ticker for a row: the `waluta` column first, then a valid fallback.

    Anything that is not a 3-letter code is treated as absent, so a missing
    column value can never become a bogus "MANY"/"USD" ticker in the ledger.
    """
    row_ccy = (waluta or "").strip().upper()
    if CCY_RE.match(row_ccy):
        return row_ccy
    alt = (fallback or "").strip().upper()
    return alt if CCY_RE.match(alt) else ""


def _parse_bossa_raw_transactions(
    raw_rows: list[list[str]],
    resolved_isins: dict[str, str],
    currency: str,
    skipped: Counter | None = None,
    warnings: list[str] | None = None,
) -> list[Transaction]:
    """Parse raw CSV rows into a list of structured Transaction objects.

    Rows may be shorter than the 5-column layout; those are counted as
    `short_row` skips. `enumerate(..., start=2)` lines the record numbers up with
    the statement, since the header occupies record 1.
    """
    transactions: list[Transaction] = []
    skipped = skipped if skipped is not None else Counter()
    warnings = warnings if warnings is not None else []
    fx_legs: Counter = Counter()
    seen_currencies: set[str] = set()

    for lineno, row in enumerate(raw_rows, start=2):
        if len(row) < 5:
            skipped["short_row"] += 1
            continue

        op_title = row[1].strip()
        details = row[2].strip()

        date_str = _parse_date(row[0])
        if date_str is None:
            skipped["bad_date"] += 1
            warnings.append(f"Row {lineno}: unreadable date {row[0].strip()!r} — skipped")
            continue

        kwota = _parse_float(row[3])
        if kwota is None:
            skipped["bad_amount"] += 1
            warnings.append(f"Row {lineno}: unreadable amount {row[3].strip()!r} — skipped")
            continue

        ccy = _resolve_row_currency(row[4], currency)
        if not ccy:
            skipped["no_currency"] += 1
            warnings.append(f"Row {lineno} ({op_title or 'no title'}): no currency — skipped")
            continue
        if ccy not in SUPPORTED_CURRENCIES and ccy not in seen_currencies:
            seen_currencies.add(ccy)
            warnings.append(
                f"Currency {ccy} is not a supported display currency — "
                "imported as a cash ticker and may not be priced"
            )

        entries: list[LedgerEntry] = []
        op_title_lower = op_title.lower()

        if "kupna" in op_title_lower:
            m = DETAILS_RE.match(details)
            if not m:
                skipped["unreadable_details"] += 1
                warnings.append(f"Row {lineno} ({op_title}): cannot read trade details — skipped")
                continue
            isin = m.group(2)
            qty = _parse_float(m.group(3))
            ticker = resolved_isins.get(isin)
            if not ticker:
                skipped["unresolved_isin"] += 1
                continue
            if qty is not None:
                entries.append(LedgerEntry(ticker=ticker, amount=round(qty, 8)))
            entries.append(LedgerEntry(ticker=ccy, amount=round(kwota, 8)))

        elif "sprzeda" in op_title_lower:
            m = DETAILS_RE.match(details)
            if not m:
                skipped["unreadable_details"] += 1
                warnings.append(f"Row {lineno} ({op_title}): cannot read trade details — skipped")
                continue
            isin = m.group(2)
            qty = _parse_float(m.group(3))
            ticker = resolved_isins.get(isin)
            if not ticker:
                skipped["unresolved_isin"] += 1
                continue
            if qty is not None:
                entries.append(LedgerEntry(ticker=ticker, amount=round(-qty, 8)))
            entries.append(LedgerEntry(ticker=ccy, amount=round(abs(kwota), 8)))

        elif "wymiana waluty" in op_title_lower:
            # Both legs of the swap arrive as separate rows, each in its own
            # currency. They are plain cash movements: NOT account operations.
            fx = FX_RE.search(op_title)
            if not fx:
                warnings.append(f"Row {lineno}: cannot read FX pair/rate from {op_title!r}")
            else:
                fx_legs[(date_str, fx.group(1).upper(), fx.group(2).upper(), fx.group(3))] += 1
            entries.append(LedgerEntry(ticker=ccy, amount=round(kwota, 8)))

        elif "przelew" in op_title_lower or "zwrot" in op_title_lower:
            entries.append(LedgerEntry(ticker=ccy, amount=round(kwota, 8), account_operation=True))

        elif "dywidenda" in op_title_lower:
            entries.append(LedgerEntry(ticker=ccy, amount=round(abs(kwota), 8)))

        else:
            skipped["unknown_operation"] += 1
            warnings.append(
                f"Row {lineno}: unrecognised operation {op_title!r} — skipped"
            )
            continue

        if entries:
            transactions.append(Transaction(date=date_str, entries=entries))

    for (dt, src, tgt, rate), legs in fx_legs.items():
        if legs != 2:
            warnings.append(
                f"FX swap {src}/{tgt} @ {rate} on {dt}: expected 2 legs, found {legs} — "
                "one side may be outside the exported date range"
            )

    transactions.sort(key=lambda t: t.date)
    return transactions


@dataclass(slots=True)
class BossaStatement:
    """Everything a BOSSA statement parse produced, including what it could not resolve."""

    transactions: list[dict] = field(default_factory=list)
    unresolved: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)


def parse_bossa_csv(
    file_path: str | Path,
    currency: str = "",
    progress_cb: Callable[[float, str], None] | None = None,
) -> BossaStatement:
    """Parse BOSSA CSV file into merged daily transactions.

    `currency` is only a fallback for rows whose `waluta` column is blank; pass
    an empty string (the normal case) so a guess can never invent a cash ticker.
    """
    currency = currency.strip().upper()
    log.info("Parsing %s (fallback currency=%s)", file_path, currency or "<per-row>")

    text = _read_csv_text(file_path)
    reader = csv.reader(io.StringIO(text), delimiter=";")

    header = next(reader, None)
    if not header:
        return BossaStatement()

    raw_rows: list[list[str]] = []
    isin_to_papier: dict[str, str] = {}
    for row in reader:
        raw_rows.append(row)
        if len(row) < 5:
            continue
        details = row[2].strip()
        m = DETAILS_RE.match(details)
        if m:
            papier, isin = m.group(1).strip(), m.group(2)
            isin_to_papier[isin] = papier

    resolved, still_unresolved = resolve_isins_with_names(isin_to_papier, progress_cb=progress_cb)

    skipped: Counter = Counter()
    warnings: list[str] = []
    raw_txns = _parse_bossa_raw_transactions(raw_rows, resolved, currency, skipped, warnings)

    # Merge entries occurring on the same date
    merged: list[Transaction] = []
    for tx in raw_txns:
        if merged and merged[-1].date == tx.date:
            merged[-1].entries.extend(tx.entries)
        else:
            merged.append(Transaction(date=tx.date, entries=list(tx.entries)))

    if still_unresolved:
        listed = ", ".join(
            f"{isin} ({name})" for isin, name in sorted(still_unresolved.items())
        )
        warnings.append(
            f"Unresolved ISIN — no ticker mapping, trade skipped: {listed}. "
            "Add ISIN=TICKER under Settings → ISIN mappings, then re-import."
        )

    log.info(
        "Parsed %d raw transactions, merged to %d daily records", len(raw_txns), len(merged)
    )
    log.info("Unresolved ISINs: %d", len(still_unresolved))
    if skipped:
        for reason in SKIP_REASONS:
            if skipped.get(reason):
                log.info("Skipped %d row(s): %s", skipped[reason], reason)
    for w in warnings:
        log.warning("%s", w)

    return BossaStatement(
        transactions=[t.to_dict() for t in merged],
        unresolved=still_unresolved,
        warnings=warnings,
        skipped={r: c for r, c in skipped.items() if c},
    )


def import_bossa(
    file_path: str | Path,
    currency: str = "",
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Validate, parse, deduplicate, and ingest BOSSA CSV transactions into the active ledger."""
    log.info("=== BOSSA import: %s (fallback currency=%s) ===", file_path, currency or "<per-row>")
    valid, msg = validate_bossa_file(file_path)
    if not valid:
        log.error("Validation failed: %s", msg)
        return {"success": False, "error": msg}

    statement = parse_bossa_csv(file_path, currency, progress_cb=progress_cb)
    result = ingest_transactions(statement.transactions)
    res_dict = result.to_dict()
    res_dict["warnings"] = statement.warnings
    return res_dict
