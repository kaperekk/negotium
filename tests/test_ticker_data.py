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
    # XTB-translated suffixes (Yahoo exchange codes)
    assert _ticker_currency("NOKIA.HE") == "EUR"   # Helsinki
    assert _ticker_currency("HTO.AT") == "EUR"     # Athens
    assert _ticker_currency("VOLV-B.ST") == "SEK"
    assert _ticker_currency("EQNR.OL") == "NOK"
    assert _ticker_currency("NOVO-B.CO") == "DKK"
    assert _ticker_currency("CEZ.PR") == "CZK"
    assert _ticker_currency("OTP.BD") == "HUF"
    assert _ticker_currency("THYAO.IS") == "TRY"

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


def test_ensure_pins_empty_year_once(tmp: Path):
    """A no-data year (pre-IPO ticker, e.g. SPCX before its 2026 IPO) is pinned
    to disk on the first attempt and never re-requested; a failed download
    (None) stays unpinned so it is retried on a later refresh."""
    import storage
    import ticker_data

    # Pre-seed names so ensure() never touches the network for metadata.
    names = storage.load_ticker_names()
    names["PREIPO"] = "Pre IPO Test"
    names["NETFAIL"] = "Net Fail Test"
    storage.save_ticker_names(names)

    calls: list[tuple[str, int]] = []
    orig = ticker_data._download_year

    def _fake_download(ticker: str, year: int):
        calls.append((ticker, year))
        return {}  # Yahoo has no data for this year

    ticker_data._download_year = _fake_download
    try:
        start, end = date(2023, 1, 1), date(2023, 6, 30)
        ticker_data.ensure("PREIPO", start, end, force_refresh_current_year=False)
        assert calls == [("PREIPO", 2023)], calls
        assert storage.has_price_year("PREIPO", 2023), "empty year must be pinned"
        assert storage.load_price_year("PREIPO", 2023) == {}

        # Second pass: year already pinned -> no new download attempt.
        ticker_data.ensure("PREIPO", start, end, force_refresh_current_year=False)
        assert calls == [("PREIPO", 2023)], calls
    finally:
        ticker_data._download_year = orig

    # Failed download (None) must NOT be pinned -> retried every time.
    ticker_data._download_year = lambda t, y: None
    try:
        for _ in range(2):
            ticker_data.ensure("NETFAIL", start, end, force_refresh_current_year=False)
            assert not storage.has_price_year("NETFAIL", 2023)
    finally:
        ticker_data._download_year = orig


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


# -- get_ticker_currency: Yahoo-backed detection with suffix fallback ----------

def test_ticker_currency_uses_yahoo_when_it_answers(tmp: Path, monkeypatch):
    """get_ticker_currency prefers Yahoo's reported currency over the suffix map.

    USD-quoted LSE lines (CNDX.L, DTLA.L) must resolve to USD — the .L suffix
    would wrongly guess GBP and misvalue them by the GBP/USD ratio.
    """
    import ticker_data

    class _FakeFastInfo:
        currency = "USD"

    class _FakeTicker:
        def __init__(self, symbol):
            self.fast_info = _FakeFastInfo()

    monkeypatch.setattr(ticker_data.yf, "Ticker", _FakeTicker)
    ticker_data.invalidate_currency_cache()
    try:
        assert ticker_data.get_ticker_currency("CNDX.L") == "USD"
        assert ticker_data.get_ticker_currency("DTLA.L") == "USD"
    finally:
        ticker_data.invalidate_currency_cache()


def test_ticker_currency_falls_back_to_suffix_map(tmp: Path, monkeypatch):
    """get_ticker_currency falls back to the suffix map when Yahoo fails.

    Dead/invalid Yahoo symbols must not silently become USD when the exchange
    suffix determines the currency (.ST→SEK, .L→GBP, .WA→PLN).
    """
    import ticker_data

    class _BrokenTicker:
        def __init__(self, symbol):
            raise RuntimeError("symbol not found")

    monkeypatch.setattr(ticker_data.yf, "Ticker", _BrokenTicker)
    ticker_data.invalidate_currency_cache()
    try:
        assert ticker_data.get_ticker_currency("ERICB.ST") == "SEK"
        assert ticker_data.get_ticker_currency("4GLD.L") == "GBP"
        assert ticker_data.get_ticker_currency("SNT.WA") == "PLN"
    finally:
        ticker_data.invalidate_currency_cache()


def test_ticker_currency_unknown_suffix_defaults_to_usd(tmp: Path, monkeypatch):
    """get_ticker_currency: unknown suffix and no Yahoo answer → USD."""
    import ticker_data

    class _BrokenTicker:
        def __init__(self, symbol):
            raise RuntimeError("symbol not found")

    monkeypatch.setattr(ticker_data.yf, "Ticker", _BrokenTicker)
    ticker_data.invalidate_currency_cache()
    try:
        assert ticker_data.get_ticker_currency("AAPL") == "USD"
    finally:
        ticker_data.invalidate_currency_cache()


