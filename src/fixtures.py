"""
fixtures.py — test helpers and fake data

Tests operate in a completely isolated temp directory so they never
touch real data files.
"""
from __future__ import annotations

import os
import sys
import tempfile
import shutil
from datetime import date
from pathlib import Path


def make_temp_root() -> Path:
    """Create and return a fresh temp directory for one test run."""
    return Path(tempfile.mkdtemp(prefix="investment_tracker_test_"))


def patch_root(tmp: Path):
    """
    Monkey-patch all storage paths to point at tmp.
    Must be called before importing any src module in a test,
    or the modules must be reloaded after the patch.
    """
    import storage
    import config as cfg_module
    import transactions
    import portfolio
    import ticker_data

    storage.ROOT               = tmp
    storage.DATA_ROOT          = tmp / "data"
    storage.PRICES_DIR         = tmp / "data" / "prices"
    storage.PROJECTS_PATH      = tmp / "data" / "projects.json"

    # Set up a default test project
    test_project = tmp / "data" / "test_project"
    test_project.mkdir(parents=True, exist_ok=True)
    (test_project / "imports").mkdir(exist_ok=True)
    storage.set_current_project("test_project")
    storage._current_project = "test_project"
    storage.TRANSACTIONS_PATH  = test_project / "transactions.jsonl"
    storage.PORTFOLIO_PATH     = test_project / "portfolio.jsonl"
    storage.BALANCE_PATH       = test_project / "balance.json"
    storage.IMPORTS_DIR        = test_project / "imports"

    cfg_module.ROOT                = tmp
    cfg_module.GLOBAL_CONFIG_PATH  = tmp / "data" / "config.json"


SAMPLE_CONFIG = {
    "name": "Test Portfolio",
    "start_day": "2023-01-01",
    "default_currency": "PLN",
    "graph_precision": "1D",
}

# Fake price data that get_price() will return via monkeypatched cache
FAKE_AAPL_PRICES = {
    "2023-01-03": 125.07,
    "2023-01-04": 126.36,
    "2023-01-05": 125.02,
    "2023-01-06": 129.62,
    "2023-01-09": 130.15,
    "2023-06-01": 180.09,
    "2023-12-29": 192.53,
}

FAKE_USDPLN_PRICES = {
    "2023-01-03": 4.38,
    "2023-01-04": 4.37,
    "2023-01-05": 4.36,
    "2023-01-06": 4.35,
    "2023-01-09": 4.34,
    "2023-06-01": 4.10,
    "2023-12-29": 3.98,
}

FAKE_EURPLN_PRICES = {
    "2023-01-03": 4.68,
    "2023-01-04": 4.67,
    "2023-01-09": 4.66,
    "2023-12-29": 4.27,
}

FAKE_EURUSD_PRICES = {
    "2023-01-03": 1.069,
    "2023-01-04": 1.068,
    "2023-01-09": 1.074,
    "2023-12-29": 1.073,
}


def inject_fake_prices(tmp: Path):
    """Write fake price JSON files into the temp data directory."""
    import json

    def write(ticker: str, year: int, prices: dict):
        p = tmp / "data" / "prices" / ticker / f"{year}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(prices))

    write("AAPL",   2023, FAKE_AAPL_PRICES)
    write("USDPLN", 2023, FAKE_USDPLN_PRICES)
    write("EURPLN", 2023, FAKE_EURPLN_PRICES)
    write("EURUSD", 2023, FAKE_EURUSD_PRICES)
