"""
base.py — abstract base class and interface specification for broker importers.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from domain.models import LedgerEntry, Transaction

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    message: str = ""

    def to_tuple(self) -> tuple[bool, str]:
        return self.valid, self.message


@dataclass(slots=True)
class ImportResult:
    success: bool
    imported: int = 0
    skipped: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "success": self.success,
            "imported": self.imported,
            "skipped": self.skipped,
        }
        if self.error:
            d["error"] = self.error
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
            add_transaction(tx.date, new_entries)
            imported += 1
        else:
            skipped += 1

    log.info("Ingest result: %d imported, %d skipped (duplicates)", imported, skipped)
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
    ) -> list[dict]:
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
