#!/usr/bin/env python3
"""
test_runner.py —  Negotium - Investment Tracker test suite

Usage:
    cd investment_tracker
    python3 tests/test_runner.py

Tests are fully isolated: each test gets its own temp directory.
All temp dirs are deleted at the end (even on failure).
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import traceback
from datetime import date
from pathlib import Path

# Add src/ and project root to path so we can import the modules
SRC = Path(__file__).parent.parent / "src"
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import fixtures as fx

# ── Test harness ───────────────────────────────────────────────────────────────

_ALL_TEMPS: list[Path] = []
_RESULTS: list[tuple[str, bool, str]] = []


def setup_env(tmp: Path) -> None:
    """Reload modules and patch paths to use tmp directory."""
    # We need to reload modules so their module-level globals are re-set
    import importlib
    import storage, config, transactions, portfolio, ticker_data

    for mod in [storage, config, transactions, portfolio, ticker_data]:
        importlib.reload(mod)

    fx.patch_root(tmp)


def run_test(name: str, fn):
    """Run a single test function in an isolated temp environment."""
    tmp = fx.make_temp_root()
    _ALL_TEMPS.append(tmp)
    try:
        setup_env(tmp)
        fn(tmp)
        _RESULTS.append((name, True, ""))
        print(f"  ✓  {name}")
    except Exception:
        tb = traceback.format_exc()
        _RESULTS.append((name, False, tb))
        print(f"  ✗  {name}")
        print(f"     {tb.strip().splitlines()[-1]}")


def cleanup():
    """Remove all temp directories created during this run."""
    removed = 0
    for tmp in _ALL_TEMPS:
        if tmp.exists():
            shutil.rmtree(tmp)
            removed += 1
    print(f"\n🧹 Cleaned up {removed} temp director{'y' if removed==1 else 'ies'}.")


# ── Individual tests ───────────────────────────────────────────────────────────

def test_config_defaults(tmp: Path):
    """Config creates default file when missing, loads it correctly."""
    import config
    cfg = config.load()
    assert cfg["name"] == "My Portfolio"
    assert cfg["start_day"] == "2020-01-01"
    assert cfg["default_currency"] == "PLN"
    assert (tmp / "data" / "config.json").exists(), "config.json should be created"


def test_config_save_and_reload(tmp: Path):
    """Config save → reload round-trip preserves all fields."""
    import config
    custom = {
        "name": "My Stocks",
        "start_day": "2022-06-15",
        "default_currency": "USD",
        "graph_precision": "1W",
    }
    config.save(custom)
    loaded = config.load()
    assert loaded["name"] == "My Stocks"
    assert loaded["start_day"] == "2022-06-15"
    assert loaded["default_currency"] == "USD"
    assert loaded["graph_precision"] == "1W"


def test_storage_jsonl_roundtrip(tmp: Path):
    """JSONL write → read preserves all records."""
    import storage
    path = tmp / "test.jsonl"
    records = [
        {"date": "2023-01-01", "entries": [{"ticker": "AAPL", "amount": 10}]},
        {"date": "2023-01-02", "entries": [{"ticker": "MSFT", "amount": 5}]},
    ]
    storage.write_jsonl(path, records)
    loaded = storage.read_jsonl(path)
    assert len(loaded) == 2
    assert loaded[0]["date"] == "2023-01-01"
    assert loaded[1]["entries"][0]["ticker"] == "MSFT"


def test_storage_append_jsonl(tmp: Path):
    """Appending to JSONL adds new records without touching existing ones."""
    import storage
    path = tmp / "append.jsonl"
    storage.write_jsonl(path, [{"date": "2023-01-01", "x": 1}])
    storage.append_jsonl(path, {"date": "2023-01-02", "x": 2})
    records = storage.read_jsonl(path)
    assert len(records) == 2
    assert records[1]["x"] == 2


def test_storage_balance(tmp: Path):
    """Balance save → load preserves values, strips near-zero entries."""
    import storage
    balance = {"AAPL": {"amount": 10.0, "avg_price": 125.0}, "PLN": {"amount": 5000.0, "avg_price": 0.0}, "MSFT": {"amount": 1e-12, "avg_price": 0.0}}
    storage.save_balance(balance)
    loaded = storage.load_balance()
    assert loaded["AAPL"]["amount"] == 10.0
    assert loaded["PLN"]["amount"] == 5000.0
    assert "MSFT" not in loaded, "Near-zero holding should be stripped"


def test_price_cache_write_read(tmp: Path):
    """Price cache write → read returns same data for a given ticker/year."""
    import storage
    prices = {"2023-01-03": 125.07, "2023-01-04": 126.36}
    storage.save_price_year("AAPL", 2023, prices)
    loaded = storage.load_price_year("AAPL", 2023)
    assert loaded["2023-01-03"] == 125.07
    assert storage.has_price_year("AAPL", 2023)
    assert not storage.has_price_year("AAPL", 2022)


def test_add_transaction_simple(tmp: Path):
    """Adding a transaction creates the ledger and updates balance."""
    import transactions, storage
    fx.inject_fake_prices(tmp)

    transactions.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    recs = transactions.get_all_transactions()
    assert len(recs) == 1
    assert recs[0]["date"] == "2023-01-03"

    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 10.0
    assert abs(bal["USD"]["amount"] - (-1250.70)) < 0.01


def test_add_transaction_same_date_merges(tmp: Path):
    """Two transactions on the same date are merged into one line."""
    import transactions

    transactions.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 5.0}])
    transactions.add_transaction("2023-01-03", [{"ticker": "MSFT", "amount": 3.0}])

    recs = transactions.get_all_transactions()
    assert len(recs) == 1, "Same-date transactions should merge into one record"
    tickers_in_rec = {e["ticker"] for e in recs[0]["entries"]}
    assert "AAPL" in tickers_in_rec
    assert "MSFT" in tickers_in_rec


def test_add_transaction_chronological_append(tmp: Path):
    """Transactions on later dates are appended in order."""
    import transactions

    transactions.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 5.0}])
    transactions.add_transaction("2023-01-09", [{"ticker": "MSFT", "amount": 2.0}])
    transactions.add_transaction("2023-06-01", [{"ticker": "PLN", "amount": 1000.0}])

    recs = transactions.get_all_transactions()
    assert len(recs) == 3
    assert recs[0]["date"] == "2023-01-03"
    assert recs[1]["date"] == "2023-01-09"
    assert recs[2]["date"] == "2023-06-01"


def test_add_transaction_past_date_inserts_correctly(tmp: Path):
    """Inserting a past-date transaction reorders the file correctly."""
    import transactions

    transactions.add_transaction("2023-01-09", [{"ticker": "AAPL", "amount": 10.0}])
    transactions.add_transaction("2023-06-01", [{"ticker": "PLN", "amount": 500.0}])

    # Now insert something between them
    transactions.add_transaction("2023-01-04", [{"ticker": "USD", "amount": 1000.0}])

    recs = transactions.get_all_transactions()
    dates = [r["date"] for r in recs]
    assert dates == sorted(dates), f"Ledger must stay chronological, got: {dates}"
    assert dates[0] == "2023-01-04"


def test_compute_holdings_at(tmp: Path):
    """compute_holdings_at returns correct balances at a given date."""
    import transactions

    transactions.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 10.0}])
    transactions.add_transaction("2023-06-01", [{"ticker": "AAPL", "amount": -5.0}])

    holdings_jan = transactions.compute_holdings_at("2023-01-31")
    assert holdings_jan["AAPL"] == 10.0

    holdings_jun = transactions.compute_holdings_at("2023-12-31")
    assert holdings_jun["AAPL"] == 5.0


def test_balance_after_full_sell(tmp: Path):
    """Selling all shares of a ticker removes it from holdings."""
    import transactions, storage

    transactions.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 10.0}])
    transactions.add_transaction("2023-01-09", [{"ticker": "AAPL", "amount": -10.0}])

    bal = storage.load_balance()
    assert "AAPL" not in bal or abs(bal.get("AAPL", {}).get("amount", 0)) < 1e-6, \
        "After full sell, AAPL should be gone from balance"


def test_get_price_fallback_weekend(tmp: Path):
    """get_price falls back to Friday's close on weekend dates."""
    import ticker_data

    cache: dict = {}
    # Inject prices only for 2023-01-06 (Friday); 2023-01-07 (Sat) should fall back
    cache["AAPL"] = {2023: {"2023-01-06": 129.62}}

    price = ticker_data.get_price("AAPL", "2023-01-07", cache, 2023)
    assert price == 129.62, f"Expected 129.62, got {price}"


