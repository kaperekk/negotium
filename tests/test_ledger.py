"""Transaction ledger & metrics — pytest suite (split from the original monolithic runner)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch
import fixtures as fx
import json


def test_first_transaction_date(tmp: Path):
    """first_transaction_date → earliest tx date; None when there are none."""
    import ledger_core
    import storage
    from datetime import date as _date

    ledger_core.get_all_transactions._cache.clear()
    assert ledger_core.first_transaction_date() is None

    storage.transactions_path().parent.mkdir(parents=True, exist_ok=True)
    storage.transactions_path().write_bytes(
        b'{"date":"2024-03-05","entries":[]}\n'
        b'{"date":"2024-01-10","entries":[]}\n'
    )
    ledger_core.get_all_transactions._cache.clear()
    assert ledger_core.first_transaction_date() == _date(2024, 1, 10)
    ledger_core.get_all_transactions._cache.clear()


def test_add_transaction_simple(tmp: Path):
    """Adding a transaction creates the ledger and updates balance."""
    import ledger_core, storage
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    recs = ledger_core.get_all_transactions()
    assert len(recs) == 1
    assert recs[0]["date"] == "2023-01-03"

    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 10.0
    assert abs(bal["USD"]["amount"] - (-1250.70)) < 0.01


def test_add_transaction_same_date_merges(tmp: Path):
    """Two transactions on the same date are merged into one line."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 5.0}])
    ledger_core.add_transaction("2023-01-03", [{"ticker": "MSFT", "amount": 3.0}])

    recs = ledger_core.get_all_transactions()
    assert len(recs) == 1, "Same-date transactions should merge into one record"
    tickers_in_rec = {e["ticker"] for e in recs[0]["entries"]}
    assert "AAPL" in tickers_in_rec
    assert "MSFT" in tickers_in_rec


def test_add_transaction_chronological_append(tmp: Path):
    """Transactions on later dates are appended in order."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 5.0}])
    ledger_core.add_transaction("2023-01-09", [{"ticker": "MSFT", "amount": 2.0}])
    ledger_core.add_transaction("2023-06-01", [{"ticker": "PLN", "amount": 1000.0}])

    recs = ledger_core.get_all_transactions()
    assert len(recs) == 3
    assert recs[0]["date"] == "2023-01-03"
    assert recs[1]["date"] == "2023-01-09"
    assert recs[2]["date"] == "2023-06-01"


def test_add_transaction_past_date_inserts_correctly(tmp: Path):
    """Inserting a past-date transaction reorders the file correctly."""
    import ledger_core

    ledger_core.add_transaction("2023-01-09", [{"ticker": "AAPL", "amount": 10.0}])
    ledger_core.add_transaction("2023-06-01", [{"ticker": "PLN", "amount": 500.0}])

    # Now insert something between them
    ledger_core.add_transaction("2023-01-04", [{"ticker": "USD", "amount": 1000.0}])

    recs = ledger_core.get_all_transactions()
    dates = [r["date"] for r in recs]
    assert dates == sorted(dates), f"Ledger must stay chronological, got: {dates}"
    assert dates[0] == "2023-01-04"


def test_balance_after_backdated_insert(tmp: Path):
    """REGRESSION: back-dated insert must not double-count existing records.

    The old _rebuild_balance(from_date=...) replayed the ledger suffix on top
    of a balance that already included those records, corrupting balance.json.
    """
    import ledger_core, storage

    ledger_core.add_transaction("2024-01-10", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1700.0},
    ])
    ledger_core.add_transaction("2023-12-01", [
        {"ticker": "AAPL", "amount": 5.0},
        {"ticker": "USD", "amount": -850.0},
    ])

    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 15.0, \
        f"AAPL must be 15.0 after back-dated insert, got {bal['AAPL']['amount']}"
    assert bal["USD"]["amount"] == -2550.0, \
        f"USD must be -2550.0 after back-dated insert, got {bal['USD']['amount']}"


def test_balance_after_same_date_merge(tmp: Path):
    """REGRESSION: merging into an existing date must not re-apply old entries."""
    import ledger_core, storage

    # Merge into the LAST date
    ledger_core.add_transaction("2024-01-10", [
        {"ticker": "AAPL", "amount": 10.0}, {"ticker": "USD", "amount": -1700.0},
    ])
    ledger_core.add_transaction("2024-01-10", [
        {"ticker": "MSFT", "amount": 2.0}, {"ticker": "USD", "amount": -700.0},
    ])
    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 10.0, \
        f"AAPL must be 10.0 after last-date merge, got {bal['AAPL']['amount']}"
    assert bal["MSFT"]["amount"] == 2.0
    assert bal["USD"]["amount"] == -2400.0

    # Merge into an EARLIER date
    ledger_core.add_transaction("2023-12-01", [
        {"ticker": "AAPL", "amount": 5.0}, {"ticker": "USD", "amount": -850.0},
    ])
    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 15.0, \
        f"AAPL must be 15.0 after past-date merge, got {bal['AAPL']['amount']}"
    assert bal["USD"]["amount"] == -3250.0


def test_existing_entry_counts_allows_legit_duplicates(tmp: Path):
    """Multiset dedup: two identical same-day buys must both importable."""
    import ledger_core, storage

    ledger_core.add_transaction("2024-01-10", [{"ticker": "AAPL", "amount": 5.0}])
    counts = ledger_core.existing_entry_counts()

    key = ("2024-01-10", "AAPL", 5.0)
    assert counts.get(key, 0) == 1

    # Simulate importing a statement that contains the same buy twice:
    # first occurrence is a duplicate, second is legitimate.
    first_is_dup = counts.get(key, 0) > 0
    if first_is_dup:
        counts[key] -= 1
    second_is_dup = counts.get(key, 0) > 0
    assert first_is_dup and not second_is_dup, \
        "multiset dedup must allow one additional identical entry"


def test_compute_holdings_at(tmp: Path):
    """compute_holdings_at returns correct balances at a given date."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 10.0}])
    ledger_core.add_transaction("2023-06-01", [{"ticker": "AAPL", "amount": -5.0}])

    holdings_jan = ledger_core.compute_holdings_at("2023-01-31")
    assert holdings_jan["AAPL"] == 10.0

    holdings_jun = ledger_core.compute_holdings_at("2023-12-31")
    assert holdings_jun["AAPL"] == 5.0