def test_ticker_currency_gbp_pence_normalised(tmp: Path, monkeypatch):
    """get_ticker_currency: Yahoo's GBp (London pence) is normalised to GBP."""
    import ticker_data

    class _FakeFastInfo:
        currency = "GBp"

    class _FakeTicker:
        def __init__(self, symbol):
            self.fast_info = _FakeFastInfo()

    monkeypatch.setattr(ticker_data.yf, "Ticker", _FakeTicker)
    ticker_data.invalidate_currency_cache()
    try:
        assert ticker_data.get_ticker_currency("HSBA.L") == "GBP"
    finally:
        ticker_data.invalidate_currency_cache()


def test_ticker_currency_cached_after_first_lookup(tmp: Path, monkeypatch):
    """get_ticker_currency caches the answer — Yahoo is consulted once."""
    import ticker_data

    calls: list[str] = []

    class _FakeFastInfo:
        currency = "EUR"

    class _FakeTicker:
        def __init__(self, symbol):
            calls.append(symbol)
            self.fast_info = _FakeFastInfo()

    monkeypatch.setattr(ticker_data.yf, "Ticker", _FakeTicker)
    ticker_data.invalidate_currency_cache()
    try:
        assert ticker_data.get_ticker_currency("IUSQ.DE") == "EUR"
        assert ticker_data.get_ticker_currency("IUSQ.DE") == "EUR"
        assert calls == ["IUSQ.DE"]
    finally:
        ticker_data.invalidate_currency_cache()


# -- FX triangulation for currencies whose {CCY}PLN=X pair has no history ------

def test_fx_yahoo_maps_no_history_currencies_via_usd():
    """Currencies without historical {CCY}PLN=X data map to {CCY}USD=X pairs.

    Yahoo's chart API returns zero points for e.g. SEKPLN=X but full history
    for SEKUSD=X — the FX_YAHOO map must use the USD pairs for those currencies
    so get_fx_rate can triangulate.
    """
    from ticker_data import FX_YAHOO

    for ccy in ("SEK", "NOK", "CAD", "KRW", "CNY", "BRL", "CZK", "TRY", "MXN", "HUF"):
        assert f"{ccy}USD" in FX_YAHOO, f"{ccy}USD missing from FX_YAHOO"
        assert f"{ccy}PLN" not in FX_YAHOO, f"{ccy}PLN should not be a direct pair"
    # Direct pairs that DO have history stay direct.
    for ccy in ("EUR", "GBP", "AUD", "HKD", "JPY", "SGD", "CHF", "DKK"):
        assert f"{ccy}PLN" in FX_YAHOO, f"{ccy}PLN missing from FX_YAHOO"


def test_fx_rate_sek_pln_via_usd_triangulation():
    """get_fx_rate: SEK→PLN triangulated via SEKUSD × USDPLN.

    Yahoo serves no historical SEKPLN=X data, so the conversion must go
    through USD (0.0965 USD per SEK × 4.0 PLN per USD = 0.386).
    """
    from ticker_data import get_fx_rate
    cache = {
        "SEKUSD": {2024: {"2024-12-27": 0.0965}},
        "USDPLN": {2024: {"2024-12-27": 4.0}},
    }
    rate = get_fx_rate("SEK", "PLN", "2024-12-27", cache, 2024)
    assert abs(rate - 0.386) < 0.001, f"SEK→PLN got {rate}"

    # Reverse direction: PLN→SEK = 1 / (SEKUSD × USDPLN)
    reverse = get_fx_rate("PLN", "SEK", "2024-12-27", cache, 2024)
    assert abs(reverse - 1 / 0.386) < 0.01, f"PLN→SEK got {reverse}"


def test_fx_rate_nok_pln_via_usd_triangulation():
    """get_fx_rate: NOK→PLN triangulated via NOKUSD × USDPLN."""
    from ticker_data import get_fx_rate
    cache = {
        "NOKUSD": {2025: {"2025-06-02": 0.10}},
        "USDPLN": {2025: {"2025-06-02": 3.7}},
    }
    rate = get_fx_rate("NOK", "PLN", "2025-06-02", cache, 2025)
    assert abs(rate - 0.37) < 0.001, f"NOK→PLN got {rate}"


# -- Regression: auto_adjust must be False for raw prices ----------------------