def test_get_price_cash_returns_one(tmp: Path):
    """Cash tickers always return 1.0 regardless of date."""
    import ticker_data

    cache: dict = {}
    for ccy in ["USD", "EUR", "PLN"]:
        price = ticker_data.get_price(ccy, "2023-01-03", cache, 2023)
        assert price == 1.0, f"Cash ticker {ccy} should return 1.0"


def test_get_fx_rate_same_currency(tmp: Path):
    """FX rate of same-to-same currency is exactly 1.0."""
    import ticker_data

    cache: dict = {}
    for ccy in ["USD", "EUR", "PLN"]:
        rate = ticker_data.get_fx_rate(ccy, ccy, "2023-01-03", cache, 2023)
        assert rate == 1.0, f"FX rate {ccy}→{ccy} should be 1.0"


def test_get_fx_rate_usd_to_pln(tmp: Path):
    """USD→PLN FX rate is read from USDPLN cache."""
    import ticker_data

    fx.inject_fake_prices(tmp)
    cache: dict = {}
    rate = ticker_data.get_fx_rate("USD", "PLN", "2023-01-03", cache, 2023)
    assert abs(rate - 4.38) < 0.01, f"Expected ~4.38, got {rate}"


def test_invalidate_portfolio(tmp: Path):
    """invalidate_portfolio_from removes snapshots on/after the given date."""
    import storage

    snapshots = [
        {"date": "2023-01-01", "total_value": 100},
        {"date": "2023-01-02", "total_value": 110},
        {"date": "2023-01-03", "total_value": 120},
        {"date": "2023-01-04", "total_value": 130},
    ]
    storage.save_portfolio(snapshots)
    storage.invalidate_portfolio_from("2023-01-03")
    kept = storage.load_portfolio()
    assert len(kept) == 2
    assert kept[-1]["date"] == "2023-01-02"


def test_portfolio_build_single_asset(tmp: Path):
    """Portfolio build produces correct values for a single USD stock in PLN base."""
    import transactions, portfolio

    fx.inject_fake_prices(tmp)

    # Buy 10 AAPL at 2023-01-03
    transactions.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    snapshots = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 3),
        base_currency="PLN",
        precision="D",
        use_cache=False,
    )

    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap["date"] == "2023-01-03"

    # Expected: 10 AAPL × 125.07 × 4.38 ≈ 5478.07 PLN
    # Plus USD cash: -1250.70 × 4.38 ≈ -5477.79 PLN → near zero net cash
    aapl_asset = next((a for a in snap["assets"] if a["ticker"] == "AAPL"), None)
    assert aapl_asset is not None, "AAPL should appear in holdings"
    expected_aapl_value = 10.0 * 125.07 * 4.38
    assert abs(aapl_asset["value_base"] - expected_aapl_value) < 1.0, \
        f"AAPL value_base: expected ~{expected_aapl_value:.2f}, got {aapl_asset['value_base']}"


def test_portfolio_build_cash_only(tmp: Path):
    """Portfolio with only PLN cash shows correct value without any FX conversion."""
    import transactions, portfolio

    fx.inject_fake_prices(tmp)

    transactions.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0},
    ])

    snapshots = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 3),
        base_currency="PLN",
        precision="D",
        use_cache=False,
    )

    snap = snapshots[0]
    assert abs(snap["total_value"] - 10000.0) < 0.01, \
        f"10000 PLN cash should be 10000 PLN total_value, got {snap['total_value']}"


def test_portfolio_invested_tracking(tmp: Path):
    """invested correctly counts only positive cash inflows."""
    import transactions, portfolio

    fx.inject_fake_prices(tmp)

    # Deposit 10000 PLN, then buy AAPL (cash outflow should not count as invested)
    transactions.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0},  # inflow → invested
    ])
    transactions.add_transaction("2023-01-04", [
        {"ticker": "AAPL", "amount": 5.0},
        {"ticker": "PLN", "amount": -631.8},   # outflow → not a invested
    ])

    snapshots = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 4),
        base_currency="PLN",
        precision="D",
        use_cache=False,
    )

    # invested at Jan 4 should still be ~10000 (only the PLN deposit counts)
    snap_jan4 = next(s for s in snapshots if s["date"] == "2023-01-04")
    assert abs(snap_jan4["invested"] - 10000.0) < 1.0, \
        f"invested should be ~10000, got {snap_jan4['invested']}"


def test_portfolio_weekly_precision(tmp: Path):
    """Weekly precision yields only Friday dates."""
    import transactions, portfolio
    from datetime import timedelta

    fx.inject_fake_prices(tmp)

    transactions.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 5.0},
    ])

    snapshots = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 27),
        base_currency="PLN",
        precision="W-FRI",
        use_cache=False,
    )

    for snap in snapshots:
        d = date.fromisoformat(snap["date"])
        assert d.weekday() == 4, f"Weekly snapshot on {snap['date']} is not a Friday"


def test_portfolio_cache_resumes(tmp: Path):
    """Portfolio build resumes from cached snapshots without recomputing them."""
    import transactions, portfolio, storage

    fx.inject_fake_prices(tmp)

    transactions.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
    ])

    # Build up to Jan 5
    portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 5),
        base_currency="PLN",
        precision="D",
        use_cache=True,
    )

    # Patch storage to track if portfolio.jsonl is re-read
    calls = []
    orig_load = storage.load_portfolio

    def mock_load():
        calls.append(1)
        return orig_load()

    storage.load_portfolio = mock_load

    # Build Jan 5 to Jan 6 (should resume from cache)
    portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 6),
        base_currency="PLN",
        precision="D",
        use_cache=True,
    )

    saved = storage.load_portfolio()
    dates = [s["date"] for s in saved]
    assert "2023-01-06" in dates, "Jan 6 should be added after resuming"

    storage.load_portfolio = orig_load  # restore


def test_day_range_daily(tmp: Path):
    """_day_range yields every day between start and end inclusive."""
    from portfolio import _day_range
    days = list(_day_range(date(2023, 1, 3), date(2023, 1, 6), "D"))
    assert len(days) == 4
    assert days[0] == date(2023, 1, 3)
    assert days[-1] == date(2023, 1, 6)


def test_day_range_weekly(tmp: Path):
    """_day_range with weekly precision yields only Fridays."""
    from portfolio import _day_range
    days = list(_day_range(date(2023, 1, 3), date(2023, 1, 31), "W-FRI"))
    for d in days:
        assert d.weekday() == 4, f"{d} is not a Friday"
    assert len(days) == 4  # Jan 6, 13, 20, 27


