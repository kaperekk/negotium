"""
storage package — low-level file I/O helpers and repositories with multi-project support.
"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import date, datetime
from pathlib import Path

from domain.currencies import (
    CURRENCY_SUFFIXES,
    SUFFIX_CURRENCY,
    SUPPORTED_CURRENCIES,
    TRIANGULATE_VIA_USD,
)
# Re-export for backward compatibility
from storage.context import (
    DATA_ROOT,
    LOCAL_USER,
    ProjectContext,
    get_current_project,
    set_current_project,
    get_current_user,
    set_current_user,
)
from storage.repositories import (
    BalanceRepository,
    SnapshotRepository,
)
from storage.backends import get_backend
from storage.audit import (
    log_event,
    log_login_attempt,
    log_user_created,
    log_user_deleted,
    log_project_created,
    log_project_deleted,
    log_project_renamed,
    log_data_import,
    get_audit_log,
)

try:
    import orjson
    def _loads(data: bytes):
        return orjson.loads(data)
    def _dumps(obj) -> str:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2).decode()
    def _dumps_compact(obj) -> str:
        return orjson.dumps(obj).decode()
except ImportError:
    import json
    _loads = json.loads
    _dumps = lambda obj: json.dumps(obj, ensure_ascii=False, indent=2)
    _dumps_compact = lambda obj: json.dumps(obj, ensure_ascii=False)


USERS_KEY = "users.json"
TICKER_NAMES_KEY = "ticker_names.json"
TICKER_META_KEY = "ticker_meta.json"
ATH_KEY = "ath.json"
EARNINGS_KEY = "earnings.json"
PRICES_PREFIX = "prices/"
ADJ_PRICES_PREFIX = "prices_adj/"
DIVIDENDS_PREFIX = "dividends/"


def _backend():
    return get_backend()


def _read_json(key: str, default=None):
    backend = _backend()
    if not backend.exists(key):
        return default if default is not None else {}
    return _loads(backend.read_bytes(key))


def _write_json(key: str, data: dict) -> None:
    backend = _backend()
    backend.write_bytes(key, _dumps(data).encode())


def _read_bytes(key: str) -> bytes | None:
    backend = _backend()
    if not backend.exists(key):
        return None
    return backend.read_bytes(key)


def _write_bytes(key: str, data: bytes) -> None:
    backend = _backend()
    backend.write_bytes(key, data)


def _exists(key: str) -> bool:
    return _backend().exists(key)


def _list_keys(prefix: str) -> list[str]:
    return _backend().list_files(prefix)


def current_project() -> str | None:
    return get_current_project()


def current_user() -> str:
    return get_current_user()


def _projects_key(user: str | None = None) -> str:
    """Get projects registry key for a user."""
    user = user or current_user()
    return f"users/{user}/projects.json"


def _load_registry(user: str | None = None) -> dict:
    return _read_json(_projects_key(user))


def _save_registry(reg: dict, user: str | None = None) -> None:
    _write_json(_projects_key(user), reg)


def _load_users() -> dict:
    return _read_json(USERS_KEY)


def _save_users(users: dict) -> None:
    _write_json(USERS_KEY, users)


# Validation helpers
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")
PROJECT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{1,128}$")
TICKER_PATTERN = re.compile(r"^[A-Z0-9\.\-]{1,20}$")


def validate_username(name: str) -> str:
    """Validate and sanitize username."""
    name = name.strip()
    if not name:
        raise ValueError("Username cannot be empty")
    if not USERNAME_PATTERN.match(name):
        raise ValueError("Username must be 1-64 chars: letters, numbers, _, -, .")
    return name


def validate_project_name(name: str) -> str:
    """Validate and sanitize project name."""
    name = name.strip()
    if not name:
        raise ValueError("Project name cannot be empty")
    if not PROJECT_NAME_PATTERN.match(name):
        raise ValueError("Project name must be 1-128 chars: letters, numbers, _, -, .")
    return name


def validate_ticker(ticker: str) -> str:
    """Validate and sanitize ticker symbol."""
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Ticker cannot be empty")
    if not TICKER_PATTERN.match(ticker):
        raise ValueError("Invalid ticker format")
    return ticker


def create_user(name: str) -> None:
    """Create a new user with their data directory."""
    name = validate_username(name)
    users = _load_users()
    for data in users.values():
        if data.get("user_name") == name:
            raise ValueError(f"User '{name}' already exists")
    user_key = str(uuid.uuid4())
    users[user_key] = {"user_name": name, "created": date.today().isoformat()}
    _save_users(users)
    set_current_user(name)
    log_user_created(name, user_key)


def list_users() -> list[str]:
    users = _load_users()
    return sorted(data.get("user_name", "") for data in users.values() if data.get("user_name"))


def get_user_by_key(user_key: str) -> str | None:
    """Get user_name by user_key."""
    if not user_key or not isinstance(user_key, str):
        return None
    users = _load_users()
    if user_key in users:
        return users[user_key].get("user_name")
    return None


def set_current_user_by_key(user_key: str) -> None:
    """Set current user by their UUID key."""
    user_name = get_user_by_key(user_key)
    if user_name:
        set_current_user(user_name)
    else:
        set_current_user(LOCAL_USER)


def list_projects(user: str | None = None) -> list[str]:
    user = user or current_user()
    reg = _load_registry(user)
    return sorted([name for name, data in reg.items() if data.get("user", LOCAL_USER) == user])


def get_last_refresh(name: str | None = None, user: str | None = None) -> str:
    user = user or current_user()
    name = name or current_project()
    if name is None:
        return ""
    reg = _load_registry(user)
    return reg.get(name, {}).get("last_refresh", "")


def set_last_refresh(date_str: str, name: str | None = None, user: str | None = None) -> None:
    user = user or current_user()
    name = name or current_project()
    if name is None:
        return
    reg = _load_registry(user)
    entry = reg.setdefault(name, {})
    entry["last_refresh"] = date_str
    _save_registry(reg, user)


def get_watchlist(name: str | None = None, user: str | None = None) -> list[str]:
    user = user or current_user()
    name = name or current_project()
    if name is None:
        return []
    reg = _load_registry(user)
    return list(reg.get(name, {}).get("watchlist", []))


def set_watchlist(tickers: list[str], name: str | None = None) -> None:
    user = user or current_user()
    name = name or current_project()
    if name is None:
        return
    reg = _load_registry(user)
    entry = reg.setdefault(name, {})
    entry["watchlist"] = list(tickers)
    _save_registry(reg, user)


def create_project(name: str, user: str | None = None) -> None:
    user = user or current_user()
    name = validate_project_name(name)
    reg = _load_registry(user)
    for proj_name, data in reg.items():
        if data.get("user", LOCAL_USER) == user and proj_name == name:
            raise ValueError(f"Project '{name}' already exists")
    ctx = ProjectContext(name, user)
    ctx.ensure_directories()
    reg[name] = {"created_at": datetime.now().isoformat(), "user": user}
    _save_registry(reg, user)
    set_current_project(name)
    log_project_created(name, user)


def rename_project(old: str, new: str, user: str | None = None) -> None:
    user = user or current_user()
    old = validate_project_name(old)
    new = validate_project_name(new)
    reg = _load_registry(user)
    if old not in reg:
        raise ValueError(f"Project '{old}' not found")
    if reg[old].get("user", LOCAL_USER) != user:
        raise ValueError(f"Project '{old}' does not belong to user '{user}'")
    if new in reg:
        raise ValueError(f"Project '{new}' already exists")
    old_prefix = f"users/{user}/{old}/"
    new_prefix = f"users/{user}/{new}/"
    backend = _backend()
    for key in backend.list_files(old_prefix):
        new_key = new_prefix + key[len(old_prefix):]
        data = backend.read_bytes(key)
        backend.write_bytes(new_key, data)
        backend.delete(key)
    reg[new] = reg.pop(old)
    _save_registry(reg, user)
    set_current_project(new)
    log_project_renamed(old, new, user)


def delete_project(name: str, user: str | None = None) -> None:
    user = user or current_user()
    name = validate_project_name(name)
    reg = _load_registry(user)
    if name not in reg:
        return
    if reg[name].get("user", LOCAL_USER) != user:
        raise ValueError(f"Project '{name}' does not belong to user '{user}'")
    prefix = f"users/{user}/{name}/"
    backend = _backend()
    for key in backend.list_files(prefix):
        backend.delete(key)
    del reg[name]
    _save_registry(reg, user)
    log_project_deleted(name, user)
    if current_project() == name:
        set_current_project(None)


def init_legacy_project() -> str | None:
    legacy_tx = DATA_ROOT / "transactions.jsonl"
    if not legacy_tx.exists():
        return None
    name = "default"
    user = current_user()
    ctx = ProjectContext(name, user)
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
    reg = _load_registry(user)
    reg[name] = {"created_at": datetime.now().isoformat(), "user": user, "migrated_from": "legacy"}
    _save_registry(reg, user)
    set_current_project(name)
    return name


def load_balance() -> dict[str, dict]:
    return BalanceRepository().load_balance()


def save_balance(balance: dict[str, dict]) -> None:
    BalanceRepository().save_balance(balance)


def _price_key(ticker: str, year: int, adjusted: bool) -> str:
    base = ADJ_PRICES_PREFIX if adjusted else PRICES_PREFIX
    return f"{base}{ticker.upper()}/{year}.json"


def load_price_year(ticker: str, year: int, adjusted: bool = False) -> dict[str, float]:
    key = _price_key(ticker, year, adjusted)
    data = _read_bytes(key)
    if data is None:
        return {}
    return _loads(data)


def save_price_year(ticker: str, year: int, prices: dict[str, float], adjusted: bool = False) -> None:
    key = _price_key(ticker, year, adjusted)
    _write_bytes(key, _dumps(prices).encode())


def has_price_year(ticker: str, year: int, adjusted: bool = False) -> bool:
    return _exists(_price_key(ticker, year, adjusted))


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
    data = _read_bytes(TICKER_NAMES_KEY)
    if data is None:
        _ticker_names_cache = {}
        return _ticker_names_cache
    with _cache_lock:
        _ticker_names_cache = _loads(data)
    return _ticker_names_cache


def save_ticker_names(names: dict[str, str]) -> None:
    global _ticker_names_cache
    _ticker_names_cache = names
    with _cache_lock:
        _write_bytes(TICKER_NAMES_KEY, _dumps(names).encode())


_ticker_meta_cache: dict | None = None


def load_ticker_meta() -> dict:
    global _ticker_meta_cache
    if _ticker_meta_cache is not None:
        return _ticker_meta_cache
    data = _read_bytes(TICKER_META_KEY)
    if data is None:
        _ticker_meta_cache = {}
        return _ticker_meta_cache
    with _cache_lock:
        _ticker_meta_cache = _loads(data)
    return _ticker_meta_cache


def save_ticker_meta(meta: dict) -> None:
    global _ticker_meta_cache
    _ticker_meta_cache = meta
    with _cache_lock:
        _write_bytes(TICKER_META_KEY, _dumps(meta).encode())


_ath_disk_cache: dict | None = None


def load_ath() -> dict:
    global _ath_disk_cache
    if _ath_disk_cache is not None:
        return _ath_disk_cache
    data = _read_bytes(ATH_KEY)
    if data is None:
        _ath_disk_cache = {}
        return _ath_disk_cache
    with _cache_lock:
        _ath_disk_cache = _loads(data)
    return _ath_disk_cache


def save_ath(data: dict) -> None:
    global _ath_disk_cache
    _ath_disk_cache = data
    with _cache_lock:
        _write_bytes(ATH_KEY, _dumps(data).encode())


_earnings_disk_cache: dict | None = None


def load_earnings() -> dict:
    global _earnings_disk_cache
    if _earnings_disk_cache is not None:
        return _earnings_disk_cache
    data = _read_bytes(EARNINGS_KEY)
    if data is None:
        _earnings_disk_cache = {}
        return _earnings_disk_cache
    with _cache_lock:
        _earnings_disk_cache = _loads(data)
    return _earnings_disk_cache


def save_earnings(data: dict) -> None:
    global _earnings_disk_cache
    _earnings_disk_cache = data
    with _cache_lock:
        _write_bytes(EARNINGS_KEY, _dumps(data).encode())


def _dividend_key(ticker: str) -> str:
    return f"{DIVIDENDS_PREFIX}{ticker.upper()}.json"


def load_dividends(ticker: str) -> dict[str, float]:
    key = _dividend_key(ticker)
    data = _read_bytes(key)
    if data is None:
        return {}
    return _loads(data)


def save_dividends(ticker: str, data: dict[str, float]) -> None:
    key = _dividend_key(ticker)
    _write_bytes(key, _dumps(data).encode())


# Backward compatibility functions for code that still uses Path-based access
def transactions_path() -> Path:
    """Get the transactions file path for the current project (local filesystem)."""
    return ProjectContext().transactions_path


def portfolio_path() -> Path:
    """Get the portfolio file path for the current project (local filesystem)."""
    return ProjectContext().portfolio_path


def balance_path() -> Path:
    """Get the balance file path for the current project (local filesystem)."""
    return ProjectContext().balance_path


def imports_dir() -> Path:
    """Get the imports directory for the current project (local filesystem)."""
    return ProjectContext().imports_dir


def benchmark_cache_path(base_ccy: str) -> Path:
    """Get the benchmark cache file path for the current project (local filesystem)."""
    return ProjectContext().benchmark_cache_path(base_ccy)


# Backward compatibility: Path-based read/write for JSONL
def read_jsonl(path: Path) -> list[dict]:
    """Read JSONL from a local file path (for backward compatibility)."""
    if not path.exists():
        return []
    with path.open("rb") as f:
        return [_loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, records: list[dict]) -> None:
    """Write JSONL to a local file path (for backward compatibility)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as f:
        for rec in records:
            f.write(_dumps_compact(rec).encode())
            f.write(b"\n")
    tmp.replace(path)


def append_jsonl(path: Path, record: dict) -> None:
    """Append a record to a JSONL file (for backward compatibility)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as f:
        f.write(_dumps_compact(record).encode())
        f.write(b"\n")


def _project_dir(name: str | None = None, user: str | None = None) -> Path:
    """Get the project directory for the given project/user (local filesystem)."""
    return ProjectContext(name, user).project_dir