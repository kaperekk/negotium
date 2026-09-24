"""
currencies.py — compatibility wrapper re-exporting from domain.currencies.
"""
from __future__ import annotations

from domain.currencies import (
    CURRENCY_SUFFIXES,
    CURRENCY_SYMBOLS,
    SUFFIX_CURRENCY,
    SUPPORTED_CURRENCIES,
    TRIANGULATE_VIA_USD,
)

__all__ = [
    "SUPPORTED_CURRENCIES",
    "CURRENCY_SUFFIXES",
    "SUFFIX_CURRENCY",
    "TRIANGULATE_VIA_USD",
    "CURRENCY_SYMBOLS",
]
