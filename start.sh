#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#   Negotium - Investment Tracker — launcher
#  Usage:  ./start.sh                 run tests then start UI
#          ./start.sh --skip-tests    skip tests, start UI only
#          ./start.sh --tests-only    run tests, don't start UI
#          ./start.sh --port 8502     custom port (default 8501)
#          ./start.sh --reset         wipe all data and start fresh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SKIP_TESTS=false
TESTS_ONLY=false
RESET=false
PORT=8501

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests)  SKIP_TESTS=true  ; shift ;;
    --tests-only)  TESTS_ONLY=true  ; shift ;;
    --reset)       RESET=true       ; shift ;;
    --port)        PORT="$2"        ; shift 2 ;;
    -h|--help)     grep '^#  ' "$0" | sed 's/#  //'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

BOLD='\033[1m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; RESET_C='\033[0m'

# ── Find Python ───────────────────────────────────────────────
PYTHON=""
for cmd in python3.14 python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cmd" &>/dev/null; then
    VER=$("$cmd" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")
    if [[ "$VER" == "True" ]]; then
      PYTHON="$cmd"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo -e "${RED}✗ Python 3.10+ not found.${RESET_C}"
  exit 1
fi

echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${RESET_C}"
echo -e "${BOLD}  📈  Negotium - Investment Tracker${RESET_C}"
echo -e "${BOLD}═══════════════════════════════════════════════${RESET_C}"
echo ""
echo -e "  Python:  $($PYTHON --version)"
echo -e "  Dir:     $SCRIPT_DIR"

# ── Optional reset ────────────────────────────────────────────
if [[ "$RESET" == "true" ]]; then
  echo ""
  echo -e "${YELLOW}  --reset: removing all data files…${RESET_C}"
  rm -f transactions.jsonl portfolio.jsonl balance.json
  rm -rf data/
  echo -e "${GREEN}  ✓ Data cleared. Starting fresh.${RESET_C}"
fi

# ── Ensure required directories exist ────────────────────────
mkdir -p data imports

# ── Check / install dependencies ─────────────────────────────
echo ""
echo -e "  Checking dependencies…"
MISSING=()
for pkg in yfinance streamlit plotly pandas orjson openpyxl python_calamine; do
  if ! "$PYTHON" -c "import $pkg" &>/dev/null 2>&1; then
    MISSING+=("$pkg")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo -e "  ${YELLOW}Installing: ${MISSING[*]}${RESET_C}"
  "$PYTHON" -m pip install "${MISSING[@]}" --break-system-packages -q 2>/dev/null \
    || "$PYTHON" -m pip install "${MISSING[@]}" -q
fi
echo -e "  ${GREEN}✓ Dependencies ready${RESET_C}"
echo ""

# ── Run tests ─────────────────────────────────────────────────
if [[ "$SKIP_TESTS" == "false" ]]; then
  echo -e "${BOLD}Running tests…${RESET_C}"
  echo ""
  if "$PYTHON" tests/test_runner.py; then
    echo ""
  else
    echo ""
    echo -e "${RED}✗ Tests failed. Use --skip-tests to launch anyway.${RESET_C}"
    exit 1
  fi
fi

[[ "$TESTS_ONLY" == "true" ]] && { echo "Tests complete."; exit 0; }

# ── Launch ────────────────────────────────────────────────────
echo -e "${BOLD}Starting app → http://localhost:${PORT}${RESET_C}"
echo -e "  Press ${BOLD}Ctrl+C${RESET_C} to stop."
echo ""

exec "$PYTHON" -m streamlit run src/app.py \
  --server.port "$PORT" \
  --server.headless true \
  --server.runOnSave true \
  --browser.gatherUsageStats false \
  --theme.base dark \
  --theme.primaryColor "#3b82f6" \
  --theme.backgroundColor "#0f172a" \
  --theme.secondaryBackgroundColor "#1e293b" \
  --theme.textColor "#f1f5f9"
