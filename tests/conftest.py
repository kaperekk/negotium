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


@pytest.fixture
def tmp(tmp_path: Path):
    """Isolated per-test environment (replaces the old custom runner's
    make_temp_root + setup_env + cleanup cycle)."""
    import config
    import fixtures as fx
    import ledger_core
    import portfolio_core
    import storage
    import ticker_data

    # Reload so module-level globals (paths, caches, registries) re-init,
    # then point them at the temp root.
    for mod in (storage, config, ledger_core, portfolio_core, ticker_data):
        importlib.reload(mod)
    fx.patch_root(tmp_path)

    # Cache hygiene across tests sharing the reloaded modules.
    cache_fn = getattr(ledger_core.get_all_transactions, "_cache", None)
    if isinstance(cache_fn, dict):
        cache_fn.clear()

    yield tmp_path
