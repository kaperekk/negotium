"""
storage.py — low-level file I/O helpers with multi-project support

Layout:
  ROOT/data/prices/{TICKER}/{YEAR}.json  — shared price cache
  ROOT/data/projects.json                — project registry
  ROOT/data/{project}/config.json        — per-project config overrides
  ROOT/data/{project}/transactions.jsonl — transaction ledger
  ROOT/data/{project}/portfolio.jsonl    — computed snapshots
  ROOT/data/{project}/balance.json       — current holdings
  ROOT/data/{project}/benchmarks_{CCY}.json — benchmark values
  ROOT/data/{project}/imports/           — per-project import files
"""
from __future__ import annotations

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
from pathlib import Path
from datetime import date, datetime
from typing import Iterator

ROOT = Path(__file__).parent.parent

DATA_ROOT     = ROOT / "data"
PRICES_DIR    = DATA_ROOT / "prices"
PROJECTS_PATH = DATA_ROOT / "projects.json"

# ── Current project state ─────────────────────────────────────────────────────

_current_project: str | None = None

TRANSACTIONS_PATH = DATA_ROOT / "transactions.jsonl"
PORTFOLIO_PATH    = DATA_ROOT / "portfolio.jsonl"
BALANCE_PATH      = DATA_ROOT / "balance.json"
IMPORTS_DIR       = Path("imports")


def _project_dir(name: str | None = None) -> Path:
    """Return the data directory for a project."""
    n = name or _current_project
    if n is None:
        raise RuntimeError("No project selected. Call set_current_project() first.")
    return DATA_ROOT / n


def set_current_project(name: str) -> None:
    """Set the active project — updates all project-scoped paths."""
    global _current_project
    global TRANSACTIONS_PATH, PORTFOLIO_PATH, BALANCE_PATH, IMPORTS_DIR

    _current_project = name
    d = _project_dir(name)
    TRANSACTIONS_PATH = d / "transactions.jsonl"
    PORTFOLIO_PATH    = d / "portfolio.jsonl"
    BALANCE_PATH      = d / "balance.json"
    IMPORTS_DIR       = d / "imports"


def get_current_project() -> str | None:
    return _current_project


def project_config_path(name: str | None = None) -> Path:
    return _project_dir(name) / "config.json"


# ── Project registry ──────────────────────────────────────────────────────────

def list_projects() -> list[str]:
    """Return sorted list of project names."""
    if not PROJECTS_PATH.exists():
        return []
    return sorted(_loads(PROJECTS_PATH.read_bytes()).keys())


def _load_registry() -> dict:
    if not PROJECTS_PATH.exists():
        return {}
    return _loads(PROJECTS_PATH.read_bytes())


def _save_registry(reg: dict) -> None:
    PROJECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROJECTS_PATH.write_bytes(_dumps(reg).encode())


def create_project(name: str) -> None:
    """Create a new empty project."""
    reg = _load_registry()
    if name in reg:
        raise ValueError(f"Project '{name}' already exists")
    _project_dir(name).mkdir(parents=True, exist_ok=True)
    (_project_dir(name) / "imports").mkdir(exist_ok=True)
    reg[name] = {"created_at": datetime.now().isoformat()}
    _save_registry(reg)
    set_current_project(name)


def rename_project(old: str, new: str) -> None:
    """Rename a project directory and update registry."""
    reg = _load_registry()
    if old not in reg:
        raise ValueError(f"Project '{old}' not found")
    if new in reg:
        raise ValueError(f"Project '{new}' already exists")
    old_dir = _project_dir(old)
    new_dir = DATA_ROOT / new
    old_dir.rename(new_dir)
    reg[new] = reg.pop(old)
    _save_registry(reg)
    set_current_project(new)


def delete_project(name: str) -> None:
    """Delete a project and all its data."""
    import shutil
    reg = _load_registry()
    if name not in reg:
        return
    d = _project_dir(name)
    if d.exists():
        shutil.rmtree(d)
    del reg[name]
    _save_registry(reg)


def init_legacy_project() -> str | None:
    """If legacy flat files exist at data/ root, migrate them into a 'default' project.
    Returns the project name if migration happened, else None."""
    legacy_tx = DATA_ROOT / "transactions.jsonl"
    if not legacy_tx.exists():
        return None
    name = "default"
    d = _project_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "imports").mkdir(exist_ok=True)
    for fname in ["transactions.jsonl", "portfolio.jsonl", "balance.json"]:
        src = DATA_ROOT / fname
        dst = d / fname
        if src.exists() and not dst.exists():
            src.rename(dst)
    for p in DATA_ROOT.glob("benchmarks_*.json"):
        dst = d / p.name
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


# ── Supported currencies ──────────────────────────────────────────────────────

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

TRIANGULATE_VIA_USD: frozenset[str] = frozenset({"MXN"})


# ── JSONL helpers ──────────────────────────────────────────────────────────────

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
    """Overwrite file with records (sorted by 'date' key if present)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        for rec in records:
            f.write(_dumps(rec).encode())
            f.write(b"\n")


def append_jsonl(path: Path, record: dict) -> None:
    """Append a single record to a .jsonl file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as f:
        f.write(_dumps(record).encode())
        f.write(b"\n")


# ── Balance ────────────────────────────────────────────────────────────────────

def load_balance() -> dict[str, dict]:
    """Return {ticker: {"amount": float, "avg_price": float}} dict."""
    if not BALANCE_PATH.exists():
        return {}
    data = _loads(BALANCE_PATH.read_bytes())
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
    BALANCE_PATH.write_bytes(_dumps(clean).encode())


# ── Price cache (shared) ──────────────────────────────────────────────────────

def price_cache_path(ticker: str, year: int) -> Path:
    return PRICES_DIR / ticker.upper() / f"{year}.json"


def load_price_year(ticker: str, year: int) -> dict[str, float]:
    """Return {YYYY-MM-DD: close_price} for a ticker/year, or {} if missing."""
    p = price_cache_path(ticker, year)
    if not p.exists():
        return {}
    return _loads(p.read_bytes())


def save_price_year(ticker: str, year: int, prices: dict[str, float]) -> None:
    """Persist {YYYY-MM-DD: close_price} for a ticker/year."""
    p = price_cache_path(ticker, year)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_dumps(prices).encode())


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
    Streams line-by-line to avoid loading the entire file into memory.
    """
    if not PORTFOLIO_PATH.exists():
        return
    tmp = PORTFOLIO_PATH.with_suffix(".jsonl.tmp")
    with PORTFOLIO_PATH.open("rb") as src, tmp.open("wb") as dst:
        from_date_bytes = from_date.encode()
        for line in src:
            stripped = line.strip()
            if stripped and stripped[9:19] < from_date_bytes:
                dst.write(line)
    tmp.rename(PORTFOLIO_PATH)


# ── Benchmark cache ──────────────────────────────────────────────────────────

def benchmark_cache_path(base_ccy: str) -> Path:
    return _project_dir() / f"benchmarks_{base_ccy.upper()}.json"


def save_benchmarks(base_ccy: str, data: list[dict]) -> None:
    """Save pre-computed benchmark values. Each entry: {date, ticker: value, ...}."""
    p = benchmark_cache_path(base_ccy)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_dumps(data).encode())


def load_benchmarks(base_ccy: str) -> list[dict] | None:
    """Load cached benchmarks, or None if missing."""
    p = benchmark_cache_path(base_ccy)
    if not p.exists():
        return None
    return _loads(p.read_bytes())
