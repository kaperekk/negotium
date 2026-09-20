#!/usr/bin/env python3
"""
Standalone performance test runner for Yahoo Finance download pipeline.

Usage:
    python tests/run_perf_download.py              # run both tests
    python tests/run_perf_download.py --full       # full history only
    python tests/run_perf_download.py --day        # single day only

No pytest required — just run directly.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
from datetime import date
from pathlib import Path

# Setup paths
TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
SRC = ROOT / "src"
for _p in (str(SRC), str(ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from test_performance_download import (
    PERF_TICKERS,
    test_perf_download_full_history,
    test_perf_download_single_day,
)


def main():
    parser = argparse.ArgumentParser(description="Run download performance tests")
    parser.add_argument("--full", action="store_true", help="Run full history test only")
    parser.add_argument("--day", action="store_true", help="Run single day test only")
    args = parser.parse_args()

    run_full = not args.day or args.full
    run_day = not args.full or args.day

    if run_full:
        with tempfile.TemporaryDirectory(prefix="perf_full_") as tmp:
            test_perf_download_full_history(Path(tmp))

    if run_day:
        with tempfile.TemporaryDirectory(prefix="perf_day_") as tmp:
            test_perf_download_single_day(Path(tmp))


if __name__ == "__main__":
    main()
