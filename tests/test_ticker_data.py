"""Ticker data / FX / prices — pytest suite (split from the original monolithic runner)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import fixtures as fx
import sys


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


def test_get_fx_rate_stale_usd_uses_latest(tmp: Path):
    """Stale USDPLN must fall back to the latest cached rate, not collapse to 1.0."""
    import ticker_data

    fx.inject_fake_prices(tmp)  # USDPLN has no value for 2023-03-01
    cache: dict = {}
    rate = ticker_data.get_fx_rate("USD", "PLN", "2023-03-01", cache, 2023)
    assert rate > 3.0, f"USD→PLN collapsed to {rate} (should use latest ~3.98)"
    assert 3.8 < rate < 4.0, f"Expected latest ~3.88-3.98, got {rate}"


def test_get_fx_rate_stale_invertible(tmp: Path):
    """USD↔PLN must be near-inverses even on stale data (not 1.0 in any direction)."""
    import ticker_data

    fx.inject_fake_prices(tmp)
    cache: dict = {}
    up = ticker_data.get_fx_rate("USD", "PLN", "2023-03-01", cache, 2023)
    pu = ticker_data.get_fx_rate("PLN", "USD", "2023-03-01", cache, 2023)
    assert up > 3.0, f"USD→PLN fell back to {up}"
    assert pu > 0.2, f"PLN→USD fell back to {pu}"
    assert abs(up * pu - 1.0) < 0.02, f"rates not inverses: {up} * {pu}"


def test_get_fx_rate_gbp_triangulates(tmp: Path):
    """GBP→EUR and GBP→USD derive via PLN pairs instead of returning 1.0."""
    import ticker_data

    cache = {
        "GBPPLN": {2023: {"2023-01-03": 5.0}},
        "EURPLN": {2023: {"2023-01-03": 4.5}},
        "USDPLN": {2023: {"2023-01-03": 4.4}},
    }
    gbp_eur = ticker_data.get_fx_rate("GBP", "EUR", "2023-01-03", cache, 2023)
    assert abs(gbp_eur - (5.0 / 4.5)) < 0.01, f"GBP→EUR got {gbp_eur}"
    gbp_usd = ticker_data.get_fx_rate("GBP", "USD", "2023-01-03", cache, 2023)
    assert abs(gbp_usd - (5.0 / 4.4)) < 0.01, f"GBP→USD got {gbp_usd}"


def test_ticker_currency_detection(tmp: Path):
    """_ticker_currency maps suffixes to correct currencies."""
    from portfolio_core import _ticker_currency

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


def test_fx_rate_same_currency(tmp: Path):
    """get_fx_rate: same currency returns 1.0."""
    from ticker_data import get_fx_rate
    assert get_fx_rate("PLN", "PLN", "2023-01-03", {}, 2023) == 1.0


def test_fx_rate_direct_pair(tmp: Path):
    """get_fx_rate: direct pair (USDPLN) returns cached price."""
    from ticker_data import get_fx_rate
    cache = {"USDPLN": {2023: {"2023-01-03": 4.38}}}
    assert get_fx_rate("USD", "PLN", "2023-01-03", cache, 2023) == 4.38


def test_fx_rate_reverse_pair(tmp: Path):
    """get_fx_rate: reverse pair returns 1/rate."""
    from ticker_data import get_fx_rate
    cache = {"USDPLN": {2023: {"2023-01-03": 4.0}}}
    rate = get_fx_rate("PLN", "USD", "2023-01-03", cache, 2023)
    assert abs(rate - 0.25) < 0.001


def test_fx_rate_eur_pln_via_triangulation(tmp: Path):
    """get_fx_rate: EUR→PLN triangulated via EURUSD * USDPLN."""
    from ticker_data import get_fx_rate
    cache = {
        "EURUSD": {2023: {"2023-01-03": 1.07}},
        "USDPLN": {2023: {"2023-01-03": 4.0}},
    }
    rate = get_fx_rate("EUR", "PLN", "2023-01-03", cache, 2023)
    assert abs(rate - 4.28) < 0.01


def test_fx_rate_usd_pln_direct(tmp: Path):
    """get_fx_rate: USD→PLN via direct USDPLN pair."""
    from ticker_data import get_fx_rate
    cache = {"USDPLN": {2023: {"2023-01-03": 4.35}}}
    rate = get_fx_rate("USD", "PLN", "2023-01-03", cache, 2023)
    assert abs(rate - 4.35) < 0.001


def test_fx_rate_pln_to_usd(tmp: Path):
    """get_fx_rate: PLN→USD via 1/USDPLN."""
    from ticker_data import get_fx_rate
    cache = {"USDPLN": {2023: {"2023-01-03": 4.0}}}
    rate = get_fx_rate("PLN", "USD", "2023-01-03", cache, 2023)
    assert abs(rate - 0.25) < 0.001


def test_fx_rate_fallback_1(tmp: Path):
    """get_fx_rate: no data returns 1.0 as last resort."""
    from ticker_data import get_fx_rate
    rate = get_fx_rate("USD", "PLN", "2023-01-03", {}, 2023)
    assert rate == 1.0


def test_fx_rate_non_pln_cross_via_pln(tmp: Path):
    """get_fx_rate: EUR→USD triangulated via EURPLN / USDPLN."""
    from ticker_data import get_fx_rate
    cache = {
        "EURPLN": {2023: {"2023-01-03": 4.68}},
        "USDPLN": {2023: {"2023-01-03": 4.0}},
    }
    rate = get_fx_rate("EUR", "USD", "2023-01-03", cache, 2023)
    assert abs(rate - 1.17) < 0.01


def test_latest_price_cash(tmp: Path):
    """_latest_price: cash ticker returns 1.0."""
    from ticker_data import _latest_price
    assert _latest_price("USD", {}, 2023) == 1.0


def test_latest_price_from_cache(tmp: Path):
    """_latest_price: returns latest price from loaded cache."""
    from ticker_data import _latest_price
    cache = {"AAPL": {2023: {"2023-01-03": 125.0, "2023-01-09": 130.0}}}
    assert _latest_price("AAPL", cache, 2023) == 130.0


def test_latest_price_empty_cache(tmp: Path):
    """_latest_price: missing ticker returns None."""
    from ticker_data import _latest_price
    assert _latest_price("AAPL", {}, 2023) is None


def test_latest_price_empty_slab(tmp: Path):
    """_latest_price: empty slab returns None."""
    from ticker_data import _latest_price
    cache = {"AAPL": {2023: {}}}
    assert _latest_price("AAPL", cache, 2023) is None


def test_latest_price_multi_year(tmp: Path):
    """_latest_price: scans newest year first."""
    from ticker_data import _latest_price
    cache = {
        "AAPL": {
            2022: {"2022-12-29": 120.0},
            2023: {"2023-01-03": 125.0},
        }
    }
    assert _latest_price("AAPL", cache, 2023) == 125.0