def test_balance_after_full_sell(tmp: Path):
    """Selling all shares of a ticker removes it from holdings."""
    import ledger_core, storage

    ledger_core.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 10.0}])
    ledger_core.add_transaction("2023-01-09", [{"ticker": "AAPL", "amount": -10.0}])

    bal = storage.load_balance()
    assert "AAPL" not in bal or abs(bal.get("AAPL", {}).get("amount", 0)) < 1e-6, \
        "After full sell, AAPL should be gone from balance"


def test_get_tickers(tmp: Path):
    """get_tickers returns all non-cash tickers from the ledger."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.0},  # cash — should be excluded
    ])
    ledger_core.add_transaction("2023-01-09", [
        {"ticker": "CDR.WA", "amount": 5.0},
        {"ticker": "PLN", "amount": -650.0},   # cash — excluded
    ])

    tickers = ledger_core.get_tickers(include_cash=False)
    assert "AAPL" in tickers
    assert "CDR.WA" in tickers
    assert "USD" not in tickers
    assert "PLN" not in tickers


def test_buy_eur_etf_full_sell(tmp: Path):
    """Buy QDVE.DE (EUR ETF), sell all shares, receive EUR back."""
    import ledger_core, storage

    fx.inject_fake_prices(tmp)
    storage.save_price_year("QDVE.DE", 2023, {
        "2023-01-03": 200.0,
        "2023-06-01": 240.0,
    })

    # Buy: 5 shares at 200 EUR each
    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "QDVE.DE", "amount": 5.0},
        {"ticker": "EUR",     "amount": -1000.0},
    ])
    # Sell: all 5 shares at 240 EUR each = 1200 EUR proceeds
    ledger_core.add_transaction("2023-06-01", [
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
    import ledger_core, storage

    fx.inject_fake_prices(tmp)
    storage.save_price_year("GOOG", 2023, {
        "2023-01-03": 88.0,
        "2023-06-01": 122.0,
    })

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "GOOG", "amount": 10.0},
        {"ticker": "USD",  "amount": -880.0},
    ])
    # Sell 4 of 10 shares
    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "GOOG", "amount": -4.0},
        {"ticker": "USD",  "amount": 488.0},   # 4 × 122
    ])

    bal = storage.load_balance()
    assert abs(bal.get("GOOG", {}).get("amount", 0) - 6.0) < 1e-9, \
        f"Expected 6 GOOG remaining, got {bal.get('GOOG', {}).get('amount', 0)}"
    assert abs(bal.get("USD", {}).get("amount", 0) - (-392.0)) < 0.01, \
        f"Expected -392 USD (net cash spent), got {bal.get('USD', {}).get('amount', 0)}"


def test_delete_transaction(tmp: Path):
    """Deleting one entry removes it and rebuilds balance."""
    import ledger_core, storage

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    ledger_core.delete_transaction("2023-01-03", 0)

    recs = ledger_core.get_all_transactions()
    assert len(recs) == 1
    assert len(recs[0]["entries"]) == 1
    assert recs[0]["entries"][0]["ticker"] == "USD"

    bal = storage.load_balance()
    assert "AAPL" not in bal or abs(bal.get("AAPL", {}).get("amount", 0)) < 1e-6


def test_delete_last_entry_removes_record(tmp: Path):
    """Deleting the only entry in a date removes the entire record."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 10.0}])
    ledger_core.add_transaction("2023-06-01", [{"ticker": "MSFT", "amount": 5.0}])

    ledger_core.delete_transaction("2023-01-03", 0)

    recs = ledger_core.get_all_transactions()
    assert len(recs) == 1
    assert recs[0]["date"] == "2023-06-01"


