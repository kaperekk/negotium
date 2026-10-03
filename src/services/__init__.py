"""
services package initialization.
"""
from __future__ import annotations

# Lazy imports to avoid pandas dependency at import time
def __getattr__(name: str):
    if name == "LedgerService":
        from services.ledger_service import LedgerService
        return LedgerService
    if name == "PortfolioService":
        from services.portfolio_service import PortfolioService
        return PortfolioService
    if name == "detect_ticker_currency":
        from services.portfolio_service import detect_ticker_currency
        return detect_ticker_currency
    raise AttributeError(f"module 'services' has no attribute {name!r}")

__all__ = [
    "LedgerService",
    "PortfolioService",
    "detect_ticker_currency",
]
