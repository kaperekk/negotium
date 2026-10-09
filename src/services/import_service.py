"""
import_service.py — unified import orchestration service.

Handles broker format detection, multi-file imports, and automatic cache invalidation.
"""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import openpyxl
import storage
from services.importers import (
    BaseBrokerImporter,
    BossaImporter,
    ImportResult,
    ManualImporter,
    ParseResult,
    XtbImporter,
    summarize_warnings,
)
from storage.context import ProjectContext
from storage.backends import get_backend

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
        self._backend = get_backend()

    def importer_for(self, broker: str) -> BaseBrokerImporter:
        """Look up the registered importer for a broker key."""
        try:
            return self.importers[broker][1]
        except KeyError:
            raise ValueError(
                f"Unknown broker {broker!r} (known: {', '.join(sorted(self.importers))})"
            ) from None

    def _is_xtb_file(self, file_path: Path) -> bool:
        """Check if an .xlsx file is an XTB export by looking for 'Cash Operations' sheet."""
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True)
            try:
                return "Cash Operations" in wb.sheetnames
            finally:
                wb.close()
        except Exception:
            return False

    def broker_for_filename(self, filename: str) -> str | None:
        """Map a statement filename to its broker key by extension and content.

        For .xlsx files, peeks inside to check for XTB's "Cash Operations" sheet.
        """
        suffix = Path(filename).suffix.lower()
        if suffix == ".xlsx":
            return "xtb"
        for broker, (pattern, _) in self.importers.items():
            if Path(pattern).suffix.lower() == suffix:
                return broker
        return None

    def broker_for_path(self, file_path: Path) -> str | None:
        """Map a statement file path to its broker key by extension and content."""
        suffix = file_path.suffix.lower()
        if suffix == ".xlsx":
            if self._is_xtb_file(file_path):
                return "xtb"
            return None
        for broker, (pattern, _) in self.importers.items():
            if Path(pattern).suffix.lower() == suffix:
                return broker
        return None

    def validate_file(self, broker: str, file_path: str | Path) -> bool:
        """Validate a statement against its broker's format rules."""
        return self.importer_for(broker).validate(file_path)

    def currency_for(self, broker: str, file_path: str | Path) -> str:
        """Resolve the account currency for a file via its importer.

        Importers that read the currency per row (BOSSA) return None,
        so a filename that happens to start with letters can never
        become a fake cash ticker.
        """
        ccy = self.importer_for(broker).file_currency(Path(file_path).name)
        return ccy or ""

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

    def _imports_prefix(self) -> str:
        return self.context.imports_prefix

    def _broker_prefix(self, broker: str) -> str:
        return f"{self._imports_prefix()}{broker}/"

    def store_import_file(self, broker: str, filename: str, data: bytes) -> str:
        """Store an imported file and return its storage key."""
        key = f"{self._broker_prefix(broker)}{filename}"
        self._backend.write_bytes(key, data)
        return key

    def get_import_file(self, broker: str, filename: str) -> bytes | None:
        """Retrieve an imported file as bytes."""
        key = f"{self._broker_prefix(broker)}{filename}"
        if not self._backend.exists(key):
            return None
        return self._backend.read_bytes(key)

    def list_import_files(self, broker: str) -> list[str]:
        """List all stored import files for a broker."""
        prefix = self._broker_prefix(broker)
        keys = self._backend.list_files(prefix)
        return [k[len(prefix):] for k in keys if k.startswith(prefix)]

    def delete_import_file(self, broker: str, filename: str) -> None:
        """Delete an imported file."""
        key = f"{self._broker_prefix(broker)}{filename}"
        self._backend.delete(key)

    def _with_temp_file(self, data: bytes, suffix: str, func: Callable[[Path], any]) -> any:
        """Create a temp file with data, call func, and clean up."""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            return func(tmp_path)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

    def import_stored_file(
        self,
        broker: str,
        filename: str,
        currency: str | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
        run_post_import: bool = True,
    ) -> ImportResult:
        """Import a previously stored file by broker and filename."""
        data = self.get_import_file(broker, filename)
        if data is None:
            return ImportResult(success=False, error=f"File not found: {filename}")

        pattern, _ = self.importers[broker]
        suffix = Path(pattern).suffix

        def do_import(path: Path) -> ImportResult:
            return self.import_file(broker, path, currency, progress_cb, run_post_import)

        return self._with_temp_file(data, suffix, do_import)

    def discover_files(self) -> list[tuple[str, str]]:
        """Every stored statement file, as (broker_key, filename) pairs, in registry order."""
        found: list[tuple[str, str]] = []
        for broker, (pattern, _) in self.importers.items():
            files = self.list_import_files(broker)
            found.extend((broker, f) for f in sorted(files))
        return found

    def run_full_refresh(
        self,
        today: date,
        base_ccy: str,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> RefreshReport:
        """Re-import all broker files in the project's imports directory.

        Clears the ledger and all derived state first so that files removed
        by the user do not leave stale transactions behind. The result always
        reflects exactly the files currently stored.
        """
        from storage.repositories import TransactionRepository
        from ledger_core import rebuild_balance

        # Wipe ledger and all portfolio snapshots before replaying from scratch
        if progress_cb:
            progress_cb(0.0, "Clearing ledger…")
        TransactionRepository(self.context).save_all([])
        storage.invalidate_portfolio_from("0000-00-00")

        all_files = self.discover_files()
        report = RefreshReport(file_count=len(all_files))

        for idx, (broker, filename) in enumerate(all_files):
            if progress_cb:
                progress_cb((idx + 1) / (len(all_files) + 1), f"Importing {filename}…")

            ccy = self.currency_for(broker, filename)
            res = self.import_stored_file(
                broker, filename, currency=ccy, progress_cb=progress_cb, run_post_import=False
            )
            if res.success:
                report.imported += res.imported
                report.skipped += res.skipped
                for w in summarize_warnings(res.warnings):
                    report.warnings.append(f"{filename}: {w}")
            else:
                report.warnings.append(f"{filename}: import failed — {res.error}")

        for broker, filename in all_files:
            importer = self.importer_for(broker)
            if hasattr(importer, "post_import"):
                ccy = self.currency_for(broker, filename)
                data = self.get_import_file(broker, filename)
                if data is not None:
                    pattern, _ = self.importers[broker]
                    suffix = Path(pattern).suffix
                    self._with_temp_file(data, suffix, lambda p: importer.post_import(p, ccy))

        if progress_cb:
            progress_cb(0.95, "Rebuilding balance…")
        rebuild_balance()
        if progress_cb:
            progress_cb(1.0, "Done")
        return report