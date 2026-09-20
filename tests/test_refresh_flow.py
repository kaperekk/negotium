"""Integration test: simulates the full 'Refresh market data' flow.

Covers the pipeline from broker file import through market-data download,
balance rebuild, and portfolio construction — the same steps that run when
the user clicks "Refresh data" in the sidebar.

Some tests hit the real Yahoo Finance API (marked ``slow``), others use
mocked price data to run offline.

Run with:
    pytest tests/test_refresh_flow.py -v
    pytest tests/test_refresh_flow.py -v -m slow   # network tests only
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_xtb_xlsx(
    path: Path,
    rows: list[list],
    *,
    sheet_name: str = "Cash Operations",
) -> None:
    """Build a minimal XTB-style Excel file with a Cash Operations sheet."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet(sheet_name)

    header = ["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"]
    ws.append(header)
    for row in rows:
        ws.append(row)

    del wb["Sheet"]
    wb.save(str(path))
    wb.close()


def _count_price_files(tmp: Path, ticker: str) -> int:
    """How many year-cache files exist for a ticker."""
    d = tmp / "data" / "prices" / ticker
    if not d.exists():
        return 0
    return len(list(d.glob("*.json")))


def _inject_prices(tmp: Path, data: list[tuple[str, int, dict[str, float]]]) -> None:
    """Write fake price JSON files into the temp data directory."""
    import json
    prices_dir = tmp / "data" / "prices"
    for ticker, year, prices in data:
        p = prices_dir / ticker / f"{year}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(prices))


# ---------------------------------------------------------------------------
# Import-only tests (no network)
# ---------------------------------------------------------------------------

def test_full_import_and_balance(tmp: Path):
    """Import XTB file → ledger → balance, no network needed."""
    import storage
    from ledger_core import get_all_transactions, rebuild_balance
    from xtb_import import import_xtb

    imports_dir = storage.imports_dir() / "xtb"
    imports_dir.mkdir(parents=True, exist_ok=True)

    xlsx = imports_dir / "statement.xlsx"
    _make_xtb_xlsx(xlsx, [
        ["Deposit", "USD", "", "2025-01-06 10:00:00", 10000, 1, "Deposit"],
        ["Stock purchase", "AAPL", "Apple Inc.",
         "2025-01-06 10:05:00", -1925.30, 2, "OPEN BUY 10/10 @ 192.53"],
        ["Stock purchase", "MSFT", "Microsoft",
         "2025-01-06 10:10:00", -2028.40, 3, "OPEN BUY 5/5 @ 405.68"],
    ])

    result = import_xtb(str(xlsx), "USD")
    assert result["success"] is True
    assert result["imported"] >= 1

    txns = get_all_transactions()
    assert len(txns) >= 1

    rebuild_balance()
    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 10.0
    assert bal["MSFT"]["amount"] == 5.0
    assert bal["USD"]["amount"] > 0  # remaining cash


def test_refresh_idempotent(tmp: Path):
    """Re-importing the same XTB file does not duplicate transactions."""
    import storage
    from ledger_core import get_all_transactions
    from xtb_import import import_xtb

    imports_dir = storage.imports_dir() / "xtb"
    imports_dir.mkdir(parents=True, exist_ok=True)

    xlsx = imports_dir / "idem.xlsx"
    _make_xtb_xlsx(xlsx, [
        ["Deposit", "USD", "", "2025-03-01 10:00:00", 5000, 1, "Deposit"],
        ["Stock purchase", "AAPL", "Apple",
         "2025-03-01 10:05:00", -962.65, 2, "OPEN BUY 5/5 @ 192.53"],
    ])

    r1 = import_xtb(str(xlsx), "USD")
    assert r1["success"] is True
    count1 = len(get_all_transactions())

    r2 = import_xtb(str(xlsx), "USD")
    assert r2["success"] is True
    count2 = len(get_all_transactions())
    assert count2 == count1, "Re-import should not add duplicate transactions"


def test_refresh_after_manual_entry(tmp: Path):
    """Manual ledger entry survives a refresh import and re-import cycle."""
    import storage
    from ledger_core import add_transaction, rebuild_balance
    from xtb_import import import_xtb

    add_transaction("2025-06-01", [
        {"ticker": "AAPL", "amount": 3.0},
        {"ticker": "USD", "amount": -577.59},
    ])

    imports_dir = storage.imports_dir() / "xtb"
    imports_dir.mkdir(parents=True, exist_ok=True)

    xlsx = imports_dir / "after_manual.xlsx"
    _make_xtb_xlsx(xlsx, [
        ["Stock purchase", "AAPL", "Apple",
         "2025-07-15 10:05:00", -960.00, 1, "OPEN BUY 5/5 @ 192.00"],
    ])

    result = import_xtb(str(xlsx), "USD")
    assert result["success"] is True

    rebuild_balance()
    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 8.0  # 3 manual + 5 broker