def test_download_year_uses_raw_prices_not_adjusted(tmp: Path, monkeypatch):
    """_download_year must call yf.download with auto_adjust=False.

    Regression guard: a previous bug used auto_adjust=True which returns
    dividend-adjusted closes. Those scale down historical prices and break
    cost-basis, TWR, and IRR calculations that must match broker cash flows.
    """
    import ticker_data
    import pandas as pd

    download_calls: list[dict] = []

    def _fake_download(symbol, start, end, progress, auto_adjust, **kwargs):
        download_calls.append({"symbol": symbol, "auto_adjust": auto_adjust})
        idx = pd.date_range(start, end, freq="B")
        df = pd.DataFrame({"Close": [100.0] * len(idx)}, index=idx)
        return df

    monkeypatch.setattr(ticker_data.yf, "download", _fake_download)
    monkeypatch.setattr(ticker_data.yf.Ticker, "fast_info", type("FI", (), {"currency": "USD"})())

    ticker_data._download_year("AAPL", 2023)

    assert len(download_calls) == 1, f"Expected 1 download call, got {len(download_calls)}"
    assert download_calls[0]["auto_adjust"] is False, (
        f"_download_year must use auto_adjust=False (raw prices), "
        f"got auto_adjust={download_calls[0]['auto_adjust']}"
    )


def test_ensure_batch_uses_raw_prices_not_adjusted(tmp: Path, monkeypatch):
    """ensure_batch must call yf.download with auto_adjust=False.

    Regression guard: batch downloads must return raw closes to match
    broker cash flows for portfolio valuation and performance metrics.
    """
    import ticker_data
    import storage
    import pandas as pd

    download_calls: list[dict] = []

    def _fake_download(symbols, start, end, progress, auto_adjust, **kwargs):
        download_calls.append({"symbols": symbols, "auto_adjust": auto_adjust})
        idx = pd.date_range(start, end, freq="B")
        if isinstance(symbols, list) and len(symbols) > 1:
            cols = pd.MultiIndex.from_product([["Close"], symbols])
            data = {col: [100.0] * len(idx) for col in cols}
            df = pd.DataFrame(data, index=idx)
            df.columns = cols
        else:
            sym = symbols[0] if isinstance(symbols, list) else symbols
            df = pd.DataFrame({"Close": [100.0] * len(idx)}, index=idx)
        return df

    monkeypatch.setattr(ticker_data.yf, "download", _fake_download)
    monkeypatch.setattr(ticker_data.yf.Ticker, "fast_info", type("FI", (), {"currency": "USD"})())

    names = storage.load_ticker_names()
    names["TEST1"] = "Test 1"
    names["TEST2"] = "Test 2"
    storage.save_ticker_names(names)

    ticker_data.ensure_batch(
        ["TEST1", "TEST2"],
        start_date=date(2023, 1, 1),
        end_date=date(2023, 1, 31),
        force_refresh_current_year=False,
    )

    assert len(download_calls) >= 1, "Expected at least 1 batch download call"
    assert download_calls[0]["auto_adjust"] is False, (
        f"ensure_batch must use auto_adjust=False (raw prices), "
        f"got auto_adjust={download_calls[0]['auto_adjust']}"
    )


def test_ensure_adjusted_batch_uses_adjusted_prices(tmp: Path, monkeypatch):
    """ensure_batch(adjusted=True) must call yf.download with auto_adjust=True.

    The adjusted cache is ONLY for benchmark what-if overlays so the
    comparison includes dividends. This is the one place adjusted is correct.
    """
    import ticker_data
    import storage
    import pandas as pd

    download_calls: list[dict] = []

    def _fake_download(symbols, start, end, progress, auto_adjust, **kwargs):
        download_calls.append({"symbols": symbols, "auto_adjust": auto_adjust})
        idx = pd.date_range(start, end, freq="B")
        if isinstance(symbols, list) and len(symbols) > 1:
            cols = pd.MultiIndex.from_product([["Close"], symbols])
            data = {col: [100.0] * len(idx) for col in cols}
            df = pd.DataFrame(data, index=idx)
            df.columns = cols
        else:
            df = pd.DataFrame({"Close": [100.0] * len(idx)}, index=idx)
        return df

    monkeypatch.setattr(ticker_data.yf, "download", _fake_download)
    monkeypatch.setattr(ticker_data.yf.Ticker, "fast_info", type("FI", (), {"currency": "USD"})())

    names = storage.load_ticker_names()
    names["BM1"] = "Benchmark 1"
    storage.save_ticker_names(names)

    ticker_data.ensure_batch(
        ["BM1"],
        start_date=date(2023, 1, 1),
        end_date=date(2023, 1, 31),
        force_refresh_current_year=False,
        adjusted=True,
    )

    assert len(download_calls) >= 1, "Expected at least 1 adjusted download call"
    assert download_calls[0]["auto_adjust"] is True, (
        f"ensure_batch(adjusted=True) must use auto_adjust=True (for benchmarks), "
        f"got auto_adjust={download_calls[0]['auto_adjust']}"
    )


