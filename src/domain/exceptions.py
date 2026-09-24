"""
exceptions.py — domain-specific exceptions for Negotium.
"""
from __future__ import annotations


class NegotiumError(Exception):
    """Base exception for all Negotium application errors."""


class CorruptedLedgerError(NegotiumError):
    """Raised when ledger JSONL format or chronology is unrecoverable."""


class InvalidImportFormatError(NegotiumError):
    """Raised when an uploaded broker statement cannot be parsed or validated."""


class PriceFetchError(NegotiumError):
    """Raised when market price downloads fail unexpectedly."""


class ProjectNotFoundError(NegotiumError):
    """Raised when an operation is performed on a non-existent project."""