def test_refresh_with_mocked_download(tmp: Path):
    """Import + injected prices → balance → portfolio build (no network)."""
    import json
    import storage
    from ledger_core import get_all_transactions, rebuild_balance
    from xtb_import import import_xtb

    imports_dir = storage.imports_dir() / "xtb"
    imports_dir.mkdir(parents=True, exist_ok=True)

    xlsx = imports_dir / "mock_dl.xlsx"
    _make_xtb_xlsx(xlsx, [
        ["Deposit", "USD", "", "2025-01-06 10:00:00", 10000, 1, "Deposit"],
        ["Stock purchase", "AAPL", "Apple",
         "2025-01-06 10:05:00", -1925.30, 2, "OPEN BUY 10/10 @ 192.53"],
        ["Stock purchase", "MSFT", "Microsoft",
         "2025-01-06 10:10:00", -2028.40, 3, "OPEN BUY 5/5 @ 405.68"],
    ])

    result = import_xtb(str(xlsx), "USD")
    assert result["success"] is True

    # Inject fake price data instead of hitting Yahoo
    _inject_prices(tmp, [
        ("AAPL", 2025, {
            "2025-01-06": 192.53, "2025-06-30": 210.00,
            "2025-12-31": 220.00,
        }),
        ("MSFT", 2025, {
            "2025-01-06": 405.68, "2025-06-30": 420.00,
            "2025-12-31": 440.00,
        }),
        ("USDPLN", 2025, {
            "2025-01-06": 4.05, "2025-06-30": 3.95,
            "2025-12-31": 3.90,
        }),
    ])

    rebuild_balance()
    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 10.0
    assert bal["MSFT"]["amount"] == 5.0

    # Build portfolio with fake prices
    from portfolio_core import build_portfolio

    def fake_get_ticker_currency(ticker):
        return "USD"

    def fake_get_fx(from_ccy, to_ccy, *args, **kwargs):
        if from_ccy == to_ccy:
            return 1.0
        rates = {"USDPLN": 3.90}
        key = f"{from_ccy}{to_ccy}"
        return rates.get(key, 1.0)

    with patch("portfolio_core.get_ticker_currency", side_effect=fake_get_ticker_currency), \
         patch("portfolio_core.get_fx_rate", side_effect=fake_get_fx):
        snapshots = build_portfolio(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            base_currency="USD",
            precision="D",
            use_cache=False,
        )

    assert len(snapshots) > 0

    last = snapshots[-1]
    assert last["total_value"] > 0
    assert last["base_currency"] == "USD"

    asset_tickers = {a["ticker"] for a in last["assets"]}
    assert "AAPL" in asset_tickers
    assert "MSFT" in asset_tickers

    aapl_val = next(a for a in last["assets"] if a["ticker"] == "AAPL")["value_base"]
    msft_val = next(a for a in last["assets"] if a["ticker"] == "MSFT")["value_base"]
    # 10 * 220 = 2200, 5 * 440 = 2200
    assert aapl_val == pytest.approx(2200.0, rel=0.01)
    assert msft_val == pytest.approx(2200.0, rel=0.01)


def test_refresh_splits_detected_with_mock(tmp: Path):
    """Stock splits are auto-fixed during import (mocked split data)."""
    import storage
    from ledger_core import get_all_transactions
    from xtb_import import import_xtb

    imports_dir = storage.imports_dir() / "xtb"
    imports_dir.mkdir(parents=True, exist_ok=True)

    xlsx = imports_dir / "split_test.xlsx"
    _make_xtb_xlsx(xlsx, [
        ["Stock purchase", "AAPL", "Apple",
         "2020-01-15 10:05:00", -96.88, 1, "OPEN BUY 1/1 @ 96.88"],
    ])

    mock_splits = {
        "AAPL": {
            "2020-08-31": 4.0,
            "2024-06-10": 10.0,
        },
    }

    def fake_get_splits(ticker):
        return mock_splits.get(ticker.upper(), {})

    with patch("ticker_data.get_splits", side_effect=fake_get_splits):
        result = import_xtb(str(xlsx), "USD")
        assert result["success"] is True

    txns = get_all_transactions()
    ticker_amounts = []
    for rec in txns:
        for e in rec["entries"]:
            if e["ticker"] == "AAPL":
                ticker_amounts.append(float(e["amount"]))

    # Original 1 share × 4 × 10 = 40 shares
    total = sum(ticker_amounts)
    assert total == 40.0, f"Expected 40 shares after splits, got {total}"