def test_update_transaction(tmp: Path):
    """Updating an entry changes ticker, amount, and account_operation."""
    import ledger_core, storage

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    ledger_core.update_transaction("2023-01-03", 0, "MSFT", 20.0, account_operation=True)

    recs = ledger_core.get_all_transactions()
    e = recs[0]["entries"][0]
    assert e["ticker"] == "MSFT"
    assert e["amount"] == 20.0
    assert e.get("account_operation") is True

    bal = storage.load_balance()
    assert bal["MSFT"]["amount"] == 20.0
    assert "AAPL" not in bal or abs(bal.get("AAPL", {}).get("amount", 0)) < 1e-6


def test_set_account_operation(tmp: Path):
    """set_account_operation toggles the flag on an entry."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.0},
    ])

    recs = ledger_core.get_all_transactions()
    assert recs[0]["entries"][0].get("account_operation") is None

    ledger_core.set_account_operation("2023-01-03", 0, True)
    recs = ledger_core.get_all_transactions()
    assert recs[0]["entries"][0].get("account_operation") is True

    ledger_core.set_account_operation("2023-01-03", 0, False)
    recs = ledger_core.get_all_transactions()
    assert recs[0]["entries"][0].get("account_operation") is None


def test_get_transactions_up_to(tmp: Path):
    """get_transactions_up_to returns only transactions up to the given date."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [{"ticker": "AAPL", "amount": 5.0}])
    ledger_core.add_transaction("2023-01-10", [{"ticker": "MSFT", "amount": 3.0}])
    ledger_core.add_transaction("2023-06-01", [{"ticker": "GOOG", "amount": 2.0}])

    result = ledger_core.get_transactions_up_to("2023-01-10")
    dates = [r["date"] for r in result]
    assert "2023-01-03" in dates
    assert "2023-01-10" in dates
    assert "2023-06-01" not in dates
    assert len(result) == 2


