"""Real-world scenarios that must work correctly.

These tests cover edge cases and life scenarios that could silently corrupt
data or produce incorrect calculations if the implementation is wrong.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import ledger_core
import storage
from ledger_core import (
    add_transaction,
    delete_transaction,
    get_all_transactions,
    update_transaction,
    compute_cagr,
    compute_irr,
)


def _reset():
    """Clear all transactions for a fresh test."""
    for rec in get_all_transactions():
        for i in range(len(rec["entries"]) - 1, -1, -1):
            delete_transaction(rec["date"], i)


# - Scenario 1: Fractional shares -


def test_fractional_shares_buy_and_sell(tmp):
    """Buying and selling fractional shares (common with modern brokers)."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 0.5},
        {"ticker": "USD", "amount": -75.0},
    ])
    add_transaction("2024-02-15", [
        {"ticker": "AAPL", "amount": -0.25},
        {"ticker": "USD", "amount": 40.0},
    ])
    balance = storage.load_balance()
    assert abs(balance["AAPL"]["amount"] - 0.25) < 1e-9
    assert balance["AAPL"]["amount"] > 0


def test_fractional_shares_full_sell(tmp):
    """Sell all fractional shares at once."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 0.12345678},
        {"ticker": "USD", "amount": -20.0},
    ])
    add_transaction("2024-02-15", [
        {"ticker": "AAPL", "amount": -0.12345678},
        {"ticker": "USD", "amount": 25.0},
    ])
    balance = storage.load_balance()
    assert "AAPL" not in balance or abs(balance["AAPL"]["amount"]) < 1e-9


# - Scenario 2: Multiple partial sells -


def test_multiple_partial_sells_avg_price(tmp):
    """Selling shares in multiple transactions preserves avg_price correctly."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1000.0},
    ])
    add_transaction("2024-02-15", [
        {"ticker": "AAPL", "amount": -3.0},
        {"ticker": "USD", "amount": 360.0},
    ])
    add_transaction("2024-03-15", [
        {"ticker": "AAPL", "amount": -4.0},
        {"ticker": "USD", "amount": 440.0},
    ])
    balance = storage.load_balance()
    assert abs(balance["AAPL"]["amount"] - 3.0) < 1e-9
    assert balance["AAPL"]["avg_price"] < 150.0


# - Scenario 3: Weekend/holiday transactions -


def test_weekend_transaction(tmp):
    """Transaction on Saturday should work (uses Friday's close)."""
    _reset()
    add_transaction("2024-01-13", [
        {"ticker": "AAPL", "amount": 1.0},
        {"ticker": "USD", "amount": -150.0},
    ])
    records = get_all_transactions()
    assert len(records) == 1
    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 1.0
    assert balance["AAPL"].get("avg_price", 0) >= 0


def test_holiday_transaction(tmp):
    """Transaction on a holiday should use the previous trading day's price."""
    _reset()
    add_transaction("2024-01-01", [
        {"ticker": "AAPL", "amount": 1.0},
        {"ticker": "USD", "amount": -150.0},
    ])
    records = get_all_transactions()
    assert len(records) == 1
    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 1.0
    assert balance["AAPL"].get("avg_price", 0) >= 0


# - Scenario 4: Zero-cost basis (gift, inheritance, spin-off) -


def test_zero_cost_basis_buy(tmp):
    """Receiving shares for free (gift, inheritance, spin-off)."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])
    add_transaction("2024-02-15", [
        {"ticker": "AAPL", "amount": 5.0},
    ])
    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 15.0
    assert balance["AAPL"]["avg_price"] < 150.0
    assert balance["AAPL"].get("avg_price", 0) >= 0


def test_zero_cost_basis_sell_all(tmp):
    """Sell all shares that were acquired for free."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
    ])
    add_transaction("2024-02-15", [
        {"ticker": "AAPL", "amount": -10.0},
        {"ticker": "USD", "amount": 2000.0},
    ])
    balance = storage.load_balance()
    assert "AAPL" not in balance or abs(balance["AAPL"]["amount"]) < 1e-9


# - Scenario 5: Stock split -