def test_get_tickers(tmp: Path):
    """get_tickers returns all non-cash tickers from the ledger."""
    import transactions

    transactions.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.0},  # cash — should be excluded
    ])
    transactions.add_transaction("2023-01-09", [
        {"ticker": "CDR.WA", "amount": 5.0},
        {"ticker": "PLN", "amount": -650.0},   # cash — excluded
    ])

    tickers = transactions.get_tickers(include_cash=False)
    assert "AAPL" in tickers
    assert "CDR.WA" in tickers
    assert "USD" not in tickers
    assert "PLN" not in tickers


def test_config_precision_mapping(tmp: Path):
    """get_precision maps config values to pandas resample rules."""
    import config
    assert config.get_precision({"graph_precision": "1D"}) == "D"
    assert config.get_precision({"graph_precision": "1W"}) == "W-FRI"
    # Default fallback
    assert config.get_precision({}) == "D"


def test_storage_loads_prices_range(tmp: Path):
    """load_prices_range merges multiple year files correctly."""
    import storage

    storage.save_price_year("AAPL", 2022, {"2022-12-30": 129.93})
    storage.save_price_year("AAPL", 2023, {"2023-01-03": 125.07})

    prices = storage.load_prices_range("AAPL", date(2022, 12, 1), date(2023, 1, 31))
    assert "2022-12-30" in prices
    assert "2023-01-03" in prices


def test_snapshots_to_series(tmp: Path):
    """snapshots_to_series extracts correct parallel arrays."""
    from portfolio import snapshots_to_series

    snaps = [
        {"date": "2023-01-03", "total_value": 1000.0, "invested": 900.0},
        {"date": "2023-01-04", "total_value": 1050.0, "invested": 900.0},
    ]
    dates, values, contrs = snapshots_to_series(snaps)
    assert dates  == ["2023-01-03", "2023-01-04"]
    assert values == [1000.0, 1050.0]
    assert contrs == [900.0, 900.0]



# ── Buy / sell round-trip tests ───────────────────────────────────────────────

def test_buy_eur_etf_full_sell(tmp: Path):
    """Buy QDVE.DE (EUR ETF), sell all shares, receive EUR back."""
    import transactions, storage

    fx.inject_fake_prices(tmp)
    storage.save_price_year("QDVE.DE", 2023, {
        "2023-01-03": 200.0,
        "2023-06-01": 240.0,
    })

    # Buy: 5 shares at 200 EUR each
    transactions.add_transaction("2023-01-03", [
        {"ticker": "QDVE.DE", "amount": 5.0},
        {"ticker": "EUR",     "amount": -1000.0},
    ])
    # Sell: all 5 shares at 240 EUR each = 1200 EUR proceeds
    transactions.add_transaction("2023-06-01", [
        {"ticker": "QDVE.DE", "amount": -5.0},
        {"ticker": "EUR",     "amount": 1200.0},
    ])

    bal = storage.load_balance()
    assert "QDVE.DE" not in bal or abs(bal.get("QDVE.DE", {}).get("amount", 0)) < 1e-9, \
        "QDVE.DE should be fully sold"
    assert abs(bal.get("EUR", {}).get("amount", 0) - 200.0) < 0.01, \
        f"Expected 200 EUR profit remaining, got {bal.get('EUR', {}).get('amount', 0)}"


def test_buy_usd_stock_partial_sell(tmp: Path):
    """Buy GOOG in USD, partially sell, verify correct remaining balance."""
    import transactions, storage

    fx.inject_fake_prices(tmp)
    storage.save_price_year("GOOG", 2023, {
        "2023-01-03": 88.0,
        "2023-06-01": 122.0,
    })

    transactions.add_transaction("2023-01-03", [
        {"ticker": "GOOG", "amount": 10.0},
        {"ticker": "USD",  "amount": -880.0},
    ])
    # Sell 4 of 10 shares
    transactions.add_transaction("2023-06-01", [
        {"ticker": "GOOG", "amount": -4.0},
        {"ticker": "USD",  "amount": 488.0},   # 4 × 122
    ])

    bal = storage.load_balance()
    assert abs(bal.get("GOOG", {}).get("amount", 0) - 6.0) < 1e-9, \
        f"Expected 6 GOOG remaining, got {bal.get('GOOG', {}).get('amount', 0)}"
    assert abs(bal.get("USD", {}).get("amount", 0) - (-392.0)) < 0.01, \
        f"Expected -392 USD (net cash spent), got {bal.get('USD', {}).get('amount', 0)}"


def test_sell_proceeds_not_counted_as_invested(tmp: Path):
    """Sale proceeds (EUR from selling ETF) must NOT increase invested."""
    import transactions, portfolio

    fx.inject_fake_prices(tmp)
    storage_mod = __import__("storage")
    storage_mod.save_price_year("QDVE.DE", 2023, {
        "2023-01-03": 200.0,
        "2023-06-01": 240.0,
    })

    # Deposit real money: 1000 EUR
    transactions.add_transaction("2023-01-03", [
        {"ticker": "EUR", "amount": 1000.0},
    ])
    # Buy QDVE.DE with it
    transactions.add_transaction("2023-01-04", [
        {"ticker": "QDVE.DE", "amount": 5.0},
        {"ticker": "EUR",     "amount": -1000.0},
    ])
    # Sell for profit: 1200 EUR back
    transactions.add_transaction("2023-06-01", [
        {"ticker": "QDVE.DE", "amount": -5.0},
        {"ticker": "EUR",     "amount": 1200.0},
    ])

    snaps = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 6, 1),
        base_currency="EUR",
        precision="D",
        use_cache=False,
    )

    last = snaps[-1]
    # invested should be ~1000 EUR (the initial deposit), NOT 2200 EUR
    assert abs(last["invested"] - 1000.0) < 1.0, \
        f"invested should be ~1000 EUR (deposit only), got {last['invested']}"
    # Total value should be ~1200 EUR (the sale proceeds sitting as cash)
    assert abs(last["total_value"] - 1200.0) < 1.0, \
        f"Total value should be ~1200 EUR (all as cash), got {last['total_value']}"


def test_currency_exchange_counts_as_invested(tmp: Path):
    """Wiring USD into the portfolio (pure cash) counts as invested."""
    import transactions, portfolio

    fx.inject_fake_prices(tmp)

    # Wire in 1000 USD — pure cash deposit
    transactions.add_transaction("2023-01-03", [
        {"ticker": "USD", "amount": 1000.0},
    ])

    snaps = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 3),
        base_currency="PLN",
        precision="D",
        use_cache=False,
    )

    snap = snaps[0]
    # 1000 USD × 4.38 USDPLN = 4380 PLN invested
    assert abs(snap["invested"] - 4380.0) < 1.0, \
        f"1000 USD deposit should add ~4380 PLN invested, got {snap['invested']}"


def test_eur_stock_valued_correctly_in_pln(tmp: Path):
    """QDVE.DE (EUR) position is correctly converted to PLN via EURPLN."""
    import transactions, portfolio

    fx.inject_fake_prices(tmp)
    storage_mod = __import__("storage")
    storage_mod.save_price_year("QDVE.DE", 2023, {
        "2023-01-03": 200.0,
    })

    transactions.add_transaction("2023-01-03", [
        {"ticker": "QDVE.DE", "amount": 5.0},
        {"ticker": "EUR",     "amount": -1000.0},
    ])

    snaps = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 3),
        base_currency="PLN",
        precision="D",
        use_cache=False,
    )

    snap  = snaps[0]
    asset = next((a for a in snap["assets"] if a["ticker"] == "QDVE.DE"), None)
    assert asset is not None, "QDVE.DE should appear in holdings"
    assert asset["currency"] == "EUR", \
        f"QDVE.DE should be EUR-denominated, got {asset['currency']}"

    # 5 shares × 200 EUR × 4.68 EURPLN = 4680 PLN
    expected = 5.0 * 200.0 * 4.68
    assert abs(asset["value_base"] - expected) < 1.0, \
        f"QDVE.DE value in PLN: expected ~{expected:.2f}, got {asset['value_base']}"