def test_refresh_split_dedup(tmp: Path):
    """Re-importing after a split fix does not add duplicate fix entries."""
    import storage
    from ledger_core import get_all_transactions
    from xtb_import import import_xtb

    imports_dir = storage.imports_dir() / "xtb"
    imports_dir.mkdir(parents=True, exist_ok=True)

    xlsx = imports_dir / "split_dedup.xlsx"
    _make_xtb_xlsx(xlsx, [
        ["Stock purchase", "DNP.WA", "DNP",
         "2025-03-16 10:00:00", -134.23, 1, "OPEN BUY 1.2712/1.2712 @ 105.59"],
    ])

    mock_splits = {"DNP.WA": {"2025-07-31": 10.0}}

    def fake_get_splits(ticker):
        return mock_splits.get(ticker.upper(), {})

    with patch("ticker_data.get_splits", side_effect=fake_get_splits):
        r1 = import_xtb(str(xlsx), "PLN")
        assert r1["success"] is True

    txns = get_all_transactions()
    dnp_fix_entries = [
        e for rec in txns
        if rec["date"] == "2025-07-31"
        for e in rec["entries"]
        if e["ticker"] == "DNP.WA"
    ]
    assert len(dnp_fix_entries) == 1, f"Expected exactly 1 fix entry, got {len(dnp_fix_entries)}"

    dnp_total = sum(
        float(e["amount"])
        for rec in txns
        for e in rec["entries"]
        if e["ticker"] == "DNP.WA"
    )
    # 1.2712 (buy) + 11.4408 (fix) = 12.712
    assert dnp_total == pytest.approx(12.712, abs=1e-4)

    # Second import — no duplicate fix
    with patch("ticker_data.get_splits", side_effect=fake_get_splits):
        r2 = import_xtb(str(xlsx), "PLN")
        assert r2["success"] is True

    txns2 = get_all_transactions()
    dnp_fix_entries2 = [
        e for rec in txns2
        if rec["date"] == "2025-07-31"
        for e in rec["entries"]
        if e["ticker"] == "DNP.WA"
    ]
    assert len(dnp_fix_entries2) == 1, (
        f"Re-import created duplicate fix: {len(dnp_fix_entries2)} entries"
    )


# ---------------------------------------------------------------------------
# Network tests (require real Yahoo Finance access)
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_real_download_ensure_batch(tmp: Path):
    """ensure_batch downloads real prices from Yahoo Finance for well-known tickers."""
    import storage
    from xtb_import import import_xtb
    from ticker_data import ensure_batch
    from ledger_core import get_all_tickers

    imports_dir = storage.imports_dir() / "xtb"
    imports_dir.mkdir(parents=True, exist_ok=True)

    xlsx = imports_dir / "real_dl.xlsx"
    _make_xtb_xlsx(xlsx, [
        ["Deposit", "USD", "", "2025-01-06 10:00:00", 10000, 1, "Deposit"],
        ["Stock purchase", "AAPL", "Apple",
         "2025-01-06 10:05:00", -1925.30, 2, "OPEN BUY 10/10 @ 192.53"],
    ])

    import_xtb(str(xlsx), "USD")

    tickers = get_all_tickers(include_fx=True)
    stock_tickers = [t for t in tickers if t not in storage.SUPPORTED_CURRENCIES]

    failed = ensure_batch(
        stock_tickers,
        start_date=date(2025, 1, 1),
        end_date=date.today(),
        force_refresh_current_year=True,
    )

    if failed:
        pytest.skip(f"Yahoo Finance unavailable: {failed}")

    assert _count_price_files(tmp, "AAPL") >= 1


@pytest.mark.slow
def test_real_full_refresh_end_to_end(tmp: Path):
    """Full end-to-end: import → download → balance → portfolio (real Yahoo)."""
    import storage
    from xtb_import import import_xtb
    from ticker_data import ensure_batch
    from ledger_core import get_all_tickers, rebuild_balance
    from portfolio_core import build_portfolio

    imports_dir = storage.imports_dir() / "xtb"
    imports_dir.mkdir(parents=True, exist_ok=True)

    xlsx = imports_dir / "e2e.xlsx"
    _make_xtb_xlsx(xlsx, [
        ["Deposit", "USD", "", "2025-01-06 10:00:00", 10000, 1, "Deposit"],
        ["Stock purchase", "AAPL", "Apple",
         "2025-01-06 10:05:00", -1925.30, 2, "OPEN BUY 10/10 @ 192.53"],
    ])

    import_xtb(str(xlsx), "USD")

    tickers = get_all_tickers(include_fx=True)
    stock_tickers = [t for t in tickers if t not in storage.SUPPORTED_CURRENCIES]

    failed = ensure_batch(
        stock_tickers,
        start_date=date(2025, 1, 1),
        end_date=date.today(),
        force_refresh_current_year=True,
    )
    if failed:
        pytest.skip(f"Yahoo Finance unavailable: {failed}")

    rebuild_balance()
    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 10.0

    snapshots = build_portfolio(
        start_date=date(2025, 1, 1),
        end_date=date.today(),
        base_currency="USD",
        precision="D",
        use_cache=False,
    )
    assert len(snapshots) > 0
    last = snapshots[-1]
    assert last["total_value"] > 0
