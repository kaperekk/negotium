"""
import_service.py — unified import orchestration service.

Handles broker format detection, multi-file imports, and automatic cache invalidation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import storage
from services.importers import (
    BaseBrokerImporter,
    BossaImporter,
    ImportResult,
    ManualImporter,
    ParseResult,
    ValidationResult,
    XtbImporter,
    summarize_warnings,
)
from storage.context import ProjectContext

log = logging.getLogger(__name__)

BROKER_IMPORTERS: dict[str, tuple[str, BaseBrokerImporter]] = {
    "xtb": ("*.xlsx", XtbImporter()),
    "bossa": ("*.csv", BossaImporter()),
    "custom": ("*.json", ManualImporter()),
}

BROKER_EXTENSIONS: dict[str, str] = {
    broker: Path(pattern).suffix.lstrip(".").lower()
    for broker, (pattern, _) in BROKER_IMPORTERS.items()
}


@dataclass(slots=True)
class RefreshReport:
    """Outcome of replaying every stored statement file."""

    file_count: int = 0
    imported: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


class ImportService:
    """Orchestration service for broker imports and ledger reconciliations."""

    def __init__(
        self,
        context: ProjectContext | None = None,
        importers: dict[str, tuple[str, BaseBrokerImporter]] | None = None,
    ):
        self.context = context or ProjectContext()
        self.importers = importers or BROKER_IMPORTERS

    def importer_for(self, broker: str) -> BaseBrokerImporter:
        """Look up the registered importer for a broker key."""
        try:
            return self.importers[broker][1]
        except KeyError:
            raise ValueError(
                f"Unknown broker {broker!r} (known: {', '.join(sorted(self.importers))})"
            ) from None

    def broker_for_filename(self, filename: str) -> str | None:
        """Map a statement filename to its broker key by extension, or None."""
        suffix = Path(filename).suffix.lower()
        for broker, (pattern, _) in self.importers.items():
            if Path(pattern).suffix.lower() == suffix:
                return broker
        return None

    def validate_file(self, broker: str, file_path: str | Path) -> ValidationResult:
        """Validate a statement against its broker's format rules."""
        return self.importer_for(broker).validate(file_path)

    def currency_for(self, broker: str, file_path: str | Path) -> str:
        """Resolve the account currency for a file via its importer.

        Importers that read the currency per row (BOSSA) return an empty
        string, so a filename that happens to start with letters can never
        become a fake cash ticker.
        """
        return self.importer_for(broker).file_currency(Path(file_path).name)

    def parse_file(
        self,
        broker: str,
        file_path: str | Path,
        currency: str | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> ParseResult:
        """Parse a single statement through the broker's registered importer."""
        importer = self.importer_for(broker)
        ccy = self.currency_for(broker, file_path) if currency is None else currency
        return importer.parse(file_path, ccy, progress_cb=progress_cb)

    def import_file(
        self,
        broker: str,
        file_path: str | Path,
        currency: str | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
        run_post_import: bool = True,
    ) -> ImportResult:
        """Import one statement file and run the broker's post-import hook."""
        importer = self.importer_for(broker)
        ccy = self.currency_for(broker, file_path) if currency is None else currency
        result = importer.import_file(file_path, ccy, progress_cb=progress_cb)
        if result.success and run_post_import and hasattr(importer, "post_import"):
            importer.post_import(file_path, ccy)
        return result

    def discover_files(self) -> list[tuple[str, Path]]:
        """Every stored statement file, as (broker_key, path) pairs, in registry order."""
        found: list[tuple[str, Path]] = []
        for broker, (pattern, _) in self.importers.items():
            bdir = self.context.imports_dir / broker
            if not bdir.exists():
                continue
            found.extend((broker, fpath) for fpath in sorted(bdir.glob(pattern)))
        return found

    def run_full_refresh(
        self,
        today: date,
        base_ccy: str,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> RefreshReport:
        """Re-import all broker files in the project's imports directory.

        Each importer resolves its own statement currency, so no filename
        guessing leaks into the ledger.
        """
        all_files = self.discover_files()
        report = RefreshReport(file_count=len(all_files))

        for idx, (broker, fpath) in enumerate(all_files):
            if progress_cb:
                progress_cb(idx / len(all_files), f"Importing {fpath.name}…")

            res = self.import_file(
                broker, fpath, progress_cb=progress_cb, run_post_import=False
            )
            if res.success:
                report.imported += res.imported
                report.skipped += res.skipped
                for w in summarize_warnings(res.warnings):
                    report.warnings.append(f"{fpath.name}: {w}")
            else:
                report.warnings.append(f"{fpath.name}: import failed — {res.error}")

        # Broker post-import hooks (e.g. XTB VWAP open-lot fixes) run after every
        # file is in the ledger, since they read the whole position set.
        for broker, fpath in all_files:
            importer = self.importer_for(broker)
            if hasattr(importer, "post_import"):
                importer.post_import(fpath, self.currency_for(broker, fpath))

        storage.invalidate_portfolio_from((today - timedelta(days=1)).isoformat())
        return report
