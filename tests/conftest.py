"""Shared pytest fixtures for the Negotium test suite.

Each test receives a `tmp` fixture: a fresh pytest temp directory with all
storage/config module globals patched to it and domain modules reloaded, so
tests are fully isolated from real user data.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
for _p in (str(SRC), str(ROOT), str(TESTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# Modules that need reloading after paths are patched
_RELOAD_MODULES = (
    "storage.context",
    "storage",
    "config",
    "ledger_core",
    "portfolio_core",
    "ticker_data",
    "xtb_import",
    "bossa_import",
    "manual_import",
    "services.import_service",
    "services.importers.base",
    "services.importers.xtb",
    "services.importers.bossa",
    "services.importers.manual",
    "services.portfolio_service",
    "isin_resolve",
    "ticker_translate",
    "currencies",
    "domain.models",
    "domain.currencies",
    "domain.exceptions",
    "ui.runtime",
    "ui.bootstrap",
    "ui.auth",
    "ui.sidebar",
    "ui.dashboard",
    "ui.holdings",
    "ui.allocation",
    "ui.trade_history",
    "ui.drawdown",
    "ui.watchlist",
    "ui.metrics",
    "ui.portfolio_chart",
    "ui.sizes",
    "ui.colors",
    "ui.styles",
    "ui.helpers",
    "ui.bootstrap",
)


def _reload_all():
    for name in _RELOAD_MODULES:
        try:
            mod = sys.modules.get(name)
            if mod:
                importlib.reload(mod)
        except Exception:
            pass  # Module not loaded yet, will be loaded fresh


@pytest.fixture(autouse=True)
def tmp(tmp_path: Path):
    """Isolated per-test environment (replaces the old custom runner's
    make_temp_root + setup_env + cleanup cycle)."""
    import fixtures as fx

    # First patch the roots, then reload modules so they pick up the patched paths.
    fx.patch_root(tmp_path)
    _reload_all()

    # Cache hygiene across tests sharing the reloaded modules.
    import ledger_core
    cache_fn = getattr(ledger_core.get_all_transactions, "_cache", None)
    if isinstance(cache_fn, dict):
        cache_fn.clear()

    yield tmp_path