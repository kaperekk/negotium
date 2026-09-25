"""
manual.py — Manual JSON transaction statement importer implementation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from services.importers.base import BaseBrokerImporter, ImportResult, ValidationResult
import manual_import


class ManualImporter(BaseBrokerImporter):
    """Manual/custom JSON transaction importer."""

    def validate(self, file_path: str | Path) -> ValidationResult:
        valid, msg = manual_import.validate_manual_file(file_path)
        return ValidationResult(valid=valid, message=msg)

    def parse(
        self,
        file_path: str | Path,
        currency: str = "",
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> list[dict]:
        return manual_import.parse_manual_json(file_path)

    def import_file(
        self,
        file_path: str | Path,
        currency: str = "",
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> ImportResult:
        res = manual_import.import_manual(file_path)
        return ImportResult(
            success=bool(res.get("success", False)),
            imported=int(res.get("imported", 0)),
            skipped=int(res.get("skipped", 0)),
            error=str(res.get("error", "")),
        )
