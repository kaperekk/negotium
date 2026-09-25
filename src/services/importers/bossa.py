"""
bossa.py — BOSSA broker statement importer implementation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import bossa_import
from services.importers.base import BaseBrokerImporter, ImportResult, ParseResult, ValidationResult


class BossaImporter(BaseBrokerImporter):
    """BOSSA 'Historia finansowa' CSV statement importer."""

    def validate(self, file_path: str | Path) -> ValidationResult:
        valid, msg = bossa_import.validate_bossa_file(file_path)
        return ValidationResult(valid=valid, message=msg)

    def parse(
        self,
        file_path: str | Path,
        currency: str = "",
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> ParseResult:
        statement = bossa_import.parse_bossa_csv(file_path, currency, progress_cb=progress_cb)
        return ParseResult(
            transactions=statement.transactions,
            unresolved=statement.unresolved,
            warnings=list(statement.warnings),
        )

    def import_file(
        self,
        file_path: str | Path,
        currency: str = "",
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> ImportResult:
        res = bossa_import.import_bossa(file_path, currency, progress_cb=progress_cb)
        return ImportResult(
            success=bool(res.get("success", False)),
            imported=int(res.get("imported", 0)),
            skipped=int(res.get("skipped", 0)),
            error=str(res.get("error", "")),
            warnings=list(res.get("warnings", [])),
        )

    def file_currency(self, filename: str) -> str:
        """BOSSA statements carry the currency per row — never guess from the filename."""
        return ""