def test_stock_split_double_shares(tmp):
    """2:1 stock split doubles shares, halves avg_price."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -2000.0},
    ])
    add_transaction("2024-02-15", [
        {"ticker": "AAPL", "amount": 10.0},
    ])
    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 20.0
    assert balance["AAPL"]["avg_price"] < 150.0


# - Scenario 6: Empty portfolio (first transaction) -


def test_empty_portfolio_first_buy(tmp):
    """First transaction ever - portfolio starts empty."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 5.0},
        {"ticker": "USD", "amount": -750.0},
    ])
    records = get_all_transactions()
    assert len(records) == 1
    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 5.0
    assert balance["AAPL"].get("avg_price", 0) >= 0


def test_empty_portfolio_deposit_only(tmp):
    """First transaction is a deposit (no stock purchase)."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "USD", "amount": 1000.0},
    ], account_operation=True)
    records = get_all_transactions()
    assert len(records) == 1
    balance = storage.load_balance()
    assert balance["USD"]["amount"] == 1000.0


# - Scenario 7: Delete transaction mid-history -


def test_delete_transaction_mid_history(tmp):
    """Deleting a transaction in the middle of history recalculates correctly."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])
    add_transaction("2024-02-15", [
        {"ticker": "AAPL", "amount": -5.0},
        {"ticker": "USD", "amount": 800.0},
    ])
    add_transaction("2024-03-15", [
        {"ticker": "AAPL", "amount": 3.0},
        {"ticker": "USD", "amount": -450.0},
    ])
    delete_transaction("2024-02-15", 0)
    balance = storage.load_balance()
    assert abs(balance["AAPL"]["amount"] - 13.0) < 1e-9


# - Scenario 8: Update transaction ticker -


def test_update_transaction_ticker(tmp):
    """Changing the ticker of an existing transaction."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])
    update_transaction("2024-01-15", 0, "MSFT", 10.0)
    records = get_all_transactions()
    assert records[0]["entries"][0]["ticker"] == "MSFT"
    balance = storage.load_balance()
    assert "AAPL" not in balance or balance.get("AAPL", {}).get("amount", 0) == 0
    assert balance["MSFT"]["amount"] == 10.0


# - Scenario 9: CAGR with single deposit -


def test_cagr_single_deposit(tmp):
    """CAGR with a single deposit and no withdrawals."""
    _reset()
    add_transaction("2024-01-01", [
        {"ticker": "USD", "amount": 1000.0},
    ], account_operation=True)
    cagr = compute_cagr(1200.0, base_currency="USD", end="2024-07-01")
    assert cagr is not None
    assert cagr > 0


def test_cagr_multiple_deposits_different_dates(tmp):
    """CAGR with multiple deposits at different dates."""
    _reset()
    add_transaction("2024-01-01", [
        {"ticker": "USD", "amount": 1000.0},
    ], account_operation=True)
    add_transaction("2024-04-01", [
        {"ticker": "USD", "amount": 500.0},
    ], account_operation=True)
    cagr = compute_cagr(1800.0, base_currency="USD", end="2024-07-01")
    assert cagr is not None
    assert cagr > 0


# - Scenario 10: IRR edge cases -


def test_irr_single_deposit_no_withdrawal(tmp):
    """IRR with a single deposit and no withdrawal."""
    _reset()
    add_transaction("2024-01-01", [
        {"ticker": "USD", "amount": 1000.0},
    ], account_operation=True)
    irr = compute_irr(1100.0, base_currency="USD", end="2024-07-01")
    assert irr is not None
    assert irr > 0


def test_irr_with_withdrawal(tmp):
    """IRR with a withdrawal."""
    _reset()
    add_transaction("2024-01-01", [
        {"ticker": "USD", "amount": 1000.0},
    ], account_operation=True)
    add_transaction("2024-03-01", [
        {"ticker": "USD", "amount": -200.0},
    ], account_operation=True)
    irr = compute_irr(900.0, base_currency="USD", end="2024-07-01")
    assert irr is not None
    assert irr > 0


def test_irr_loss_scenario(tmp):
    """IRR when portfolio has lost money."""
    _reset()
    add_transaction("2024-01-01", [
        {"ticker": "USD", "amount": 1000.0},
    ], account_operation=True)
    irr = compute_irr(800.0, base_currency="USD", end="2024-07-01")
    assert irr is not None
    assert irr < 0


# - Scenario 11: Many small transactions (DCA) -


def test_many_small_transactions(tmp):
    """Many micro-investments over time (DCA strategy)."""
    _reset()
    for month in range(1, 13):
        add_transaction(f"2024-{month:02d}-15", [
            {"ticker": "AAPL", "amount": 0.5},
            {"ticker": "USD", "amount": -100.0},
        ])
    balance = storage.load_balance()
    assert abs(balance["AAPL"]["amount"] - 6.0) < 1e-9
    assert balance["AAPL"].get("avg_price", 0) >= 0


# - Scenario 12: Same-day buy and sell -


def test_same_day_buy_and_sell_different_tickers(tmp):
    """Buy one ticker and sell another on the same day."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])
    add_transaction("2024-01-15", [
        {"ticker": "MSFT", "amount": -5.0},
        {"ticker": "USD", "amount": -100.0},
    ])
    records = get_all_transactions()
    assert len(records) == 1
    assert len(records[0]["entries"]) == 4


