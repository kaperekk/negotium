"""
base.py — abstract base class and interface specification for broker importers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    message: str = ""


@dataclass(slots=True)
class ImportResult:
    success: bool
    imported: int = 0
    skipped: int = 0
    error: str = ""


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