def test_get_all_tickers(tmp: Path):
    """get_all_tickers returns stock tickers plus FX pair tickers."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.0},
    ])
    ledger_core.add_transaction("2023-01-06", [
        {"ticker": "QDVE.DE", "amount": 5.0},
        {"ticker": "EUR", "amount": -1000.0},
    ])

    tickers = ledger_core.get_all_tickers(include_fx=True)
    assert "AAPL" in tickers
    assert "QDVE.DE" in tickers
    # Cash tickers excluded, FX pairs included
    assert "USD" not in tickers
    assert "EUR" not in tickers


def test_rebuild_balance_includes_today_transactions(tmp: Path):
    """_rebuild_balance includes today's records in balance and avg_price."""
    from unittest.mock import patch
    import ledger_core, storage
    from datetime import date as _real_date

    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
    ])
    ledger_core.add_transaction("2023-01-05", [
        {"ticker": "AAPL", "amount": 5.0},
    ])

    class _FakeDate(_real_date):
        @classmethod
        def today(cls):
            return _real_date(2023, 1, 5)

    with patch.object(ledger_core, "date", _FakeDate):
        records = ledger_core.get_all_transactions()
        ledger_core._rebuild_balance(records)

    bal = storage.load_balance()
    assert abs(bal["AAPL"]["amount"] - 15.0) < 1e-6, \
        f"Balance should be 15 AAPL (today's +5 included), got {bal['AAPL']['amount']}"


def test_avg_price_stored_in_native_currency(tmp: Path):
    """avg_price is stored in the ticker's native currency (EUR for .DE stocks)."""
    import ledger_core, storage

    fx.inject_fake_prices(tmp)
    storage.save_price_year("SEC0.DE", 2023, {"2023-01-03": 88.27})

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "SEC0.DE", "amount": 288.0},
        {"ticker": "EUR",     "amount": -25425.0},
    ])

    bal = storage.load_balance()
    avg = bal["SEC0.DE"]["avg_price"]
    assert abs(avg - 88.27) < 0.01, \
        f"avg_price should be 88.27 EUR (native), got {avg}"


def test_avg_price_usd_stored_in_usd(tmp: Path):
    """avg_price for USD stock is stored in USD."""
    import ledger_core, storage

    fx.inject_fake_prices(tmp)
    storage.save_price_year("GOOG", 2023, {"2023-01-03": 88.0})

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "GOOG", "amount": 10.0},
        {"ticker": "USD",  "amount": -880.0},
    ])

    bal = storage.load_balance()
    avg = bal["GOOG"]["avg_price"]
    assert abs(avg - 88.0) < 0.01, \
        f"avg_price should be 88.0 USD (native), got {avg}"


def test_get_ticker_history_buys_and_sells(tmp: Path):
    """get_ticker_history returns chronological buys/sells with correct sides."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD",  "amount": -1250.0},
    ])
    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "AAPL", "amount": -4.0},
        {"ticker": "USD",  "amount": 500.0},
    ])

    hist = ledger_core.get_ticker_history("AAPL")
    assert len(hist) == 2
    assert hist[0]["side"] == "Buy"
    assert hist[0]["amount"] == 10.0
    assert hist[0]["date"] == "2023-01-03"
    assert hist[1]["side"] == "Sell"
    assert hist[1]["amount"] == -4.0
    assert hist[1]["date"] == "2023-06-01"


def test_get_ticker_history_running_shares(tmp: Path):
    """Running position tracks cumulative shares across trades."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [{"ticker": "GOOG", "amount": 10.0}])
    ledger_core.add_transaction("2023-03-01", [{"ticker": "GOOG", "amount": 5.0}])
    ledger_core.add_transaction("2023-06-01", [{"ticker": "GOOG", "amount": -8.0}])

    hist = ledger_core.get_ticker_history("GOOG")
    assert len(hist) == 3
    assert hist[0]["running"] == 10.0
    assert hist[1]["running"] == 15.0
    assert hist[2]["running"] == 7.0


def test_get_ticker_history_excludes_cash(tmp: Path):
    """Cash tickers (USD, EUR, PLN) are excluded from history."""
    import ledger_core

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD",  "amount": -1250.0},
    ])

    hist_aapl = ledger_core.get_ticker_history("AAPL")
    assert len(hist_aapl) == 1

    hist_usd = ledger_core.get_ticker_history("USD")
    assert len(hist_usd) == 0

    hist_pln = ledger_core.get_ticker_history("PLN")
    assert len(hist_pln) == 0