def test_usd_stock_valued_correctly_in_pln(tmp: Path):
    """GOOG (USD) position is correctly converted to PLN via USDPLN."""
    import transactions, portfolio

    fx.inject_fake_prices(tmp)
    storage_mod = __import__("storage")
    storage_mod.save_price_year("GOOG", 2023, {
        "2023-01-03": 88.0,
    })

    transactions.add_transaction("2023-01-03", [
        {"ticker": "GOOG", "amount": 10.0},
        {"ticker": "USD",  "amount": -880.0},
    ])

    snaps = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 3),
        base_currency="PLN",
        precision="D",
        use_cache=False,
    )

    asset = next((a for a in snaps[0]["assets"] if a["ticker"] == "GOOG"), None)
    assert asset is not None, "GOOG should appear in holdings"
    assert asset["currency"] == "USD", \
        f"GOOG should be USD-denominated, got {asset['currency']}"

    # 10 shares × 88 USD × 4.38 USDPLN = 3854.4 PLN
    expected = 10.0 * 88.0 * 4.38
    assert abs(asset["value_base"] - expected) < 1.0, \
        f"GOOG value in PLN: expected ~{expected:.2f}, got {asset['value_base']}"


def test_mixed_portfolio_pln_eur_usd(tmp: Path):
    """Portfolio with PLN, EUR and USD positions all valued correctly."""
    import transactions, portfolio

    fx.inject_fake_prices(tmp)
    storage_mod = __import__("storage")
    storage_mod.save_price_year("QDVE.DE", 2023, {"2023-01-09": 210.0})
    storage_mod.save_price_year("GOOG",    2023, {"2023-01-09": 91.0})

    # Deposit PLN cash
    transactions.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 5000.0},
    ])
    # Buy EUR ETF
    transactions.add_transaction("2023-01-04", [
        {"ticker": "QDVE.DE", "amount": 3.0},
        {"ticker": "EUR",     "amount": -630.0},
    ])
    # Buy USD stock
    transactions.add_transaction("2023-01-06", [
        {"ticker": "GOOG", "amount": 2.0},
        {"ticker": "USD",  "amount": -182.0},
    ])

    snaps = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 9),
        base_currency="PLN",
        precision="D",
        use_cache=False,
    )

    last   = snaps[-1]
    tickers = {a["ticker"] for a in last["assets"]}

    assert "PLN"     in tickers, "PLN cash should appear"
    assert "EUR"     in tickers, "EUR cash should appear"
    assert "USD"     in tickers, "USD cash should appear"
    assert "QDVE.DE" in tickers, "QDVE.DE should appear"
    assert "GOOG"    in tickers, "GOOG should appear"

    qdve = next(a for a in last["assets"] if a["ticker"] == "QDVE.DE")
    goog = next(a for a in last["assets"] if a["ticker"] == "GOOG")
    assert qdve["currency"] == "EUR"
    assert goog["currency"] == "USD"

    # invested = only the PLN deposit (5000 PLN)
    # EUR buy and USD buy are stock transactions, not counted
    assert abs(last["invested"] - 5000.0) < 1.0, \
        f"Only PLN deposit should count as invested: {last['invested']}"


def test_delete_transaction(tmp: Path):
    """Deleting one entry removes it and rebuilds balance."""
    import transactions, storage

    transactions.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    transactions.delete_transaction("2023-01-03", 0)

    recs = transactions.get_all_transactions()
    assert len(recs) == 1
    assert len(recs[0]["entries"]) == 1
    assert recs[0]["entries"][0]["ticker"] == "USD"

    bal = storage.load_balance()
    assert "AAPL" not in bal or abs(bal.get("AAPL", {}).get("amount", 0)) < 1e-6


def test_delete_last_entry_removes_record(tmp: Path):
    """Deleting the only entry in a date removes the entire record."""
    import transactions

    transactions.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 10.0}])
    transactions.add_transaction("2023-06-01", [{"ticker": "MSFT", "amount": 5.0}])

    transactions.delete_transaction("2023-01-03", 0)

    recs = transactions.get_all_transactions()
    assert len(recs) == 1
    assert recs[0]["date"] == "2023-06-01"


def test_update_transaction(tmp: Path):
    """Updating an entry changes ticker, amount, and account_operation."""
    import transactions, storage

    transactions.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    transactions.update_transaction("2023-01-03", 0, "MSFT", 20.0, account_operation=True)

    recs = transactions.get_all_transactions()
    e = recs[0]["entries"][0]
    assert e["ticker"] == "MSFT"
    assert e["amount"] == 20.0
    assert e.get("account_operation") is True

    bal = storage.load_balance()
    assert bal["MSFT"]["amount"] == 20.0
    assert "AAPL" not in bal or abs(bal.get("AAPL", {}).get("amount", 0)) < 1e-6


def test_xtb_parse_shares(tmp: Path):
    """_parse_shares extracts share count from XTB comment patterns."""
    from xtb_import import _parse_shares

    assert _parse_shares("OPEN BUY 4/4.138 @ 48.3060") == 4.0
    assert _parse_shares("OPEN BUY 0.1367 @ 1462.60") == 0.1367
    assert _parse_shares("CLOSE BUY 3.9657/14.7171 @ 123.3700") == 3.9657
    assert _parse_shares("OPEN BUY 1 @ 107.00") == 1.0
    assert _parse_shares(None) is None
    assert _parse_shares("") is None
    assert _parse_shares("no match here") is None


def test_xtb_parse_transfer_rate(tmp: Path):
    """_parse_transfer_rate extracts exchange rate from transfer comment."""
    from xtb_import import _parse_transfer_rate

    comment = "Currency conversion, EUR to USD from TA: 52016471 to: 51963109, Exchange rate:1.159044"
    assert _parse_transfer_rate(comment) == 1.159044

    assert _parse_transfer_rate(None) is None
    assert _parse_transfer_rate("no rate here") is None


def test_xtb_parse_transfer_target(tmp: Path):
    """_parse_transfer_target extracts target currency from transfer comment."""
    from xtb_import import _parse_transfer_target

    comment = "Currency conversion, EUR to USD from TA: 52016471 to: 51963109, Exchange rate:1.159044"
    assert _parse_transfer_target(comment) == "USD"

    comment2 = "Currency conversion, PLN to EUR from TA: 53394664 to: 52016471, Exchange rate:0.23"
    assert _parse_transfer_target(comment2) == "EUR"

    assert _parse_transfer_target(None) is None
    assert _parse_transfer_target("no currency here") is None


