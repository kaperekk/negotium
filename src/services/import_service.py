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
from services.importers.base import BaseBrokerImporter, ImportResult, ValidationResult
from storage.context import ProjectContext

log = logging.getLogger(__name__)

BROKERS = ["XTB", "BOSSA", "Custom"]


class ImportService:
    """Orchestration service for broker imports and ledger reconciliations."""

    def __init__(self, context: ProjectContext | None = None):
        self.context = context or ProjectContext()

    def run_full_refresh(
        self,
        today: date,
        base_ccy: str,
        detect_currency_fn: Callable[[str], str],
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> tuple[int, int]:
        """Re-import all broker files in the project's imports directory."""
        from bossa_import import import_bossa
        from manual_import import import_manual
        from xtb_import import fix_avg_prices_from_open_positions, import_xtb

        imports_dir = self.context.imports_dir
        all_files: list[tuple[str, Path]] = []

        for b in BROKERS:
            bdir = imports_dir / b.lower()
            if not bdir.exists():
                continue
            for fpath in sorted(bdir.glob("*.xlsx")):
                all_files.append(("xtb", fpath))
            for fpath in sorted(bdir.glob("*.csv")):
                all_files.append(("bossa", fpath))
            for fpath in sorted(bdir.glob("*.json")):
                all_files.append(("custom", fpath))

        total_imported = 0
        if all_files:
            for idx, (kind, fpath) in enumerate(all_files):
                ccy = detect_currency_fn(fpath.name)
                if progress_cb:
                    progress_cb(idx / len(all_files), f"Importing {fpath.name}…")
                if kind == "bossa":
                    res = import_bossa(str(fpath), ccy)
                elif kind == "custom":
                    res = import_manual(str(fpath))
                else:
                    res = import_xtb(str(fpath), ccy)

                if res.get("success"):
                    total_imported += res.get("imported", 0)

            for kind, fpath in all_files:
                if kind == "xtb":
                    ccy = detect_currency_fn(fpath.name)
                    fix_avg_prices_from_open_positions(str(fpath), ccy)

        storage.invalidate_portfolio_from((today - timedelta(days=1)).isoformat())
        return len(all_files), total_imported