def test_cagr_basic(tmp: Path):
    """CAGR: single deposit growing over time yields positive return."""
    import ledger_core
    from ledger_core import compute_cagr
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0, "account_operation": True},
    ])

    cagr = compute_cagr(12000.0, "PLN")
    assert cagr is not None
    assert cagr > 0


def test_cagr_no_transactions(tmp: Path):
    """CAGR: no transactions returns None."""
    from ledger_core import compute_cagr
    assert compute_cagr(10000.0, "PLN") is None


def test_cagr_zero_invested(tmp: Path):
    """CAGR: zero net invested returns None."""
    import ledger_core
    from ledger_core import compute_cagr
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0, "account_operation": True},
    ])
    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": -10000.0, "account_operation": True},
    ])

    cagr = compute_cagr(0.0, "PLN")
    assert cagr is None


def test_cagr_loss(tmp: Path):
    """CAGR: value below invested yields negative CAGR."""
    import ledger_core
    from ledger_core import compute_cagr
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0, "account_operation": True},
    ])

    cagr = compute_cagr(5000.0, "PLN")
    assert cagr is not None
    assert cagr < 0


def test_cagr_with_fx(tmp: Path):
    """CAGR: USD deposit converted to PLN uses FX rate."""
    import ledger_core
    from ledger_core import compute_cagr
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "USD", "amount": 2000.0, "account_operation": True},
    ])

    cagr = compute_cagr(10000.0, "PLN")
    assert cagr is not None
    assert cagr > 0


def test_irr_basic(tmp: Path):
    """IRR: single deposit with positive return yields positive IRR."""
    import ledger_core
    from ledger_core import compute_irr
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0, "account_operation": True},
    ])

    irr = compute_irr(12000.0, "PLN")
    assert irr is not None
    assert irr > 0


def test_irr_no_transactions(tmp: Path):
    """IRR: no transactions returns None."""
    from ledger_core import compute_irr
    assert compute_irr(10000.0, "PLN") is None


def test_irr_multiple_deposits(tmp: Path):
    """IRR: multiple deposits are handled correctly."""
    import ledger_core
    from ledger_core import compute_irr
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 5000.0, "account_operation": True},
    ])
    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "PLN", "amount": 5000.0, "account_operation": True},
    ])

    irr = compute_irr(12000.0, "PLN")
    assert irr is not None
    assert irr > 0


def test_irr_with_withdrawal(tmp: Path):
    """IRR: withdrawal reduces invested capital correctly."""
    import ledger_core
    from ledger_core import compute_irr
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0, "account_operation": True},
    ])
    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "PLN", "amount": -3000.0, "account_operation": True},
    ])

    irr = compute_irr(9000.0, "PLN")
    assert irr is not None


def test_irr_loss(tmp: Path):
    """IRR: value below invested yields negative IRR."""
    import ledger_core
    from ledger_core import compute_irr
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0, "account_operation": True},
    ])

    irr = compute_irr(5000.0, "PLN")
    assert irr is not None
    assert irr < 0


def _reference_irr(ext_flows: list, terminal: float) -> float:
    """Independent XIRR solver (bisection) used as an oracle for compute_irr.

    ``ext_flows`` is a list of (date_str, amount_in_base_ccy) where outflows
    are negative (deposits) and inflows positive (withdrawals). ``terminal``
    is the final positive portfolio value dated today.
    """
    from datetime import date as _d

    today = _d.today().isoformat()
    items = sorted(list(ext_flows) + [(today, terminal)], key=lambda x: x[0])
    start = _d.fromisoformat(items[0][0])
    yrs = [(_d.fromisoformat(d) - start).days / 365.25 for d, _ in items]
    amts = [a for _, a in items]

    def npv(r: float) -> float:
        return sum(a / (1.0 + r) ** t for a, t in zip(amts, yrs))

    lo, hi = -0.5, 5.0
    for _ in range(300):
        mid = (lo + hi) / 2.0
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
        if abs(hi - lo) < 1e-11:
            break
    return (lo + hi) / 2.0