# - Scenario 13: Transaction at year boundary -


def test_transaction_at_year_boundary(tmp):
    """Transaction on December 31 and January 1."""
    _reset()
    add_transaction("2023-12-31", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])
    add_transaction("2024-01-01", [
        {"ticker": "AAPL", "amount": 5.0},
        {"ticker": "USD", "amount": -750.0},
    ])
    records = get_all_transactions()
    assert len(records) == 2
    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 15.0


# - Scenario 14: Sell exact number of shares owned -


def test_sell_exact_shares_owned(tmp):
    """Sell exactly the number of shares owned (should zero out)."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])
    add_transaction("2024-02-15", [
        {"ticker": "AAPL", "amount": -10.0},
        {"ticker": "USD", "amount": 1800.0},
    ])
    balance = storage.load_balance()
    assert "AAPL" not in balance or abs(balance["AAPL"]["amount"]) < 1e-9


# - Scenario 15: CAGR/IRR with no transactions -


def test_cagr_no_transactions(tmp):
    """CAGR returns None when there are no transactions."""
    _reset()
    cagr = compute_cagr(1000.0, base_currency="USD")
    assert cagr is None


def test_irr_no_transactions(tmp):
    """IRR returns None when there are no transactions."""
    _reset()
    irr = compute_irr(1000.0, base_currency="USD")
    assert irr is None


# - Scenario 16: CAGR with zero invested -


def test_cagr_zero_invested(tmp):
    """CAGR returns None when net invested is zero."""
    _reset()
    add_transaction("2024-01-01", [
        {"ticker": "USD", "amount": 1000.0},
    ], account_operation=True)
    add_transaction("2024-02-01", [
        {"ticker": "USD", "amount": -1000.0},
    ], account_operation=True)
    cagr = compute_cagr(0.0, base_currency="USD", end="2024-07-01")
    assert cagr is None


# - Scenario 17: Backdated transaction after many others -


def test_backdated_transaction_after_many(tmp):
    """Inserting a transaction before all existing ones."""
    _reset()
    add_transaction("2024-03-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])
    add_transaction("2024-06-15", [
        {"ticker": "AAPL", "amount": 5.0},
        {"ticker": "USD", "amount": -750.0},
    ])
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 3.0},
        {"ticker": "USD", "amount": -450.0},
    ])
    records = get_all_transactions()
    assert records[0]["date"] == "2024-01-15"
    assert records[1]["date"] == "2024-03-15"
    assert records[2]["date"] == "2024-06-15"
    balance = storage.load_balance()
    assert abs(balance["AAPL"]["amount"] - 18.0) < 1e-9


# - Scenario 18: Delete all transactions -


def test_delete_all_transactions(tmp):
    """Deleting all transactions leaves an empty ledger."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])
    delete_transaction("2024-01-15", 0)
    delete_transaction("2024-01-15", 0)
    records = get_all_transactions()
    assert len(records) == 0
    balance = storage.load_balance()
    assert len(balance) == 0


