#!/usr/bin/env bash
# Test runner script for Negotium.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "============================================================"
echo "🧪 Negotium Test Runner"
echo "============================================================"

PYTHONPATH=src .venv/bin/python -m pytest tests/ \
    --ignore=tests/test_range_refresh_regression.py \
    -v --tb=short "$@"