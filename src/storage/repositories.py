"""
repositories.py — typed repository abstractions for storage persistence.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from domain.models import AssetHolding, LedgerEntry, PortfolioSnapshot, TickerMeta, Transaction
from storage.context import DATA_ROOT, ProjectContext

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


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write bytes via temp file + rename so a crash never leaves a torn file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield parsed dicts from a .jsonl file, skipping blank lines."""
    if not path.exists():
        return
    with path.open("rb") as f:
        for line in f:
            if line.strip():
                yield _loads(line)


def read_jsonl(path: Path) -> list[dict]:
    return list(iter_jsonl(path))


def write_jsonl(path: Path, records: list[dict]) -> None:
    """Atomically overwrite file with one JSON object per line."""
    buf = b"".join(_dumps(rec).encode() + b"\n" for rec in records)
    write_bytes_atomic(path, buf)


def append_jsonl(path: Path, record: dict) -> None:
    """Append a single record to a .jsonl file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as f:
        f.write(_dumps(record).encode())
        f.write(b"\n")


class TransactionRepository:
    """Persistence operations for transaction ledgers."""

    def __init__(self, context: ProjectContext | None = None):
        self.context = context or ProjectContext()

    @property
    def path(self) -> Path:
        return self.context.transactions_path

    def get_all(self) -> list[Transaction]:
        return [Transaction.from_dict(d) for d in read_jsonl(self.path)]

    def get_all_dicts(self) -> list[dict]:
        return read_jsonl(self.path)

    def save_all(self, transactions: list[Transaction] | list[dict]) -> None:
        raw = [t.to_dict() if isinstance(t, Transaction) else t for t in transactions]
        write_jsonl(self.path, raw)

    def append(self, transaction: Transaction | dict) -> None:
        raw = transaction.to_dict() if isinstance(transaction, Transaction) else transaction
        append_jsonl(self.path, raw)


class SnapshotRepository:
    """Persistence operations for portfolio snapshots and benchmarks."""

    def __init__(self, context: ProjectContext | None = None):
        self.context = context or ProjectContext()

    @property
    def portfolio_path(self) -> Path:
        return self.context.portfolio_path

    def load_portfolio(self) -> list[PortfolioSnapshot]:
        return [PortfolioSnapshot.from_dict(d) for d in read_jsonl(self.portfolio_path)]

    def load_portfolio_dicts(self) -> list[dict]:
        return read_jsonl(self.portfolio_path)

    def save_portfolio(self, snapshots: list[PortfolioSnapshot] | list[dict]) -> None:
        raw = [s.to_dict() if isinstance(s, PortfolioSnapshot) else s for s in snapshots]
        write_jsonl(self.portfolio_path, raw)

    def invalidate_portfolio_from(self, from_date: str) -> None:
        if not self.portfolio_path.exists():
            return
        tmp = self.portfolio_path.with_suffix(".jsonl.tmp")
        with self.portfolio_path.open("rb") as src, tmp.open("wb") as dst:
            for line in src:
                stripped = line.strip()
                if not stripped:
                    continue
                rec = _loads(stripped)
                if str(rec.get("date", "")) < from_date:
                    dst.write(line)
        tmp.rename(self.portfolio_path)

    def load_benchmarks(self, base_ccy: str) -> list[dict] | None:
        p = self.context.benchmark_cache_path(base_ccy)
        if not p.exists():
            return None
        return _loads(p.read_bytes())

    def save_benchmarks(self, base_ccy: str, data: list[dict]) -> None:
        p = self.context.benchmark_cache_path(base_ccy)
        write_bytes_atomic(p, _dumps(data).encode())


class BalanceRepository:
    """Persistence operations for balance.json (holdings & avg_price)."""

    def __init__(self, context: ProjectContext | None = None):
        self.context = context or ProjectContext()

    @property
    def path(self) -> Path:
        return self.context.balance_path

    def load_balance(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        data = _loads(self.path.read_bytes())
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(self.path, _dumps(clean).encode())