# - Scenario 19: Update transaction amount -


def test_update_transaction_amount(tmp):
    """Changing the amount of an existing transaction."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])
    update_transaction("2024-01-15", 0, "AAPL", 15.0)
    records = get_all_transactions()
    assert records[0]["entries"][0]["amount"] == 15.0
    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 15.0


# - Scenario 20: Mixed currency transactions -


def test_mixed_currency_transactions(tmp):
    """Transactions in different currencies."""
    _reset()
    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])
    add_transaction("2024-02-15", [
        {"ticker": "SAP", "amount": 5.0},
        {"ticker": "EUR", "amount": -750.0},
    ])
    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 10.0
    assert balance["SAP"]["amount"] == 5.0
    assert balance["USD"]["amount"] == -1500.0
    assert balance["EUR"]["amount"] == -750.0
# ── Scenario 29: Dividend import ────────────────────────────────────────────


def test_dividend_increases_cash_balance(tmp: Path):
    """Dividends from broker import increase the cash balance."""
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    # Import a dividend
    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 12.50},
    ])

    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 10.0
    assert balance["USD"]["amount"] == -1487.50


def test_dividend_does_not_affect_stock_position(tmp: Path):
    """Dividends are cash-only — stock positions are unchanged."""
    import fixtures as fx
    fx.inject_fake_prices(tmp)
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 25.00},
    ])

    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 10.0
    assert balance["AAPL"]["avg_price"] > 0  # unchanged


def test_multiple_dividends_same_ticker(tmp: Path):
    """Multiple dividend payments accumulate correctly."""
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    # Quarterly dividends
    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 8.00},
    ])
    add_transaction("2024-06-15", [
        {"ticker": "USD", "amount": 8.50},
    ])
    add_transaction("2024-09-15", [
        {"ticker": "USD", "amount": 9.00},
    ])

    balance = storage.load_balance()
    assert balance["USD"]["amount"] == -1474.50  # -1500 + 8 + 8.5 + 9


def test_dividend_in_different_currency(tmp: Path):
    """Dividends paid in a different currency than the stock."""
    _reset()

    # Buy EUR stock
    add_transaction("2024-01-15", [
        {"ticker": "SAP", "amount": 5.0},
        {"ticker": "EUR", "amount": -750.0},
    ])

    # Receive dividend in EUR
    add_transaction("2024-03-15", [
        {"ticker": "EUR", "amount": 15.00},
    ])

    balance = storage.load_balance()
    assert balance["SAP"]["amount"] == 5.0
    assert balance["EUR"]["amount"] == -735.0


def test_dividend_with_stock_buy_same_import(tmp: Path):
    """Dividend and stock buy in the same import batch."""
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    # Buy more stock AND receive dividend
    add_transaction("2024-02-15", [
        {"ticker": "AAPL", "amount": 5.0},
        {"ticker": "USD", "amount": -10.0},  # dividend + buy cost
    ])

    balance = storage.load_balance()
    assert balance["AAPL"]["amount"] == 15.0


def test_dividend_persists_after_rebuild(tmp: Path):
    """Dividends survive a balance rebuild."""
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 12.50},
    ])

    # Force a balance rebuild
    ledger_core._rebuild_balance(ledger_core.get_all_transactions())

    balance = storage.load_balance()
    assert balance["USD"]["amount"] == -1487.50


def test_dividend_does_not_affect_irr(tmp: Path):
    """Dividends are internal — they don't change IRR."""
    _reset()

    # Deposit and buy stock
    add_transaction("2024-01-01", [
        {"ticker": "USD", "amount": 1000.0},
    ], account_operation=True)

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    # Get IRR without dividend
    irr_before = ledger_core.compute_irr(2000.0, base_currency="USD", end="2024-07-01")

    # Add a dividend (no account_operation flag)
    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 50.00},
    ])

    # Get IRR with dividend
    irr_after = ledger_core.compute_irr(2000.0, base_currency="USD", end="2024-07-01")

    # IRR should be unchanged (dividend is internal cash movement)
    assert irr_before == irr_after


