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
    ValidationResult,
)
import xtb_import


class XtbImporter(BaseBrokerImporter):
    """XTB Excel statement importer."""

    def validate(self, file_path: str | Path) -> ValidationResult:
        valid, msg = xtb_import.validate_xtb_file(file_path)
        return ValidationResult(valid=valid, message=msg)

    def parse(
        self,
        file_path: str | Path,
        currency: str,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> ParseResult:
        return ParseResult(transactions=xtb_import.parse_xtb_excel(file_path, currency))

    def import_file(
        self,
        file_path: str | Path,
        currency: str,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> ImportResult:
        res = xtb_import.import_xtb(file_path, currency)
        return ImportResult(
            success=bool(res.get("success", False)),
            imported=int(res.get("imported", 0)),
            skipped=int(res.get("skipped", 0)),
            error=str(res.get("error", "")),
            warnings=list(res.get("warnings", [])),
        )

    def post_import(self, file_path: str | Path, currency: str) -> None:
        """Run post-import actions such as updating average cost basis from Open Positions."""
        xtb_import.fix_avg_prices_from_open_positions(file_path, currency)

    def file_currency(self, filename: str) -> str:
        """XTB exports one account per file, named after its currency (e.g. `EUR_history.xlsx`)."""
        prefix = Path(filename).name.strip()[:3].upper()
        return prefix if prefix in SUPPORTED_CURRENCIES else "EUR"