def _rebuild_npv(current_value: float, base_ccy: str) -> float:
    """Rebuild compute_irr's cash flows and return NPV at the computed IRR.

    Oracle-free correctness check: the IRR returned by compute_irr must zero
    the NPV of exactly the flows it used.
    """
    from datetime import date as _d
    from ledger_core import compute_irr, get_all_transactions
    from ticker_data import get_fx_rate

    base = base_ccy.upper()
    flows: list = []
    for rec in get_all_transactions():
        for e in rec["entries"]:
            if not e.get("account_operation", False):
                continue
            t = e["ticker"].upper()
            amt = float(e["amount"])
            fx = get_fx_rate(t, base, rec["date"], {}, int(rec["date"][:4])) if t != base else 1.0
            flows.append((rec["date"], -amt * fx))

    today = _d.today().isoformat()
    flows.append((today, current_value))
    flows.sort(key=lambda x: x[0])
    start = _d.fromisoformat(flows[0][0])
    yrs = [(_d.fromisoformat(d) - start).days / 365.25 for d, _ in flows]
    amts = [a for _, a in flows]

    irr = compute_irr(current_value, base)
    return irr, sum(a / (1.0 + irr) ** t for a, t in zip(amts, yrs))


def test_irr_known_two_flow(tmp: Path):
    """IRR: a 1-year 1000→1100 deposit equals the closed-form ~10%."""
    import ledger_core
    from ledger_core import compute_irr
    from datetime import date as _d

    fx.inject_fake_prices(tmp)
    dep = _d.today().replace(year=_d.today().year - 1).isoformat()
    ledger_core.add_transaction(dep, [
        {"ticker": "PLN", "amount": 1000.0, "account_operation": True},
    ])
    irr = compute_irr(1100.0, "PLN")
    days = (_d.today() - _d.fromisoformat(dep)).days
    expected = (1100.0 / 1000.0) ** (365.25 / days) - 1.0
    assert abs(irr - expected) < 1e-6


def test_irr_dividend_ignored(tmp: Path):
    """IRR regression: a dividend must NOT change the IRR (it is internal)."""
    import ledger_core
    from ledger_core import compute_irr

    fx.inject_fake_prices(tmp)
    # baseline: deposit only
    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0, "account_operation": True},
    ])
    irr_base = compute_irr(12000.0, "PLN")

    # same deposit + a dividend (currency entry, no account_operation flag)
    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "PLN", "amount": 100.0},
    ])
    irr_div = compute_irr(12000.0, "PLN")
    assert abs(irr_base - irr_div) < 1e-9


def test_irr_withholding_tax_ignored(tmp: Path):
    """IRR regression: a withholding-tax entry must NOT change the IRR."""
    import ledger_core
    from ledger_core import compute_irr

    fx.inject_fake_prices(tmp)
    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 10000.0, "account_operation": True},
    ])
    irr_base = compute_irr(12000.0, "PLN")
    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "PLN", "amount": -20.0},
    ])
    irr_tax = compute_irr(12000.0, "PLN")
    assert abs(irr_base - irr_tax) < 1e-9


def test_irr_fx_deposit(tmp: Path):
    """IRR: a USD deposit is FX-converted and matches a PLN reference IRR."""
    import ledger_core
    from ledger_core import compute_irr
    from ticker_data import get_fx_rate

    fx.inject_fake_prices(tmp)
    dep_date = "2023-01-03"  # USDPLN = 4.38 in fake data
    usd_rate = get_fx_rate("USD", "PLN", dep_date, {}, 2023)
    ledger_core.add_transaction(dep_date, [
        {"ticker": "USD", "amount": 1000.0, "account_operation": True},
    ])
    # terminal value = deposit grown 10% in USD terms, expressed in PLN
    terminal = 1000.0 * usd_rate * 1.10
    irr = compute_irr(terminal, "PLN")
    ref = _reference_irr([(dep_date, -1000.0 * usd_rate)], terminal)
    assert abs(irr - ref) < 1e-6