def test_xtb_transfer_creates_source_entry(tmp: Path):
    """Transfer import creates the source currency entry (each file has its own side)."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")

    ws.append(["", "", "", "", "", "", ""])
    ws.append(["", "", "", "", "", "", ""])
    ws.append(["", "", "", "", "", "", ""])
    ws.append(["", "", "", "", "", "", ""])
    ws.append(["", "", "", "", "", "", ""])
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append([
        "Transfer", "", "",
        "2026-06-01 10:47:30", -956, 1288183841,
        "Currency conversion, EUR to USD from TA: 52016471 to: 51963109, Exchange rate:1.159044",
    ])

    del wb["Sheet"]
    xlsx_path = tmp / "test_transfer.xlsx"
    wb.save(str(xlsx_path))
    wb.close()

    txns = parse_xtb_excel(str(xlsx_path), "EUR")
    assert len(txns) == 1

    entries = txns[0]["entries"]
    assert len(entries) == 1

    eur_entry = entries[0]
    assert eur_entry["ticker"] == "EUR"
    assert eur_entry["amount"] == -956
    assert eur_entry.get("account_operation") is True


def test_xtb_deposit_creates_account_operation(tmp: Path):
    """Deposit import creates entry with account_operation=True."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")

    for _ in range(5):
        ws.append(["", "", "", "", "", "", ""])
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append(["Deposit", "", "", "2026-01-15 12:00:00", 5000, 111, "eWallet deposit"])

    del wb["Sheet"]
    xlsx_path = tmp / "test_deposit.xlsx"
    wb.save(str(xlsx_path))
    wb.close()

    txns = parse_xtb_excel(str(xlsx_path), "EUR")
    assert len(txns) == 1

    entries = txns[0]["entries"]
    assert len(entries) == 1
    assert entries[0]["ticker"] == "EUR"
    assert entries[0]["amount"] == 5000
    assert entries[0].get("account_operation") is True


def test_xtb_stock_purchase_creates_two_entries(tmp: Path):
    """Stock purchase creates share entry + currency outflow entry."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")

    for _ in range(5):
        ws.append(["", "", "", "", "", "", ""])
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append([
        "Stock purchase", "AAPL", "Apple",
        "2026-01-15 12:00:00", -1250.70, 222,
        "OPEN BUY 10/10 @ 125.07",
    ])

    del wb["Sheet"]
    xlsx_path = tmp / "test_buy.xlsx"
    wb.save(str(xlsx_path))
    wb.close()

    txns = parse_xtb_excel(str(xlsx_path), "EUR")
    assert len(txns) == 1

    entries = txns[0]["entries"]
    assert len(entries) == 2

    stock_entry = next(e for e in entries if e["ticker"] == "AAPL")
    cash_entry = next(e for e in entries if e["ticker"] == "EUR")

    assert stock_entry["amount"] == 10.0
    assert cash_entry["amount"] == -1250.70


def test_xtb_withholding_tax(tmp: Path):
    """Withholding tax creates a currency entry (no account_operation)."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")

    for _ in range(5):
        ws.append(["", "", "", "", "", "", ""])
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append([
        "Withholding tax", "FB2A.DE", "Meta",
        "2026-03-26 10:57:00", -0.76, 333,
        "FB2A.DE USD WHT 30%",
    ])

    del wb["Sheet"]
    xlsx_path = tmp / "test_wht.xlsx"
    wb.save(str(xlsx_path))
    wb.close()

    txns = parse_xtb_excel(str(xlsx_path), "EUR")
    assert len(txns) == 1

    entries = txns[0]["entries"]
    assert len(entries) == 1
    assert entries[0]["ticker"] == "EUR"
    assert entries[0]["amount"] == -0.76
    assert entries[0].get("account_operation") is None or entries[0].get("account_operation") is False


def test_xtb_negative_position_gets_fixed(tmp: Path):
    """Sell without prior buy gets a compensating buy of X shares for 0.01 cash."""
    from xtb_import import parse_xtb_excel
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Cash Operations")

    for _ in range(5):
        ws.append(["", "", "", "", "", "", ""])
    ws.append(["Type", "Ticker", "Instrument", "Time", "Amount", "ID", "Comment"])
    ws.append([
        "Stock sell", "S2B.WA", "S2B",
        "2026-05-20 10:00:00", 193.50, 111,
        "CLOSE BUY 5.7315/5.7315 @ 33.76",
    ])

    del wb["Sheet"]
    xlsx_path = tmp / "test_negative.xlsx"
    wb.save(str(xlsx_path))
    wb.close()

    txns = parse_xtb_excel(str(xlsx_path), "PLN")
    assert len(txns) == 2

    sell_rec = txns[0]
    sell_entry = next(e for e in sell_rec["entries"] if e["ticker"] == "S2B.WA")
    assert sell_entry["amount"] < 0

    fix_rec = txns[1]
    buy_entry = next(e for e in fix_rec["entries"] if e["ticker"] == "S2B.WA")
    cash_entry = next(e for e in fix_rec["entries"] if e["ticker"] == "PLN")
    assert buy_entry["amount"] == abs(sell_entry["amount"])
    assert cash_entry["amount"] == -0.01


# ── Ticker translate tests ─────────────────────────────────────────────────────

def test_translate_no_rules(tmp: Path):
    """translate_ticker with no rules returns uppercased input."""
    from ticker_translate import translate_ticker
    assert translate_ticker("aapl") == "AAPL"
    assert translate_ticker("GOOG") == "GOOG"
    assert translate_ticker("", None) == ""


def test_translate_exact_match(tmp: Path):
    """Exact match rule replaces ticker."""
    from ticker_translate import translate_ticker
    rules = ["AMZN.DE=AMZ.DE", "VOW3.DE=VOW.DE"]
    assert translate_ticker("AMZN.DE", rules) == "AMZ.DE"
    assert translate_ticker("VOW3.DE", rules) == "VOW.DE"
    assert translate_ticker("AAPL.DE", rules) == "AAPL.DE"  # no match


def test_translate_suffix_swap(tmp: Path):
    """Suffix swap rule *.PL=*.WA replaces extension."""
    from ticker_translate import translate_ticker
    rules = ["*.PL=*.WA"]
    assert translate_ticker("SNT.PL", rules) == "SNT.WA"
    assert translate_ticker("CDR.PL", rules) == "CDR.WA"
    assert translate_ticker("AAPL.US", rules) == "AAPL.US"  # no match


def test_translate_suffix_strip(tmp: Path):
    """Suffix strip rule .US= removes the suffix."""
    from ticker_translate import translate_ticker
    rules = [".US="]
    assert translate_ticker("AAPL.US", rules) == "AAPL"
    assert translate_ticker("GOOG.US", rules) == "GOOG"
    assert translate_ticker("AAPL.DE", rules) == "AAPL.DE"  # no match


def test_translate_no_match(tmp: Path):
    """No matching rule returns uppercased input."""
    from ticker_translate import translate_ticker
    rules = ["AMZN.DE=AMZ.DE", "*.PL=*.WA"]
    assert translate_ticker("MSFT", rules) == "MSFT"
    assert translate_ticker("AAPL.US", rules) == "AAPL.US"


# ── Transactions: set_account_operation, get_transactions_up_to, get_all_tickers ──

def test_set_account_operation(tmp: Path):
    """set_account_operation toggles the flag on an entry."""
    import transactions

    transactions.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.0},
    ])

    recs = transactions.get_all_transactions()
    assert recs[0]["entries"][0].get("account_operation") is None

    transactions.set_account_operation("2023-01-03", 0, True)
    recs = transactions.get_all_transactions()
    assert recs[0]["entries"][0].get("account_operation") is True

    transactions.set_account_operation("2023-01-03", 0, False)
    recs = transactions.get_all_transactions()
    assert recs[0]["entries"][0].get("account_operation") is None


def test_get_transactions_up_to(tmp: Path):
    """get_transactions_up_to returns only transactions up to the given date."""
    import transactions

    transactions.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 5.0}])
    transactions.add_transaction("2023-01-10", [{"ticker": "MSFT", "amount": 3.0}])
    transactions.add_transaction("2023-06-01", [{"ticker": "GOOG", "amount": 2.0}])

    result = transactions.get_transactions_up_to("2023-01-10")
    dates = [r["date"] for r in result]
    assert "2023-01-03" in dates
    assert "2023-01-10" in dates
    assert "2023-06-01" not in dates
    assert len(result) == 2


