"""
storage.py — low-level file I/O helpers

Layout:
  ROOT/data/transactions.jsonl  — transaction ledger
  ROOT/data/portfolio.jsonl     — computed snapshots
  ROOT/data/balance.json        — current holdings {ticker: amount}
  ROOT/data/benchmarks_{CCY}.json — hypothetical benchmark values
  ROOT/data/prices/{TICKER}/{YEAR}.json — daily close price cache
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import date
from typing import Iterator

ROOT = Path(__file__).parent.parent


DATA_ROOT         = ROOT / "data"
TRANSACTIONS_PATH = DATA_ROOT / "transactions.jsonl"
PORTFOLIO_PATH    = DATA_ROOT / "portfolio.jsonl"
BALANCE_PATH      = DATA_ROOT / "balance.json"
PRICES_DIR        = DATA_ROOT / "prices"

SUPPORTED_CURRENCIES: frozenset[str] = frozenset({"USD", "EUR", "PLN"})

CURRENCY_SUFFIXES: dict[str, list[str]] = {
    "EUR": [".DE", ".F", ".PA", ".MI", ".AS", ".BR", ".LS", ".MC", ".VI", ".IR"],
    "GBP": [".L"],
    "MXN": [".MX"],
    "CAD": [".TO"],
    "AUD": [".AX"],
    "HKD": [".HK"],
    "JPY": [".T"],
    "KRW": [".KS"],
    "CNY": [".SS", ".SZ"],
    "SGD": [".SG", ".SI"],
    "CHF": [".SW"],
    "BRL": [".SA"],
    "PLN": [".WA"],
}
SUFFIX_CURRENCY: dict[str, str] = {s: ccy for ccy, suffixes in CURRENCY_SUFFIXES.items() for s in suffixes}

# Currencies without direct {ccy}PLN=X on Yahoo — triangulate via USD instead
TRIANGULATE_VIA_USD: frozenset[str] = frozenset({"MXN"})


# ── JSONL helpers ──────────────────────────────────────────────────────────────

def iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield parsed dicts from a .jsonl file, skipping blank lines."""
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_jsonl(path: Path) -> list[dict]:
    return list(iter_jsonl(path))


def write_jsonl(path: Path, records: list[dict]) -> None:
    """Overwrite file with records (sorted by 'date' key if present)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, record: dict) -> None:
    """Append a single record to a .jsonl file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Balance ────────────────────────────────────────────────────────────────────

def load_balance() -> dict[str, dict]:
    """Return {ticker: {"amount": float, "avg_price": float}} dict."""
    if not BALANCE_PATH.exists():
        return {}
    with BALANCE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    result = {}
    for k, v in data.items():
        if isinstance(v, dict):
            result[k] = v
        else:
            result[k] = {"amount": v, "avg_price": 0.0}
    return result


def save_balance(balance: dict[str, dict]) -> None:
    """Persist balance, removing tickers with ~0 holdings."""
    clean = {}
    for k, v in balance.items():
        amt = v.get("amount", 0.0) if isinstance(v, dict) else v
        if abs(amt) > 1e-9:
            if isinstance(v, dict):
                clean[k] = {"amount": round(amt, 8), "avg_price": round(v.get("avg_price", 0.0), 6)}
            else:
                clean[k] = {"amount": round(amt, 8), "avg_price": 0.0}
    BALANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BALANCE_PATH.open("w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)


# ── Price cache ────────────────────────────────────────────────────────────────

def price_cache_path(ticker: str, year: int) -> Path:
    return PRICES_DIR / ticker.upper() / f"{year}.json"


def load_price_year(ticker: str, year: int) -> dict[str, float]:
    """Return {YYYY-MM-DD: close_price} for a ticker/year, or {} if missing."""
    p = price_cache_path(ticker, year)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_price_year(ticker: str, year: int, prices: dict[str, float]) -> None:
    """Persist {YYYY-MM-DD: close_price} for a ticker/year."""
    p = price_cache_path(ticker, year)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(prices, f, indent=2, ensure_ascii=False)


def has_price_year(ticker: str, year: int) -> bool:
    return price_cache_path(ticker, year).exists()


def load_prices_range(ticker: str, start: date, end: date) -> dict[str, float]:
    """
    Return merged {YYYY-MM-DD: close} for all years in [start.year, end.year].
    Uses the on-disk cache only — call ticker_data.ensure() first.
    """
    result: dict[str, float] = {}
    for year in range(start.year, end.year + 1):
        result.update(load_price_year(ticker, year))
    return result


# ── Portfolio snapshots ────────────────────────────────────────────────────────

def load_portfolio() -> list[dict]:
    return read_jsonl(PORTFOLIO_PATH)


def save_portfolio(snapshots: list[dict]) -> None:
    write_jsonl(PORTFOLIO_PATH, snapshots)


def invalidate_portfolio_from(from_date: str) -> None:
    """
    Remove all portfolio snapshots on or after from_date.
    Called when a transaction is inserted that affects a past date.
    """
    records = read_jsonl(PORTFOLIO_PATH)
    kept = [r for r in records if r["date"] < from_date]
    write_jsonl(PORTFOLIO_PATH, kept)


# ── Benchmark cache ──────────────────────────────────────────────────────────

def benchmark_cache_path(base_ccy: str) -> Path:
    return DATA_ROOT / f"benchmarks_{base_ccy.upper()}.json"


def save_benchmarks(base_ccy: str, data: list[dict]) -> None:
    """Save pre-computed benchmark values. Each entry: {date, ticker: value, ...}."""
    p = benchmark_cache_path(base_ccy)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_benchmarks(base_ccy: str) -> list[dict] | None:
    """Load cached benchmarks, or None if missing."""
    p = benchmark_cache_path(base_ccy)
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)
