"""Shared UI helper functions for formatting."""

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


def safe_get(mapping: dict[str, Any], key: str, default: Any = None) -> Any:
    """Return a dict value only when the key exists."""
    return mapping.get(key, default)