def test_dividend_first_transaction(tmp: Path):
    """Dividend as the very first transaction (no prior cash balance)."""
    _reset()

    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 100.00},
    ])

    balance = storage.load_balance()
def test_dividend_first_transaction(tmp: Path):
    """Dividend as the very first transaction (no prior cash balance)."""
    _reset()

    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 100.00},
    ])

    balance = storage.load_balance()
    assert balance["USD"]["amount"] == 100.0


def test_dividend_with_tax_withholding(tmp: Path):
    """Dividend with tax withheld — net amount is credited."""
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    # Dividend of $10 with 15% tax withheld → net $8.50
    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 8.50},
    ])

    balance = storage.load_balance()
    assert balance["USD"]["amount"] == -1491.50


def test_dividend_fractional_cents(tmp: Path):
    """Dividend with fractional cents (e.g., $0.333)."""
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 100.0},
        {"ticker": "USD", "amount": -15000.0},
    ])

    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 33.33},
    ])

    balance = storage.load_balance()
    assert abs(balance["USD"]["amount"] - (-14966.67)) < 1e-9


def test_dividend_same_day_as_sell(tmp: Path):
    """Dividend received on the same day as selling the stock."""
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    # Sell all shares and receive dividend on the same day
    add_transaction("2024-03-15", [
        {"ticker": "AAPL", "amount": -10.0},
        {"ticker": "USD", "amount": 1600.0},
    ])

    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 25.00},
    ])

    balance = storage.load_balance()
    # AAPL fully sold — ticker removed from balance
    aapl_balance = balance.get("AAPL", {}).get("amount", 0.0)
    assert abs(aapl_balance) < 1e-9
    assert balance["USD"]["amount"] == 125.0


def test_dividend_on_delisted_stock(tmp: Path):
    """Dividend received after stock is fully sold (delisted/liquidated)."""
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    # Sell all shares
    add_transaction("2024-02-15", [
        {"ticker": "AAPL", "amount": -10.0},
        {"ticker": "USD", "amount": 1600.0},
    ])

    # Final liquidation dividend arrives after sell
    add_transaction("2024-04-15", [
        {"ticker": "USD", "amount": 50.00},
    ])

    balance = storage.load_balance()
    # AAPL fully sold — ticker removed from balance
    aapl_balance = balance.get("AAPL", {}).get("amount", 0.0)
    assert abs(aapl_balance) < 1e-9
    assert balance["USD"]["amount"] == 150.0


def test_dividend_does_not_affect_cagr(tmp: Path):
    """Dividends don't change CAGR (they're internal, not new investment)."""
    _reset()

    add_transaction("2024-01-01", [
        {"ticker": "USD", "amount": 1000.0},
    ], account_operation=True)

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    cagr_before = compute_cagr(2000.0, base_currency="USD", end="2024-07-01")

    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 50.00},
    ])

    cagr_after = compute_cagr(2000.0, base_currency="USD", end="2024-07-01")

    assert cagr_before == cagr_after


def test_multiple_different_dividends_same_day(tmp: Path):
    """Dividends from multiple stocks on the same day."""
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    add_transaction("2024-01-15", [
        {"ticker": "MSFT", "amount": 5.0},
        {"ticker": "USD", "amount": -1000.0},
    ])

    # Both pay dividends on the same day
    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 25.00},
    ])

    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 15.00},
    ])

    balance = storage.load_balance()
    assert balance["USD"]["amount"] == -2460.0


def test_dividend_zero_amount(tmp: Path):
    """Zero-amount dividend (should be allowed, no-op)."""
    _reset()

    add_transaction("2024-01-15", [
        {"ticker": "AAPL", "amount": 10.0},
        {"ticker": "USD", "amount": -1500.0},
    ])

    add_transaction("2024-03-15", [
        {"ticker": "USD", "amount": 0.0},
        ])

    balance = storage.load_balance()
    assert balance["USD"]["amount"] == -1500.0  # buy -1500, dividend +0

