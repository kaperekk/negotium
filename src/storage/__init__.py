"""
storage package — low-level file I/O helpers and repositories with multi-project support.
"""
from __future__ import annotations

import threading
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from domain.currencies import (
    CURRENCY_SUFFIXES,
    CURRENCY_SYMBOLS,
    SUFFIX_CURRENCY,
    SUPPORTED_CURRENCIES,
    TRIANGULATE_VIA_USD,
)
from storage.context import (
    DATA_ROOT,
    ROOT,
    ProjectContext,
    get_current_project,
    set_current_project,
)
from storage.repositories import (
    BalanceRepository,
    SnapshotRepository,
    TransactionRepository,
    append_jsonl,
    iter_jsonl,
    read_jsonl,
    write_bytes_atomic,
    write_jsonl,
)

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


PRICES_DIR = DATA_ROOT / "prices"
ADJ_PRICES_DIR = DATA_ROOT / "prices_adj"
PROJECTS_PATH = DATA_ROOT / "projects.json"
TICKER_NAMES_PATH = DATA_ROOT / "ticker_names.json"
TICKER_META_PATH = DATA_ROOT / "ticker_meta.json"
ATH_PATH = DATA_ROOT / "ath.json"
EARNINGS_PATH = DATA_ROOT / "earnings.json"

_write_bytes_atomic = write_bytes_atomic


def current_project() -> str | None:
    return get_current_project()


def _project_dir(name: str | None = None) -> Path:
    return ProjectContext(name).project_dir


def transactions_path() -> Path:
    return ProjectContext().transactions_path


def portfolio_path() -> Path:
    return ProjectContext().portfolio_path


def balance_path() -> Path:
    return ProjectContext().balance_path


def imports_dir() -> Path:
    return ProjectContext().imports_dir


def benchmark_cache_path(base_ccy: str) -> Path:
    return ProjectContext().benchmark_cache_path(base_ccy)


def _load_registry() -> dict:
    if not PROJECTS_PATH.exists():
        return {}
    return _loads(PROJECTS_PATH.read_bytes())


def _save_registry(reg: dict) -> None:
    _write_bytes_atomic(PROJECTS_PATH, _dumps(reg).encode())


def list_projects() -> list[str]:
    if not PROJECTS_PATH.exists():
        return []
    return sorted(_load_registry().keys())


def get_last_refresh(name: str | None = None) -> str:
    name = name or current_project()
    if name is None:
        return ""
    reg = _load_registry()
    return reg.get(name, {}).get("last_refresh", "")


def set_last_refresh(date_str: str, name: str | None = None) -> None:
    name = name or current_project()
    if name is None:
        return
    reg = _load_registry()
    entry = reg.setdefault(name, {})
    entry["last_refresh"] = date_str
    _save_registry(reg)


def get_watchlist(name: str | None = None) -> list[str]:
    name = name or current_project()
    if name is None:
        return []
    reg = _load_registry()
    return list(reg.get(name, {}).get("watchlist", []))


def set_watchlist(tickers: list[str], name: str | None = None) -> None:
    name = name or current_project()
    if name is None:
        return
    reg = _load_registry()
    entry = reg.setdefault(name, {})
    entry["watchlist"] = list(tickers)
    _save_registry(reg)


def create_project(name: str) -> None:
    reg = _load_registry()
    if name in reg:
        raise ValueError(f"Project '{name}' already exists")
    ctx = ProjectContext(name)
    ctx.ensure_directories()
    reg[name] = {"created_at": datetime.now().isoformat()}
    _save_registry(reg)
    set_current_project(name)


def rename_project(old: str, new: str) -> None:
    reg = _load_registry()
    if old not in reg:
        raise ValueError(f"Project '{old}' not found")
    if new in reg:
        raise ValueError(f"Project '{new}' already exists")
    old_dir = _project_dir(old)
    new_dir = _project_dir(new)
    old_dir.rename(new_dir)
    reg[new] = reg.pop(old)
    _save_registry(reg)
    set_current_project(new)


def delete_project(name: str) -> None:
    import shutil
    reg = _load_registry()
    if name not in reg:
        return
    d = _project_dir(name)
    if d.exists():
        shutil.rmtree(d)
    del reg[name]
    _save_registry(reg)
    if current_project() == name:
        set_current_project(None)


def init_legacy_project() -> str | None:
    legacy_tx = DATA_ROOT / "transactions.jsonl"
    if not legacy_tx.exists():
        return None
    name = "default"
    ctx = ProjectContext(name)
    ctx.ensure_directories()
    for fname in ["transactions.jsonl", "portfolio.jsonl", "balance.json"]:
        src = DATA_ROOT / fname
        dst = ctx.project_dir / fname
        if src.exists() and not dst.exists():
            src.rename(dst)
    for p in DATA_ROOT.glob("benchmarks_*.json"):
        dst = ctx.project_dir / p.name
        if not dst.exists():
            p.rename(dst)
    build_log = DATA_ROOT / "build.log"
    if build_log.exists():
        build_log.unlink()
    reg = _load_registry()
    reg[name] = {"created_at": datetime.now().isoformat(), "migrated_from": "legacy"}
    _save_registry(reg)
    set_current_project(name)
    return name


