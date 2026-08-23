"""Shared UI helper functions for formatting and file detection."""

from __future__ import annotations

from typing import Any


def fmt(v: float) -> str:
    """Format values in a compact, human-friendly manner."""
    if v is None or v != v:
        return "—"
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"{v/1_000:.2f}K"
    if abs(v) >= 10:
        return f"{v:.2f}"
    if abs(v) >= 1:
        return f"{v:.3f}"
    return f"{v:.4f}"


def detect_currency(filename: str) -> str:
    """Infer a currency from a filename prefix."""
    prefix = filename.strip()[:3].upper()
    return prefix if prefix in ("EUR", "PLN", "USD") else "USD"


def safe_get(mapping: dict[str, Any], key: str, default: Any = None) -> Any:
    """Return a dict value only when the key exists."""
    return mapping.get(key, default)
