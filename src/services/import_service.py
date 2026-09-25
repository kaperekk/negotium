"""
import_service.py — unified import orchestration service.

Handles broker format detection, multi-file imports, and automatic cache invalidation.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import storage
from services.importers import (
    BaseBrokerImporter,
    BossaImporter,
    ImportResult,
    ManualImporter,
    ValidationResult,
    XtbImporter,
)
from storage.context import ProjectContext

log = logging.getLogger(__name__)

BROKER_IMPORTERS: dict[str, tuple[str, BaseBrokerImporter]] = {
    "xtb": ("*.xlsx", XtbImporter()),
    "bossa": ("*.csv", BossaImporter()),
    "custom": ("*.json", ManualImporter()),
}


class ImportService:
    """Orchestration service for broker imports and ledger reconciliations."""

    def __init__(
        self,
        context: ProjectContext | None = None,
        importers: dict[str, tuple[str, BaseBrokerImporter]] | None = None,
    ):
        self.context = context or ProjectContext()
        self.importers = importers or BROKER_IMPORTERS

    def run_full_refresh(
        self,
        today: date,
        base_ccy: str,
        detect_currency_fn: Callable[[str], str],
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> tuple[int, int]:
        """Re-import all broker files in the project's imports directory."""
        imports_dir = self.context.imports_dir
        all_files: list[tuple[str, Path, BaseBrokerImporter]] = []

        for broker_key, (glob_pattern, importer) in self.importers.items():
            bdir = imports_dir / broker_key
            if not bdir.exists():
                continue
            for fpath in sorted(bdir.glob(glob_pattern)):
                all_files.append((broker_key, fpath, importer))

        total_imported = 0
        if all_files:
            for idx, (broker_key, fpath, importer) in enumerate(all_files):
                ccy = detect_currency_fn(fpath.name)
                if progress_cb:
                    progress_cb(idx / len(all_files), f"Importing {fpath.name}…")

                res = importer.import_file(fpath, ccy, progress_cb=progress_cb)
                if res.success:
                    total_imported += res.imported

            # Execute any broker post-import hooks (e.g. VWAP open lot fixes)
            for broker_key, fpath, importer in all_files:
                if hasattr(importer, "post_import"):
                    ccy = detect_currency_fn(fpath.name)
                    importer.post_import(fpath, ccy)

        storage.invalidate_portfolio_from((today - timedelta(days=1)).isoformat())
        return len(all_files), total_imported