def test_get_all_tickers(tmp: Path):
    """get_all_tickers returns stock tickers plus FX pair tickers."""
    import transactions

    transactions.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.0},
    ])
    transactions.add_transaction("2023-01-06", [
        {"ticker": "QDVE.DE", "amount": 5.0},
        {"ticker": "EUR", "amount": -1000.0},
    ])

    tickers = transactions.get_all_tickers(include_fx=True)
    assert "AAPL" in tickers
    assert "QDVE.DE" in tickers
    # Cash tickers excluded, FX pairs included
    assert "USD" not in tickers
    assert "EUR" not in tickers


# ── Storage: project management ────────────────────────────────────────────────

def test_create_and_list_projects(tmp: Path):
    """create_project + list_projects returns sorted project names."""
    import storage

    storage.create_project("alpha")
    storage.create_project("gamma")
    storage.create_project("beta")

    projects = storage.list_projects()
    assert "alpha" in projects
    assert "beta" in projects
    assert "gamma" in projects
    assert projects == sorted(projects)


def test_rename_project(tmp: Path):
    """rename_project preserves project data under new name."""
    import storage

    storage.create_project("old_name")
    storage.set_current_project("old_name")
    storage.save_balance({"AAPL": {"amount": 10.0, "avg_price": 150.0}})

    storage.rename_project("old_name", "new_name")

    projects = storage.list_projects()
    assert "new_name" in projects
    assert "old_name" not in projects

    storage.set_current_project("new_name")
    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 10.0


def test_delete_project(tmp: Path):
    """delete_project removes project directory and registry entry."""
    import storage

    storage.create_project("to_delete")
    assert "to_delete" in storage.list_projects()

    storage.delete_project("to_delete")
    assert "to_delete" not in storage.list_projects()


def test_project_config_isolation(tmp: Path):
    """Different projects can have independent configs."""
    import storage, json

    storage.create_project("proj_a")
    cfg_a = storage.project_config_path("proj_a")
    cfg_a.write_text(json.dumps({"name": "Portfolio A"}))

    storage.create_project("proj_b")
    cfg_b = storage.project_config_path("proj_b")
    cfg_b.write_text(json.dumps({"name": "Portfolio B"}))

    assert json.loads(cfg_a.read_text())["name"] == "Portfolio A"
    assert json.loads(cfg_b.read_text())["name"] == "Portfolio B"


# ── Storage: benchmark roundtrip ───────────────────────────────────────────────

def test_benchmark_save_load_roundtrip(tmp: Path):
    """save_benchmarks → load_benchmarks roundtrip preserves data."""
    import storage

    data = [
        {"date": "2023-01-03", "SXRV.DE": 5000.0, "I500.DE": 4800.0},
        {"date": "2023-01-04", "SXRV.DE": 5050.0, "I500.DE": 4820.0},
    ]
    storage.save_benchmarks("PLN", data)
    loaded = storage.load_benchmarks("PLN")
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0]["SXRV.DE"] == 5000.0
    assert loaded[1]["I500.DE"] == 4820.0


def test_benchmark_load_returns_none_when_missing(tmp: Path):
    """load_benchmarks returns None when no cache file exists."""
    import storage
    assert storage.load_benchmarks("USD") is None


# ── Portfolio: withdrawal and _ticker_currency ─────────────────────────────────

def test_withdrawal_decreases_invested(tmp: Path):
    """Withdrawal (negative account_operation) reduces invested capital."""
    import transactions, portfolio

    fx.inject_fake_prices(tmp)

    transactions.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0},
    ])
    transactions.add_transaction("2023-01-04", [
        {"ticker": "PLN", "amount": -3000.0, "account_operation": True},
    ])

    snaps = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 4),
        base_currency="PLN",
        precision="D",
        use_cache=False,
    )

    snap_jan3 = next(s for s in snaps if s["date"] == "2023-01-03")
    snap_jan4 = next(s for s in snaps if s["date"] == "2023-01-04")

    assert abs(snap_jan3["invested"] - 10000.0) < 1.0
    assert abs(snap_jan4["invested"] - 7000.0) < 1.0, \
        f"Withdrawal should reduce invested to ~7000, got {snap_jan4['invested']}"
    assert abs(snap_jan4["total_value"] - 7000.0) < 1.0


def test_ticker_currency_detection(tmp: Path):
    """_ticker_currency maps suffixes to correct currencies."""
    from portfolio import _ticker_currency

    assert _ticker_currency("PLN") == "PLN"
    assert _ticker_currency("USD") == "USD"
    assert _ticker_currency("EUR") == "EUR"
    assert _ticker_currency("QDVE.DE") == "EUR"
    assert _ticker_currency("SNT.WA") == "PLN"
    assert _ticker_currency("4GLD.L") == "GBP"
    assert _ticker_currency("AAPL") == "USD"  # no suffix → USD default

    # Unknown suffix defaults to USD (triggers warning on stdout)
    import io, sys
    old = sys.stdout
    sys.stdout = io.StringIO()
    assert _ticker_currency("AAPL.US") == "USD"
    sys.stdout = old


# ── Manual import tests ────────────────────────────────────────────────────────

def test_manual_validate_errors(tmp: Path):
    """validate_manual_file catches various malformed inputs."""
    from manual_import import validate_manual_file

    empty = tmp / "empty.json"
    empty.write_text("")
    valid, msg = validate_manual_file(empty)
    assert not valid
    assert "empty" in msg.lower()

    bad_json = tmp / "bad.json"
    bad_json.write_text("{not json}")
    valid, msg = validate_manual_file(bad_json)
    assert not valid

    not_array = tmp / "not_array.json"
    not_array.write_text('{"date": "2023-01-03"}')
    valid, msg = validate_manual_file(not_array)
    assert not valid
    assert "array" in msg.lower()

    missing_date = tmp / "missing_date.json"
    missing_date.write_text('[{"entries": [{"ticker": "AAPL", "amount": 10}]}]')
    valid, msg = validate_manual_file(missing_date)
    assert not valid
    assert "date" in msg.lower()

    missing_ticker = tmp / "missing_ticker.json"
    missing_ticker.write_text('[{"date": "2023-01-03", "entries": [{"amount": 10}]}]')
    valid, msg = validate_manual_file(missing_ticker)
    assert not valid
    assert "ticker" in msg.lower()


def test_manual_parse_and_import(tmp: Path):
    """parse_manual_json parses correctly; import_manual deduplicates."""
    from manual_import import parse_manual_json, import_manual

    data = [
        {
            "date": "2023-01-03",
            "entries": [
                {"ticker": "AAPL", "amount": 10.0},
                {"ticker": "USD", "amount": -1250.0},
            ],
        },
        {
            "date": "2023-01-04",
            "entries": [
                {"ticker": "MSFT", "amount": 5.0, "account_operation": True},
            ],
        },
    ]

    json_file = tmp / "test_manual.json"
    json_file.write_text(json.dumps(data))

    parsed = parse_manual_json(json_file)
    assert len(parsed) == 2
    assert parsed[0]["date"] == "2023-01-03"
    assert len(parsed[0]["entries"]) == 2
    assert parsed[1]["entries"][0].get("account_operation") is True

    result = import_manual(json_file)
    assert result["success"] is True
    assert result["imported"] == 2

    # Import again — should skip duplicates
    result2 = import_manual(json_file)
    assert result2["success"] is True
    assert result2["skipped"] == 2
    assert result2["imported"] == 0


# ── BOSSA validate tests ──────────────────────────────────────────────────────