def test_irr_matches_reference_xirr(tmp: Path):
    """IRR: solver agrees with an independent bisection XIRR oracle."""
    import ledger_core
    from ledger_core import compute_irr

    fx.inject_fake_prices(tmp)
    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 5000.0, "account_operation": True},
    ])
    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "PLN", "amount": -2000.0, "account_operation": True},
    ])
    ledger_core.add_transaction("2023-09-15", [
        {"ticker": "PLN", "amount": 3000.0, "account_operation": True},
    ])
    terminal = 9000.0
    flows = [
        ("2023-01-03", -5000.0),
        ("2023-06-01", 2000.0),
        ("2023-09-15", -3000.0),
    ]
    irr = compute_irr(terminal, "PLN")
    ref = _reference_irr(flows, terminal)
    assert abs(irr - ref) < 1e-6


def test_irr_npv_is_zero(tmp: Path):
    """IRR property: compute_irr's rate zeroes the NPV of its own flows."""
    import ledger_core
    from ledger_core import compute_irr

    fx.inject_fake_prices(tmp)
    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 5000.0, "account_operation": True},
    ])
    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "PLN", "amount": -2000.0, "account_operation": True},
    ])
    ledger_core.add_transaction("2023-09-15", [
        {"ticker": "PLN", "amount": 3000.0, "account_operation": True},
    ])
    _, npv = _rebuild_npv(9000.0, "PLN")
    assert abs(npv) < 1e-6


def test_irr_multiple_sign_changes(tmp: Path):
    """IRR: deposit/withdraw/deposit still yields a finite, bounded rate."""
    import ledger_core
    from ledger_core import compute_irr

    fx.inject_fake_prices(tmp)
    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 1000.0, "account_operation": True},
    ])
    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "PLN", "amount": -400.0, "account_operation": True},
    ])
    ledger_core.add_transaction("2023-09-15", [
        {"ticker": "PLN", "amount": 600.0, "account_operation": True},
    ])
    irr = compute_irr(1500.0, "PLN")
    assert irr is not None
    assert -0.5 <= irr <= 5.0


def test_irr_high_return(tmp: Path):
    """IRR: a very large gain stays within the solver's upper bound."""
    import ledger_core
    from ledger_core import compute_irr

    fx.inject_fake_prices(tmp)
    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "PLN", "amount": 1000.0, "account_operation": True},
    ])
    irr = compute_irr(20000.0, "PLN")
    assert irr is not None
    assert irr > 0.5


def test_avg_price_sell_reduces_proportionally(tmp: Path):
    """_update_avg_prices: sell-only reduces cost pool proportionally."""
    import ledger_core
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "AAPL", "amount": -5.0},
        {"ticker": "USD", "amount": 900.45},
    ])

    import storage
    bal = storage.load_balance()
    assert bal["AAPL"]["amount"] == 5.0
    assert bal["AAPL"]["avg_price"] > 0


def test_avg_price_full_sell_zeroes(tmp: Path):
    """_update_avg_prices: full sell removes ticker from balance."""
    import ledger_core
    fx.inject_fake_prices(tmp)

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    ledger_core.add_transaction("2023-06-01", [
        {"ticker": "AAPL", "amount": -10.0},
        {"ticker": "USD", "amount": 1800.90},
    ])

    import storage
    bal = storage.load_balance()
    assert "AAPL" not in bal or abs(bal.get("AAPL", {}).get("amount", 0)) < 1e-9


def test_remap_tickers_applies_rules(tmp: Path):
    """remap_tickers re-applies ticker_rules to existing entries."""
    import ledger_core
    import storage
    import config

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    cfg = config.load()
    cfg["ticker_rules"] = ["AAPL=MSFT"]
    config.save(cfg)

    changed = ledger_core.remap_tickers()
    assert changed == 1

    records = storage.read_jsonl(storage.transactions_path())
    tickers = [e["ticker"] for r in records for e in r["entries"]]
    assert "MSFT" in tickers
    assert "AAPL" not in tickers


def test_remap_tickers_no_op(tmp: Path):
    """remap_tickers is a no-op when rules don't change any ticker."""
    import ledger_core
    import storage
    import config

    ledger_core.add_transaction("2023-01-03", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1250.70},
    ])

    cfg = config.load()
    cfg["ticker_rules"] = ["MSFT=AAPL"]
    config.save(cfg)

    changed = ledger_core.remap_tickers()
    assert changed == 0
