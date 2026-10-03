"""
repositories.py — typed repository abstractions for storage persistence.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from domain.models import AssetHolding, LedgerEntry, PortfolioSnapshot, TickerMeta, Transaction
from storage.context import DATA_ROOT, ProjectContext
from storage.backends import get_backend

try:
    import orjson
    def _loads(data: bytes):
        return orjson.loads(data)
    def _dumps(obj) -> str:
        return orjson.dumps(obj).decode()
except ImportError:
    import json
    _loads = json.loads
    _dumps = lambda obj: json.dumps(obj, ensure_ascii=False)


def _get_backend():
    return get_backend()


def _read_bytes(key: str) -> bytes | None:
    backend = _get_backend()
    if not backend.exists(key):
        return None
    return backend.read_bytes(key)


def _write_bytes(key: str, data: bytes) -> None:
    backend = _get_backend()
    backend.write_bytes(key, data)


def _delete(key: str) -> None:
    backend = _get_backend()
    backend.delete(key)


def _list_keys(prefix: str) -> list[str]:
    backend = _get_backend()
    return backend.list_files(prefix)


def iter_jsonl(key: str) -> Iterator[dict]:
    """Yield parsed dicts from a .jsonl file, skipping blank lines."""
    data = _read_bytes(key)
    if data is None:
        return
    for line in data.splitlines():
        if line.strip():
            yield _loads(line)


def read_jsonl(key: str) -> list[dict]:
    return list(iter_jsonl(key))


def write_jsonl(key: str, records: list[dict]) -> None:
    """Atomically overwrite file with one JSON object per line."""
    buf = b"".join(_dumps(rec).encode() + b"\n" for rec in records)
    _write_bytes(key, buf)


def append_jsonl(key: str, record: dict) -> None:
    """Append a single record to a .jsonl file."""
    existing = read_jsonl(key)
    existing.append(record)
    write_jsonl(key, existing)


class TransactionRepository:
    """Persistence operations for transaction ledgers."""

    def __init__(self, context: ProjectContext | None = None):
        self.context = context or ProjectContext()

    @property
    def key(self) -> str:
        return self.context.transactions_key

    def get_all(self) -> list[Transaction]:
        return [Transaction.from_dict(d) for d in read_jsonl(self.key)]

    def get_all_dicts(self) -> list[dict]:
        return read_jsonl(self.key)

    def save_all(self, transactions: list[Transaction] | list[dict]) -> None:
        raw = [t.to_dict() if isinstance(t, Transaction) else t for t in transactions]
        write_jsonl(self.key, raw)

    def append(self, transaction: Transaction | dict) -> None:
        raw = transaction.to_dict() if isinstance(transaction, Transaction) else transaction
        append_jsonl(self.key, raw)


class SnapshotRepository:
    """Persistence operations for portfolio snapshots and benchmarks."""

    def __init__(self, context: ProjectContext | None = None):
        self.context = context or ProjectContext()

    @property
    def portfolio_key(self) -> str:
        return self.context.portfolio_key

    def load_portfolio(self) -> list[PortfolioSnapshot]:
        return [PortfolioSnapshot.from_dict(d) for d in read_jsonl(self.portfolio_key)]

    def load_portfolio_dicts(self) -> list[dict]:
        return read_jsonl(self.portfolio_key)

    def save_portfolio(self, snapshots: list[PortfolioSnapshot] | list[dict]) -> None:
        raw = [s.to_dict() if isinstance(s, PortfolioSnapshot) else s for s in snapshots]
        write_jsonl(self.portfolio_key, raw)

    def invalidate_portfolio_from(self, from_date: str) -> None:
        data = read_jsonl(self.portfolio_key)
        filtered = [rec for rec in data if str(rec.get("date", "")) < from_date]
        write_jsonl(self.portfolio_key, filtered)

    def load_benchmarks(self, base_ccy: str) -> list[dict] | None:
        key = self.context.benchmark_cache_key(base_ccy)
        data = _read_bytes(key)
        if data is None:
            return None
        return _loads(data)

    def save_benchmarks(self, base_ccy: str, data: list[dict]) -> None:
        key = self.context.benchmark_cache_key(base_ccy)
        _write_bytes(key, _dumps(data).encode())


class BalanceRepository:
    """Persistence operations for balance.json (holdings & avg_price)."""

    def __init__(self, context: ProjectContext | None = None):
        self.context = context or ProjectContext()

    @property
    def key(self) -> str:
        return self.context.balance_key

    def load_balance(self) -> dict[str, dict]:
        data = _read_bytes(self.key)
        if data is None:
            return {}
        data = _loads(data)
        result = {}
        for k, v in data.items():
            if isinstance(v, dict):
                result[k] = v
            else:
                result[k] = {"amount": float(v), "avg_price": 0.0}
        return result

    def save_balance(self, balance: dict[str, dict]) -> None:
        clean = {}
        for k, v in balance.items():
            amt = v.get("amount", 0.0) if isinstance(v, dict) else v
            if abs(amt) > 1e-9:
                if isinstance(v, dict):
                    clean[k] = {
                        "amount": round(float(amt), 8),
                        "avg_price": round(float(v.get("avg_price", 0.0)), 6),
                    }
                else:
                    clean[k] = {"amount": round(float(amt), 8), "avg_price": 0.0}
        _write_bytes(self.key, _dumps(clean).encode())