def test_bossa_validate_errors(tmp: Path):
    """validate_bossa_file catches empty and malformed files."""
    from bossa_import import validate_bossa_file

    empty = tmp / "empty.csv"
    empty.write_text("")
    valid, msg = validate_bossa_file(empty)
    assert not valid
    assert "empty" in msg.lower()

    wrong_cols = tmp / "wrong.csv"
    wrong_cols.write_text("name;value\ntest;123")
    valid, msg = validate_bossa_file(wrong_cols)
    assert not valid
    assert "missing" in msg.lower()

    valid_file = tmp / "valid.csv"
    valid_file.write_text("data;tytuł operacji;szczegóły;kwota;waluta\nrow1;row2;row3;row4;row5")
    valid, msg = validate_bossa_file(valid_file)
    assert valid


# ── ISIN resolve tests ─────────────────────────────────────────────────────────

def test_isin_resolve_from_config(tmp: Path):
    """resolve_isins_with_names resolves ISINs based on config rules."""
    import json as _json
    import config as cfg_module

    cfg = cfg_module.load()
    cfg["isin_tickers"] = [
        "IE00B4L5Y983=IWDA.L",
        "US5949181085=MSFT.US",
    ]
    cfg_module.save(cfg)

    from isin_resolve import resolve_isins_with_names

    isin_map = {
        "IE00B4L5Y983": "iShares Core MSCI World",
        "US5949181085": "Microsoft",
        "DE0005793303": "unknown fund",
    }

    resolved, unresolved = resolve_isins_with_names(isin_map)
    assert resolved["IE00B4L5Y983"] == "IWDA.L"
    assert resolved["US5949181085"] == "MSFT.US"
    assert "DE0005793303" in unresolved
    assert unresolved["DE0005793303"] == "unknown fund"


# ── Skip-today transaction tests ──────────────────────────────────────────────

def test_portfolio_skips_today_transactions(tmp: Path):
    """build_portfolio excludes transactions dated today."""
    from unittest.mock import patch
    import transactions, portfolio
    from datetime import date as _real_date

    fx.inject_fake_prices(tmp)

    # Yesterday's transaction — should be included
    transactions.add_transaction("2023-01-04", [
        {"ticker": "AAPL", "amount": 10.0},
    ])
    # Today's transaction — should be skipped
    transactions.add_transaction("2023-01-05", [
        {"ticker": "AAPL", "amount": 5.0},
    ])

    class _FakeDate(_real_date):
        @classmethod
        def today(cls):
            return _real_date(2023, 1, 5)

    with patch.object(transactions, "date", _FakeDate), \
         patch.object(portfolio, "date", _FakeDate):
        snapshots = portfolio.build_portfolio(
            start_date=date(2023, 1, 3),
            end_date=date(2023, 1, 5),
            base_currency="PLN",
            precision="D",
            use_cache=False,
        )

    snap = next(s for s in snapshots if s["date"] == "2023-01-05")
    aapl = next((a for a in snap["assets"] if a["ticker"] == "AAPL"), None)
    assert aapl is not None, "AAPL from yesterday should appear"
    assert abs(aapl["amount"] - 10.0) < 1e-6, \
        f"Should hold 10 AAPL (today's +5 skipped), got {aapl['amount']}"


def test_rebuild_balance_skips_today_transactions(tmp: Path):
    """_rebuild_balance excludes today's records from balance and avg_price."""
    from unittest.mock import patch
    import transactions, storage
    from datetime import date as _real_date

    fx.inject_fake_prices(tmp)

    transactions.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
    ])
    transactions.add_transaction("2023-01-05", [
        {"ticker": "AAPL", "amount": 5.0},
    ])

    class _FakeDate(_real_date):
        @classmethod
        def today(cls):
            return _real_date(2023, 1, 5)

    with patch.object(transactions, "date", _FakeDate):
        records = transactions.get_all_transactions()
        transactions._rebuild_balance(records)

    bal = storage.load_balance()
    assert abs(bal["AAPL"]["amount"] - 10.0) < 1e-6, \
        f"Balance should be 10 AAPL (today's +5 skipped), got {bal['AAPL']['amount']}"


# ── Holdings return calculation tests ─────────────────────────────────────────

def test_avg_price_stored_in_native_currency(tmp: Path):
    """avg_price is stored in the ticker's native currency (EUR for .DE stocks)."""
    import transactions, storage

    fx.inject_fake_prices(tmp)
    storage.save_price_year("SEC0.DE", 2023, {"2023-01-03": 88.27})

    transactions.add_transaction("2023-01-03", [
        {"ticker": "SEC0.DE", "amount": 288.0},
        {"ticker": "EUR",     "amount": -25425.0},
    ])

    bal = storage.load_balance()
    avg = bal["SEC0.DE"]["avg_price"]
    assert abs(avg - 88.27) < 0.01, \
        f"avg_price should be 88.27 EUR (native), got {avg}"


def test_avg_price_usd_stored_in_usd(tmp: Path):
    """avg_price for USD stock is stored in USD."""
    import transactions, storage

    fx.inject_fake_prices(tmp)
    storage.save_price_year("GOOG", 2023, {"2023-01-03": 88.0})

    transactions.add_transaction("2023-01-03", [
        {"ticker": "GOOG", "amount": 10.0},
        {"ticker": "USD",  "amount": -880.0},
    ])

    bal = storage.load_balance()
    avg = bal["GOOG"]["avg_price"]
    assert abs(avg - 88.0) < 0.01, \
        f"avg_price should be 88.0 USD (native), got {avg}"


def test_cost_basis_eur_stock_converts_to_pln(tmp: Path):
    """Cost basis for EUR stock uses avg_price × EURPLN rate × shares."""
    import transactions, portfolio, storage

    fx.inject_fake_prices(tmp)
    storage.save_price_year("SEC0.DE", 2023, {
        "2023-01-03": 88.27,
        "2023-01-04": 90.00,
    })

    transactions.add_transaction("2023-01-03", [
        {"ticker": "SEC0.DE", "amount": 288.0},
        {"ticker": "EUR",     "amount": -25425.0},
    ])

    snaps = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 4),
        base_currency="PLN",
        precision="D",
        use_cache=False,
    )

    snap = next(s for s in snaps if s["date"] == "2023-01-04")
    asset = next(a for a in snap["assets"] if a["ticker"] == "SEC0.DE")

    bal = storage.load_balance()
    avg_raw = bal["SEC0.DE"]["avg_price"]  # 88.27 EUR (native)

    # avg_price is in native EUR, not PLN — verify it's the stock price, not inflated
    assert 80 < avg_raw < 100, \
        f"avg_price should be ~88 EUR (native), got {avg_raw}"

    # Value uses EURPLN, cost basis must use same currency
    # Return = (90/88.27 - 1) × 100 ≈ 1.96% — FX cancels out
    ret_pct = ((asset["value_base"] / (asset["amount"] * avg_raw * 4.67)) - 1) * 100
    assert 0 < ret_pct < 5, \
        f"Return should be ~2%, got {ret_pct:.1f}%"


