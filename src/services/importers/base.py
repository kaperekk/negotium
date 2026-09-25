"""
base.py — abstract base class and interface specification for broker importers.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from domain.models import LedgerEntry, Transaction

log = logging.getLogger(__name__)

# Warnings are user-facing: the UI renders them next to the import result.
# Keep the cap in one place so no importer can flood the sidebar.
MAX_REPORTED_WARNINGS = 10


def summarize_warnings(warnings: list[str], limit: int = MAX_REPORTED_WARNINGS) -> list[str]:
    """Cap a warning list for display, keeping a count of what was hidden."""
    if len(warnings) <= limit:
        return list(warnings)
    hidden = len(warnings) - limit
    return [*warnings[:limit], f"… and {hidden} more warning{'s' if hidden != 1 else ''}"]


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    message: str = ""

    def to_tuple(self) -> tuple[bool, str]:
        return self.valid, self.message


@dataclass(slots=True)
class ParseResult:
    """Output of a broker statement parse.

    `unresolved` carries identifiers the importer could not translate (BOSSA
    ISINs without a ticker mapping) and `warnings` carries non-fatal problems
    (unrecognised rows, missing currencies, unpaired FX legs). Both must
    survive to the caller — a successful import can still have work left.
    """

    transactions: list[dict] = field(default_factory=list)
    unresolved: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.transactions)


@dataclass(slots=True)
class ImportResult:
    success: bool
    imported: int = 0
    skipped: int = 0
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "success": self.success,
            "imported": self.imported,
            "skipped": self.skipped,
        }
        if self.error:
            d["error"] = self.error
        if self.warnings:
            d["warnings"] = summarize_warnings(self.warnings)
        return d


def ingest_transactions(transactions: list[Transaction | dict]) -> ImportResult:
    """Standardized deduplication and ingestion engine across all broker statement importers.

    Takes a list of Transaction models (or transaction dicts), checks against existing
    entries in the active project ledger, and inserts non-duplicate transactions.
    """
    from ledger_core import add_transaction, existing_entry_counts

    existing = existing_entry_counts()
    imported = 0
    skipped = 0
    partial = 0

    for item in transactions:
        tx = Transaction.from_dict(item) if isinstance(item, dict) else item
        new_entries: list[dict] = []
        for e in tx.entries:
            key = (tx.date, e.ticker.upper(), round(float(e.amount), 8))
            if existing.get(key, 0) > 0:
                existing[key] -= 1
            else:
                new_entries.append(e.to_dict())

        if new_entries:
            if len(new_entries) != len(tx.entries):
                # A trade is only meaningful with all of its legs: writing the
                # surviving half would unbalance the ledger against the cash
                # leg already on file. Keep the multiset invariant, but say so.
                partial += 1
                log.warning(
                    "Partially duplicate transaction on %s: %d of %d entries already in ledger, importing %d",
                    tx.date,
                    len(tx.entries) - len(new_entries),
                    len(tx.entries),
                    len(new_entries),
                )
            add_transaction(tx.date, new_entries)
            imported += 1
        else:
            skipped += 1

    log.info("Ingest result: %d imported, %d skipped (duplicates)", imported, skipped)
    if partial:
        log.warning("Ingest: %d transactions imported with some legs already present", partial)
    return ImportResult(success=True, imported=imported, skipped=skipped)


class BaseBrokerImporter(ABC):
    """Abstract interface for all broker transaction statement importers."""

    @abstractmethod
    def validate(self, file_path: str | Path) -> ValidationResult:
        """Validate if the given file matches this broker format."""
        raise NotImplementedError

    @abstractmethod
    def parse(
        self,
        file_path: str | Path,
        currency: str,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> ParseResult:
        """Parse the broker file into Negotium ledger transaction dictionaries."""
        raise NotImplementedError

    @abstractmethod
    def import_file(
        self,
        file_path: str | Path,
        currency: str,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> ImportResult:
        """Parse and ingest the broker transactions into the active project ledger."""
        raise NotImplementedError

    def file_currency(self, filename: str) -> str:
        """Resolve the statement's account currency from its filename.

        The default is "unknown": importers whose statements carry a currency
        per row (BOSSA) or not at all (custom JSON) override this to return an
        empty string rather than guessing, so a guess can never leak into the
        ledger as a fake cash ticker.
        """
        return ""
