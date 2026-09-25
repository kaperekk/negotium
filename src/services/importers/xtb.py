"""
xtb.py — XTB broker statement importer implementation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from currencies import SUPPORTED_CURRENCIES
from services.importers.base import (
    BaseBrokerImporter,
    ImportResult,
    ParseResult,
)
import xtb_import


class XtbImporter(BaseBrokerImporter):
    """XTB Excel statement importer."""

    def validate(self, file_path: str | Path) -> bool:
        valid, _ = xtb_import.validate_xtb_file(file_path)
        return valid

    def parse(
        self,
        file_path: str | Path,
        currency: str | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> ParseResult:
        return ParseResult(transactions=xtb_import.parse_xtb_excel(file_path, currency or "EUR"))

    def import_file(
        self,
        file_path: str | Path,
        currency: str | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> ImportResult:
        try:
            res = xtb_import.import_xtb(file_path, currency or "EUR")
        except Exception as e:
            return ImportResult(success=False, error=str(e))
        return ImportResult(
            success=bool(res.get("success", False)),
            imported=int(res.get("imported", 0)),
            skipped=int(res.get("skipped", 0)),
            error=str(res.get("error", "")),
            warnings=list(res.get("warnings", [])),
        )

    def post_import(self, file_path: str | Path, currency: str) -> None:
        """Run post-import actions such as updating average cost basis from Open Positions.

        XTB-specific: uses the Open Positions sheet to fix VWAP cost basis.
        Other brokers (BOSSA, Manual) don't provide open-position data, so this
        hook is a no-op for them.
        """
        xtb_import.fix_avg_prices_from_open_positions(file_path, currency)

    def file_currency(self, filename: str) -> str | None:
        """XTB exports one account per file, named after its currency (e.g. `EUR_history.xlsx`)."""
        prefix = Path(filename).name.strip()[:3].upper()
        return prefix if prefix in SUPPORTED_CURRENCIES else "EUR"