def test_return_eur_stock_not_inflated(tmp: Path):
    """Return for EUR stock is reasonable, not 300%+ due to missing FX conversion."""
    import transactions, portfolio, storage

    fx.inject_fake_prices(tmp)
    storage.save_price_year("SXRV.DE", 2023, {
        "2023-01-03": 42.0,
        "2023-01-09": 44.0,
    })

    transactions.add_transaction("2023-01-03", [
        {"ticker": "SXRV.DE", "amount": 3.5},
        {"ticker": "EUR",     "amount": -147.0},
    ])

    snaps = portfolio.build_portfolio(
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 9),
        base_currency="PLN",
        precision="D",
        use_cache=False,
    )

    snap = next(s for s in snaps if s["date"] == "2023-01-09")
    asset = next(a for a in snap["assets"] if a["ticker"] == "SXRV.DE")

    bal = storage.load_balance()
    avg_raw = bal["SXRV.DE"]["avg_price"]  # 42.0 EUR (native)

    # avg_price should be the EUR stock price, not some PLN-inflated number
    assert 30 < avg_raw < 50, \
        f"avg_price should be ~42 EUR (native), got {avg_raw}"

    # Return ≈ 44/42 - 1 ≈ 4.8%. With proper FX conversion both value and
    # cost_basis use the same EURPLN rate, so it cancels out.
    # Without the fix, cost_basis would be in EUR while value is in PLN → 300%+.
    # We just check it's in a sane range (0–20%).
    shares = asset["amount"]
    # Use avg_raw directly (native EUR) — this is what the holdings table
    # does BEFORE the fix (missing FX conversion). If the fix works,
    # the return should be ~5% regardless of FX rate used.
    ret_pct_native = ((asset["value_base"] / (shares * avg_raw * 4.34)) - 1) * 100
    assert -5 < ret_pct_native < 20, \
        f"Return ~{ret_pct_native:.1f}% looks inflated (FX conversion may be missing)"


# ── Runner ────────────────────────────────────────────────────────────────────

ALL_TESTS = [
    ("Config: creates defaults",              test_config_defaults),
    ("Transactions: buy EUR ETF full sell",   test_buy_eur_etf_full_sell),
    ("Transactions: buy USD stock partial",   test_buy_usd_stock_partial_sell),
    ("Portfolio: sell proceeds not contrib",  test_sell_proceeds_not_counted_as_invested),
    ("Portfolio: cash deposit is contrib",    test_currency_exchange_counts_as_invested),
    ("Portfolio: EUR stock → PLN correct",    test_eur_stock_valued_correctly_in_pln),
    ("Portfolio: USD stock → PLN correct",    test_usd_stock_valued_correctly_in_pln),
    ("Portfolio: mixed PLN/EUR/USD portfolio",test_mixed_portfolio_pln_eur_usd),
    ("Config: save and reload",               test_config_save_and_reload),
    ("Config: precision mapping",             test_config_precision_mapping),
    ("Storage: JSONL round-trip",             test_storage_jsonl_roundtrip),
    ("Storage: JSONL append",                 test_storage_append_jsonl),
    ("Storage: balance save/load",            test_storage_balance),
    ("Storage: price cache write/read",       test_price_cache_write_read),
    ("Storage: load_prices_range",            test_storage_loads_prices_range),
    ("Transactions: add simple",              test_add_transaction_simple),
    ("Transactions: same-date merges",        test_add_transaction_same_date_merges),
    ("Transactions: chronological append",    test_add_transaction_chronological_append),
    ("Transactions: past-date insert",        test_add_transaction_past_date_inserts_correctly),
    ("Transactions: compute_holdings_at",     test_compute_holdings_at),
    ("Transactions: full sell zeroes balance",test_balance_after_full_sell),
    ("Transactions: delete entry",            test_delete_transaction),
    ("Transactions: delete last entry removes record", test_delete_last_entry_removes_record),
    ("Transactions: update entry",            test_update_transaction),
    ("Transactions: get_tickers",             test_get_tickers),
    ("XTB: parse_shares",                     test_xtb_parse_shares),
    ("XTB: parse_transfer_rate",              test_xtb_parse_transfer_rate),
    ("XTB: parse_transfer_target",            test_xtb_parse_transfer_target),
    ("XTB: transfer creates source entry",    test_xtb_transfer_creates_source_entry),
    ("XTB: deposit has account_operation",    test_xtb_deposit_creates_account_operation),
    ("XTB: stock purchase two entries",       test_xtb_stock_purchase_creates_two_entries),
    ("XTB: withholding tax entry",            test_xtb_withholding_tax),
    ("XTB: negative position gets fixed",    test_xtb_negative_position_gets_fixed),
    ("Prices: weekend fallback",              test_get_price_fallback_weekend),
    ("Prices: cash returns 1.0",              test_get_price_cash_returns_one),
    ("FX: same-currency rate is 1.0",         test_get_fx_rate_same_currency),
    ("FX: USD→PLN from cache",                test_get_fx_rate_usd_to_pln),
    ("Portfolio: invalidate cache",           test_invalidate_portfolio),
    ("Portfolio: single asset PLN value",     test_portfolio_build_single_asset),
    ("Portfolio: cash-only",                  test_portfolio_build_cash_only),
    ("Portfolio: invested tracking",      test_portfolio_invested_tracking),
    ("Portfolio: weekly precision Fridays",   test_portfolio_weekly_precision),
    ("Portfolio: cache resume",               test_portfolio_cache_resumes),
    ("Portfolio: _day_range daily",           test_day_range_daily),
    ("Portfolio: _day_range weekly",          test_day_range_weekly),
    ("Portfolio: snapshots_to_series",        test_snapshots_to_series),
    # ── New tests ────────────────────────────────────────────────────────────
    ("Ticker translate: no rules",            test_translate_no_rules),
    ("Ticker translate: exact match",         test_translate_exact_match),
    ("Ticker translate: suffix swap",         test_translate_suffix_swap),
    ("Ticker translate: suffix strip",        test_translate_suffix_strip),
    ("Ticker translate: no match",            test_translate_no_match),
    ("Transactions: set_account_operation",   test_set_account_operation),
    ("Transactions: get_transactions_up_to",  test_get_transactions_up_to),
    ("Transactions: get_all_tickers",         test_get_all_tickers),
    ("Storage: create and list projects",     test_create_and_list_projects),
    ("Storage: rename project",               test_rename_project),
    ("Storage: delete project",               test_delete_project),
    ("Storage: project config isolation",     test_project_config_isolation),
    ("Storage: benchmark save/load",          test_benchmark_save_load_roundtrip),
    ("Storage: benchmark load missing",       test_benchmark_load_returns_none_when_missing),
    ("Portfolio: withdrawal decreases invested", test_withdrawal_decreases_invested),
    ("Portfolio: ticker currency detection",  test_ticker_currency_detection),
    ("Manual: validate errors",              test_manual_validate_errors),
    ("Manual: parse and import",              test_manual_parse_and_import),
    ("BOSSA: validate errors",               test_bossa_validate_errors),
    ("ISIN: resolve from config",            test_isin_resolve_from_config),
    ("Portfolio: skips today transactions",   test_portfolio_skips_today_transactions),
    ("Rebuild balance: skips today",          test_rebuild_balance_skips_today_transactions),
    ("Avg price: stored in native currency",  test_avg_price_stored_in_native_currency),
    ("Avg price: USD stock in USD",           test_avg_price_usd_stored_in_usd),
    ("Cost basis: EUR stock → PLN",           test_cost_basis_eur_stock_converts_to_pln),
    ("Return: EUR stock not inflated",        test_return_eur_stock_not_inflated),
]


def main():
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("   Negotium - Investment Tracker — Test Suite")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    for name, fn in ALL_TESTS:
        run_test(name, fn)

    passed  = sum(1 for _, ok, _ in _RESULTS if ok)
    failed  = sum(1 for _, ok, _ in _RESULTS if not ok)
    total   = len(_RESULTS)

    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  {passed}/{total} passed", end="")
    if failed:
        print(f"  |  {failed} FAILED")
    else:
        print("  — all green ✓")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if failed:
        print("\nFailed tests:")
        for name, ok, tb in _RESULTS:
            if not ok:
                print(f"\n  ✗ {name}")
                for line in tb.strip().splitlines():
                    print(f"    {line}")

    cleanup()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
