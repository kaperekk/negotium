"""
models.py — domain models for Negotium.

Lightweight, slotted dataclasses representing core entities across the system.
Includes fast dict conversion methods compatible with JSONL and JSON serialization.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class LedgerEntry:
    """A single leg/entry of a transaction."""
    ticker: str
    amount: float
    account_operation: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "ticker": self.ticker,
            "amount": self.amount,
        }
        if self.account_operation:
            d["account_operation"] = True
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LedgerEntry:
        return cls(
            ticker=str(data["ticker"]).upper(),
            amount=float(data["amount"]),
            account_operation=bool(data.get("account_operation", False)),
        )


@dataclass(slots=True)
class Transaction:
    """A multi-leg ledger transaction on a given calendar date."""
    date: str  # YYYY-MM-DD
    entries: list[LedgerEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transaction:
        return cls(
            date=str(data["date"]),
            entries=[LedgerEntry.from_dict(e) for e in data.get("entries", [])],
        )


@dataclass(slots=True)
class AssetHolding:
    """Valuation snapshot of an individual asset holding on a given day."""
    ticker: str
    amount: float
    price: float
    currency: str
    value_native: float
    value_base: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "amount": self.amount,
            "price": self.price,
            "currency": self.currency,
            "value_native": self.value_native,
            "value_base": self.value_base,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetHolding:
        return cls(
            ticker=str(data["ticker"]),
            amount=float(data["amount"]),
            price=float(data["price"]),
            currency=str(data["currency"]),
            value_native=float(data["value_native"]),
            value_base=float(data["value_base"]),
        )


@dataclass(slots=True)
class PortfolioSnapshot:
    """Portfolio state and valuation snapshot for a single day."""
    date: str  # YYYY-MM-DD
    assets: list[AssetHolding]
    total_value: float
    invested: float
    base_currency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "assets": [a.to_dict() for a in self.assets],
            "total_value": self.total_value,
            "invested": self.invested,
            "base_currency": self.base_currency,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PortfolioSnapshot:
        return cls(
            date=str(data["date"]),
            assets=[AssetHolding.from_dict(a) for a in data.get("assets", [])],
            total_value=float(data.get("total_value", 0.0)),
            invested=float(data.get("invested", 0.0)),
            base_currency=str(data.get("base_currency", "")),
        )


@dataclass(slots=True)
class TickerMeta:
    """Sector, country, and asset class classification for a ticker."""
    ticker: str
    name: str = ""
    sector: str = "Unknown"
    country: str = "Unknown"
    asset_class: str = "Equity"

    def to_dict(self) -> dict[str, str]:
        return {
            "sector": self.sector,
            "country": self.country,
            "asset_class": self.asset_class,
        }

    @classmethod
    def from_dict(cls, ticker: str, data: dict[str, Any], name: str = "") -> TickerMeta:
        return cls(
            ticker=ticker,
            name=name,
            sector=str(data.get("sector", "Unknown")),
            country=str(data.get("country", "Unknown")),
            asset_class=str(data.get("asset_class", "Equity")),
        )