def load_balance() -> dict[str, dict]:
    return BalanceRepository().load_balance()


def save_balance(balance: dict[str, dict]) -> None:
    BalanceRepository().save_balance(balance)


def price_cache_path(ticker: str, year: int, adjusted: bool = False) -> Path:
    base = ADJ_PRICES_DIR if adjusted else PRICES_DIR
    return base / ticker.upper() / f"{year}.json"


def load_price_year(ticker: str, year: int, adjusted: bool = False) -> dict[str, float]:
    p = price_cache_path(ticker, year, adjusted)
    if not p.exists():
        return {}
    return _loads(p.read_bytes())


def save_price_year(ticker: str, year: int, prices: dict[str, float], adjusted: bool = False) -> None:
    p = price_cache_path(ticker, year, adjusted)
    _write_bytes_atomic(p, _dumps(prices).encode())


def has_price_year(ticker: str, year: int, adjusted: bool = False) -> bool:
    return price_cache_path(ticker, year, adjusted).exists()


def load_prices_range(ticker: str, start: date, end: date, adjusted: bool = False) -> dict[str, float]:
    result: dict[str, float] = {}
    for year in range(start.year, end.year + 1):
        result.update(load_price_year(ticker, year, adjusted))
    return result


def load_portfolio() -> list[dict]:
    return SnapshotRepository().load_portfolio_dicts()


def save_portfolio(snapshots: list[dict]) -> None:
    SnapshotRepository().save_portfolio(snapshots)


def invalidate_portfolio_from(from_date: str) -> None:
    SnapshotRepository().invalidate_portfolio_from(from_date)


def save_benchmarks(base_ccy: str, data: list[dict]) -> None:
    SnapshotRepository().save_benchmarks(base_ccy, data)


def load_benchmarks(base_ccy: str) -> list[dict] | None:
    return SnapshotRepository().load_benchmarks(base_ccy)


_cache_lock = threading.Lock()
_ticker_names_cache: dict[str, str] | None = None


def load_ticker_names() -> dict[str, str]:
    global _ticker_names_cache
    if _ticker_names_cache is not None:
        return _ticker_names_cache
    if not TICKER_NAMES_PATH.exists():
        _ticker_names_cache = {}
        return _ticker_names_cache
    with _cache_lock:
        _ticker_names_cache = _loads(TICKER_NAMES_PATH.read_bytes())
    return _ticker_names_cache


def save_ticker_names(names: dict[str, str]) -> None:
    global _ticker_names_cache
    _ticker_names_cache = names
    with _cache_lock:
        _write_bytes_atomic(TICKER_NAMES_PATH, _dumps(names).encode())


_ticker_meta_cache: dict | None = None


def load_ticker_meta() -> dict:
    global _ticker_meta_cache
    if _ticker_meta_cache is not None:
        return _ticker_meta_cache
    if not TICKER_META_PATH.exists():
        _ticker_meta_cache = {}
        return _ticker_meta_cache
    with _cache_lock:
        _ticker_meta_cache = _loads(TICKER_META_PATH.read_bytes())
    return _ticker_meta_cache


def save_ticker_meta(meta: dict) -> None:
    global _ticker_meta_cache
    _ticker_meta_cache = meta
    with _cache_lock:
        _write_bytes_atomic(TICKER_META_PATH, _dumps(meta).encode())


_ath_disk_cache: dict | None = None


def load_ath() -> dict:
    global _ath_disk_cache
    if _ath_disk_cache is not None:
        return _ath_disk_cache
    if not ATH_PATH.exists():
        _ath_disk_cache = {}
        return _ath_disk_cache
    with _cache_lock:
        _ath_disk_cache = _loads(ATH_PATH.read_bytes())
    return _ath_disk_cache


def save_ath(data: dict) -> None:
    global _ath_disk_cache
    _ath_disk_cache = data
    with _cache_lock:
        _write_bytes_atomic(ATH_PATH, _dumps(data).encode())


_earnings_disk_cache: dict | None = None


def load_earnings() -> dict:
    global _earnings_disk_cache
    if _earnings_disk_cache is not None:
        return _earnings_disk_cache
    if not EARNINGS_PATH.exists():
        _earnings_disk_cache = {}
        return _earnings_disk_cache
    with _cache_lock:
        _earnings_disk_cache = _loads(EARNINGS_PATH.read_bytes())
    return _earnings_disk_cache


def save_earnings(data: dict) -> None:
    global _earnings_disk_cache
    _earnings_disk_cache = data
    with _cache_lock:
        _write_bytes_atomic(EARNINGS_PATH, _dumps(data).encode())


def dividend_cache_path(ticker: str) -> Path:
    return DATA_ROOT / "dividends" / f"{ticker.upper()}.json"


def load_dividends(ticker: str) -> dict[str, float]:
    p = dividend_cache_path(ticker)
    if not p.exists():
        return {}
    return _loads(p.read_bytes())


def save_dividends(ticker: str, data: dict[str, float]) -> None:
    p = dividend_cache_path(ticker)
    _write_bytes_atomic(p, _dumps(data).encode())
