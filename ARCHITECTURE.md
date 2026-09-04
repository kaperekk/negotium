# Negotium — Investment Tracker — Architecture

A local Python application that tracks multi-currency stock portfolios over
time. No server, no database daemon, no background process. Everything lives
in plain files and starts from cold in under a second (warm cache).

Part of the Negotium docs: [README](README.md) · [USAGE](USAGE.md) · [IMPORTS](IMPORTS.md) · [CONFIG](CONFIG.md)

---

## Table of contents

1. [Module map](#1-module-map)
2. [File layout on disk](#2-file-layout-on-disk)
3. [File formats](#3-file-formats)
4. [Data flow — startup](#4-data-flow--startup)
5. [Data flow — add a transaction](#5-data-flow--add-a-transaction)
6. [Data flow — build portfolio](#6-data-flow--build-portfolio)
7. [Multi-currency logic](#7-multi-currency-logic)
8. [Caching strategy](#8-caching-strategy)
9. [Performance decisions](#9-performance-decisions)
10. [Dependency map](#10-dependency-map)
11. [Benchmark numbers](#11-benchmark-numbers)

---

## 1. Module map

```
src/
├── app.py             Streamlit entry point. Wires runtime, sidebar, dashboard.
│                      Owns no logic of its own.
├── config.py          Read / write data/config.json (single global config).
│                      No logic beyond that. Theme helpers.
├── storage.py         All file I/O. The only module that touches the
│                      filesystem (except ticker_data, which also writes the
│                      price cache). Multi-project paths, JSONL helpers,
│                      price cache, registry, balance, benchmarks, dividends.
├── ledger_core.py     Transaction ledger: add/update/delete, chronological
│                      order enforcement, balance + avg-price rebuild,
│                      CAGR, IRR, holdings-at-date. Import dedup counts.
├── currencies.py      Single source of truth: supported currencies, exchange
│                      suffixes, triangulation rules, display symbols.
├── portfolio_core.py  Build the portfolio value time-series. The core engine.
├── ticker_data.py     Yahoo Finance: batched price download, per-year cache,
│                      FX rates, dividends, earnings dates, ticker names and
│                      metadata, all-time-highs.
├── ticker_translate.py  Rule-based ticker symbol translation.
├── isin_resolve.py    ISIN → ticker resolution from config mappings.
├── bossa_import.py    BOSSA "Historia finansowa" CSV importer.
├── xtb_import.py      XTB Excel (Cash Operations sheet) importer.
├── manual_import.py   Custom JSON importer + file validation.
├── fixtures.py        Test helpers: temp roots, fake price data.
└── ui/                Streamlit view layer — one module per concern:
    ├── runtime.py         Bootstrap: config, storage, theme, locale.
    ├── sidebar.py         Projects, currency, date range, settings,
    │                      add-transaction form, import expander, refresh.
    ├── dashboard.py       Page assembly: metrics, chart, tables, sections.
    ├── portfolio_chart.py Plotly value chart + benchmarks + invested line.
    ├── holdings.py        Holdings table.
    ├── trade_history.py   Per-ticker trade-history dialog.
    ├── allocation.py      Allocation breakdown donuts.
    ├── drawdown.py        Drawdown statistics + underwater chart.
    ├── metrics.py         Metric cards and P&L toggles.
    ├── watchlist.py       Bottom-of-page watchlist (parallel quote warm-up).
    ├── colors.py          Single source of truth: theme palettes + the
    │                      benchmark ETF set.
    ├── style_base.py      Base CSS and runtime style overrides.
    ├── style_components.py  Component-level CSS and HTML fragments.
    ├── styles.py          Compatibility layer for the style modules.
    ├── bootstrap.py       App bootstrap helpers (import logging, project
    │                      context).
    └── helpers.py         Formatting and file-detection helpers.
```

No module except `storage` and `ticker_data` reads or writes files directly.
`app.py` does not touch the filesystem at all — it only calls other modules.
The domain core (`ledger_core`, `portfolio_core`) is kept separate from the
view layer (`ui/`); `ui/styles.py` exists as a stable import name over the
split style implementations. Currency definitions live only in
`currencies.py` (re-exported by `storage` for older call sites).

---

## 2. File layout on disk

```
negotium/                          ← project root
├── start.sh                       launcher
├── data/
│   ├── config.json                global settings (shared by all projects)
│   ├── projects.json              project registry: created_at, last_refresh, watchlist
│   ├── prices/                    shared price cache — stocks and FX pairs
│   │   ├── AAPL/
│   │   │   └── 2024.json          {YYYY-MM-DD: close_price} per trading day
│   │   └── USDPLN/
│   │       └── 2024.json
│   ├── ticker_names.json          {ticker: company short name}
│   ├── ticker_meta.json           {ticker: {sector, country, asset_class}}
│   ├── dividends.json             {ticker: {YYYY-MM-DD: dividend_per_share}}
│   ├── earnings.json              {ticker: next_earnings_date}
│   └── {PROJECT}/                 one directory per project
│       ├── transactions.jsonl     append-only ledger (the source of truth)
│       ├── balance.json           derived holdings snapshot
│       ├── portfolio.jsonl        derived daily snapshots
│       ├── benchmarks_{CCY}.json  derived benchmark series per display currency
│       └── imports/
│           ├── xtb/               uploaded XTB .xlsx files (kept for replay)
│           ├── bossa/             uploaded BOSSA .csv files
│           └── custom/            uploaded custom .json files
├── src/                           application code (see module map)
└── tests/
    └── conftest.py                shared fixtures (isolated temp dirs)
    ├── test_ledger.py
    ├── test_portfolio.py
    ├── test_storage.py
    ├── test_ticker_data.py
    └── … (145 tests, pytest)
```

All files are human-readable JSON / JSONL — you can open any of them in a text
editor. Deleting anything under `data/prices/` or the derived files just means
they are rebuilt / re-downloaded. `transactions.jsonl` is the only file that
is *not* reproducible: it is your data.

---

## 3. File formats

### config.json — global settings

```json
{
  "default_currency": "PLN",
  "theme": "dark",
  "ticker_rules": ["*.PL=*.WA", ".US="],
  "isin_tickers": ["IE00B4L5Y983=IWDA.AS"]
}
```

Four keys, documented in [CONFIG.md](CONFIG.md#global-config--dataconfigjson).
Loaded by `config.load()` with an in-memory cache; missing keys are filled
from defaults.

### projects.json — project registry

```json
{
  "XTB": {
    "created_at": "2026-08-24T23:22:43.053550",
    "last_refresh": "2026-09-02",
    "watchlist": ["AMZN", "TSLA", "CRI.WA"]
  }
}
```

One key per project. `last_refresh` drives the 24 h auto-refresh check;
`watchlist` stores the per-project watchlist symbols.

### transactions.jsonl — the ledger, one line per calendar date

```jsonl
{"date":"2023-01-03","entries":[{"ticker":"AAPL","amount":10.0},{"ticker":"USD","amount":-1250.0}]}
{"date":"2023-06-01","entries":[{"ticker":"USD","amount":-5000.0},{"ticker":"PLN","amount":19850.0}]}
```

- One line per calendar date; multiple operations on the same day share a line.
- The file must stay in ascending date order. `ledger_core.add_transaction()`
  enforces this: append for new latest dates, merge into the last line for a
  same-date addition, and full-file rewrite with correct positioning for
  past-date insertions.
- `ticker` is a stock symbol (`AAPL`, `CDR.WA`, `SAP.DE`) or a cash currency
  (`USD`, `EUR`, `PLN`).
- Negative `amount` = money or shares leaving (sell, cash out, FX leg out).
- Optional per-entry `"account_operation": true` marks deposits/withdrawals
  that count toward invested capital.

### balance.json — current holdings (derived)

```json
{
  "AAPL": {"amount": 10.0, "avg_price": 171.02},
  "USD":  {"amount": 3250.0, "avg_price": 0.0}
}
```

A derived file, rebuilt by replaying `transactions.jsonl` whenever transactions
change (rebuilds can start from a given date instead of replaying everything).
`avg_price` accumulates the average purchase price for P&L display. Entries
whose `|amount|` falls below `1e-9` are pruned on save. Its only purpose is to
avoid replaying the whole ledger every time the UI needs current holdings.

---

### data/prices/{TICKER}/{YEAR}.json — shared price cache

```json
{
  "2024-01-02": 185.2,
  "2024-01-03": 184.4,
  "2024-01-04": 182.9
}
```

- Only trading days appear (no weekends, no holidays), stored as floats.
- One file per ticker per calendar year. Stock tickers and FX pairs use the
  same mechanism.
- Historical years are written once and never re-fetched; the current year is
  re-downloaded on every startup / refresh so the latest closes are picked up.
- FX pairs are stored under their internal names (`USDPLN`, `EURPLN`, …) —
  see section 7 for how they map to Yahoo Finance symbols.

### portfolio.jsonl — computed daily snapshots (derived)

```json
{
  "date": "2024-01-03",
  "assets": [
    {"ticker": "AAPL", "amount": 10.0, "price": 185.2, "currency": "USD",
     "value_native": 1852.0, "value_base": 7437.08},
    {"ticker": "USD", "amount": 3250.0, "price": 1.0, "currency": "USD",
     "value_native": 3250.0, "value_base": 13093.75}
  ],
  "total_value": 20530.83,
  "invested": 25000.0,
  "base_currency": "PLN"
}
```

- One line per day. `value_native` = amount × price in the asset's own
  currency; `value_base` = `value_native` × FX rate → base currency.
- `total_value` = sum of all `value_base` entries.
- `invested` = cumulative net deposits in base currency (the reference line on
  the chart). The invested rule:
  - entries marked `account_operation` **always** count (deposits and withdrawals),
  - unmarked pure-cash transactions also count,
  - stock buys/sells **never** count — even though their cash leg moves money.
- `base_currency` tags the snapshot so snapshots for different display
  currencies (PLN / EUR / USD) are stored and retrieved independently.

### benchmarks_{CCY}.json — computed benchmark series (derived, per project)

```json
[
  {"date": "2024-01-03", "SXRV.DE": 100.0, "I500.DE": 100.0, "...": 100.0},
  {"date": "2024-01-04", "SXRV.DE": 100.9, "I500.DE": 100.4, "...": 100.1}
]
```

Normalised growth series (first day = 100) for the benchmark ETF set defined
in `ui/colors.py`: SXRV.DE (NASDAQ 100), I500.DE (S&P 500), VWCE.DE (FTSE
All-World), IS3N.DE (Emerging Markets), BTCE.DE (Bitcoin), 4GLD.DE (Gold).
One file per project per display currency.

### Shared metadata caches

| File | Schema | Filled by |
|---|---|---|
| `ticker_names.json` | `{ticker: "Apple Inc."}` | `get_ticker_name()` on first sight of a ticker |
| `ticker_meta.json` | `{ticker: {sector, country, asset_class}}` | `get_ticker_meta()` — used by allocation donuts |
| `dividends.json` | `{ticker: {"2024-02-09": 0.45, …}}` | `get_dividends()` — used by trade-history dialog |
| `earnings.json` | `{ticker: "2026-10-28"}` | `get_next_earnings()` (24 h TTL) — used by watchlist |

All of them are keyed by ticker and shared across projects; deleting any of
them just triggers a re-fetch from Yahoo Finance.

---

## 4. Data flow — startup

```
start.sh
│
├─ 1. pytest tests/                       (skipped with --skip-tests)
│
└─ 2. streamlit run src/app.py
     │
     ├─ ui.runtime.init_runtime()         config + storage + theme + locale
     │
     ├─ ui.sidebar.render_sidebar()
     │    ├─ project select / create      storage.set_current_project()
     │    ├─ auto-refresh check           last_refresh ≥ 24 h → refresh path
     │    ├─ currency + date range pickers
     │    ├─ ⚙️ settings                  theme, ticker rules, ISIN mappings
     │    ├─ ➕ add transaction form
     │    └─ 📥 import expander           upload + import statement files
     │
     ├─ ledger_core.first_transaction_date()
     │
     └─ ui.dashboard.render_dashboard()
          ├─ ledger_core.get_all_tickers()    scan ledger → tickers + FX pairs
          ├─ ticker_data.ensure_batch()       ONE batched Yahoo download for
          │                                   every missing (ticker, year) slab
          ├─ portfolio.build_portfolio()      resume from last snapshot (§6)
          ├─ benchmark series compute / cache
          └─ render: metrics, chart, holdings, allocation, drawdown, watchlist
```

On a warm weekly startup (all history cached, only current-year refresh plus a
few new days to compute) this is tens of milliseconds of Python compute plus
whatever Yahoo Finance takes to answer for the current-year batch.

---

## 5. Data flow — add a transaction

```
UI form submit (or importer)
│
└─ ledger_core.add_transaction(date, entries)
     │
     ├─ normalise: ticker rules applied, amounts rounded, account_operation set
     │
     ├─ storage.read_jsonl(transactions.jsonl)   load full ledger
     │
     ├─ Three-way branch on date position:
     │
     │   A. date > last line date
     │      └─ storage.append_jsonl()            O(1) — just append
     │         update running balance + avg prices, storage.save_balance()
     │
     │   B. date == last line date
     │      └─ merge entries into last record
     │         storage.write_jsonl()             rewrite whole file
     │         _rebuild_balance(from_date)       replay from that date
     │
     │   C. date < last line date  (past insertion)
     │      └─ scan for insertion point
     │         storage.write_jsonl()             rewrite whole file
     │         _rebuild_balance(from_date)       replay from that date
     │
     └─ storage.invalidate_portfolio_from(date)
          └─ stream portfolio.jsonl, keep lines where date < insertion date
             write to .tmp, atomically rename over original
             (never loads the whole file into RAM just to trim it)
```

After `add_transaction` returns, the UI drops the session-state cache keys for
the affected currency/benchmarks and re-renders. The next render rebuilds only
from the invalidated date onward.

---

## 6. Data flow — build portfolio

The most algorithmically significant function. Replaying all transactions for
every day would be O(days × transactions); a single forward pass gives
O(days + transactions).

```
portfolio_core.build_portfolio(start, end, base_ccy, precision)
│
├─ Load existing snapshots from portfolio.jsonl, filtered to base_ccy
│
├─ Restore running state from the last cached snapshot:
│    balance = {ticker: amount}          (from last snapshot's assets)
│    cumulative_contrib = last snapshot's invested
│    resume_from = last cached date + 1 day
│
├─ Load pending transactions (date >= resume_from, date <= today)
│
├─ For each day in [resume_from .. end]:          ← FORWARD PASS
│    │
│    ├─ Apply all pending tx whose date <= today   (tx_idx pointer only
│    │   update the balance dict in place           moves forward, never resets)
│    │   invested rule applied per entry (§3, portfolio.jsonl)
│    │
│    ├─ For each ticker in balance:
│    │    ├─ cash (USD/EUR/PLN): value_base = amount × fx_rate(ccy → base, day)
│    │    └─ stock: price      = _PriceCache.get(ticker, day)
│    │              value_base = amount × price × fx_rate(ticker_ccy → base, day)
│    │
│    └─ Append snapshot to new_snapshots
│
├─ _merge_snapshots(existing, new_snapshots)
│    deduplicate by date (new wins), sort by date
│
└─ storage.save_portfolio(merged) → portfolio.jsonl
```

`snapshots_to_series()` then extracts the flat date / value / invested lists
the chart and drawdown code consume.

### _PriceCache — RAM layout

```
_data: {
  "AAPL":   { 2023: {"2023-01-03": 125.07, ...},   ← loaded on first access
              2024: {"2024-01-02": 185.20, ...} },  ← loaded when year changes
  "USDPLN": { 2023: {"2023-01-03": 4.38, ...}, ... },
  ...
}
```

Each `(ticker, year)` slab is loaded from disk exactly once per
`build_portfolio` call. A 5-year, 10-ticker portfolio occupies roughly
`10 × 5 × 260 × ~20 B ≈ 260 KB` in RAM — negligible on any machine.

---

## 7. Multi-currency logic

### Ticker currency detection

A stock's price is always quoted in a specific currency. The app infers it
from the ticker suffix (`storage.CURRENCY_SUFFIXES`) rather than storing it
explicitly:

```
*.WA          → PLN   (Warsaw Stock Exchange / GPW)
*.DE .F .PA   → EUR   (Xetra, Frankfurt, Euronext Paris)
*.MI .AS .BR  → EUR   (Milan, Amsterdam, Brussels)
*.LS .MC .VI .IR → EUR (Lisbon, Madrid, Vienna, Irish)
*.HE .AT      → EUR   (Helsinki, Athens)
*.L           → GBP   (London)
*.ST → SEK   *.OL → NOK   *.CO → DKK
*.PR → CZK   *.BD → HUF   *.IS → TRY
*.MX          → MXN   *.TO → CAD   *.AX → AUD   *.HK → HKD
*.T           → JPY   *.KS → KRW   *.SS/.SZ → CNY
*.SG .SI      → SGD   *.SW → CHF   *.SA → BRL
(none)        → USD   (default: NYSE / NASDAQ; unknown suffix → USD + warning)
```

The full table lives in [CONFIG.md](CONFIG.md#supported-currencies--exchange-suffixes).

### FX rate universe

FX pairs are generated from the suffix table, so every supported currency
automatically gets a pair:

```
FX_YAHOO = {f"{ccy}PLN": f"{ccy}PLN=X"}   for every ccy except PLN and MXN
FX_YAHOO["USDPLN"] = "USDPLN=X"
FX_YAHOO["EURUSD"] = "EURUSD=X"
FX_YAHOO["MXNUSD"] = "MXNUSD=X"           (MXN triangulates via USD)
FX_YAHOO["HUFUSD"] = "HUFUSD=X"           (HUF triangulates via USD)
```

FX rates are fetched and cached exactly like stock prices — per-year JSON
files under `data/prices/USDPLN/`, `data/prices/EURPLN/`, etc.

### FX lookup order (`ticker_data.get_fx_rate`)

```
1. Direct pair exists in FX_YAHOO?    → use it
2. Reverse pair exists?               → 1 / reverse_rate
3. Triangulate via USD:
     EUR→PLN = EURUSD × USDPLN
     PLN→EUR = 1 / (EURUSD × USDPLN)
     PLN→USD = 1 / USDPLN
4. Fallback: 1.0  (same currency, or rate unavailable)
```

For each asset on each day: `value_base = amount × price_native × fx(native → base)`.

### Weekend and holiday handling

Markets don't trade on weekends or public holidays. When a price for date `D`
is missing from the cache, `get_price` walks backward up to 5 calendar days
until it finds a valid close — covering weekends (2 days) and long holiday
weekends (up to 4 days in most markets). FX pairs use the same mechanism,
since forex markets also close on weekends.

### Moving money between currencies

A currency exchange (e.g. converting USD to PLN) is recorded as two entries on
the same transaction line:

```jsonl
{"date":"2024-03-15","entries":[{"ticker":"USD","amount":-5000.0},{"ticker":"PLN","amount":19850.0}]}
```

The USD balance drops by 5000, the PLN balance rises by 19850; the actual
exchange rate at the moment of transfer is implicitly captured in the ratio.
Both cash positions are tracked independently and converted to the display
currency using the market FX rate for each day, so historical P&L correctly
reflects the rate at the time of the transfer.

---

## 8. Caching strategy

Six distinct caches, each with different scope and lifetime:

| Cache | Location | Lifetime | Keyed by |
|---|---|---|---|
| Historical prices | `data/prices/{TICKER}/{YEAR}.json` | Permanent — elapsed years never re-fetched | ticker, year |
| Current-year prices | same files, current year | Re-fetched on each startup / Refresh | ticker |
| Portfolio snapshots | `{PROJECT}/portfolio.jsonl` | Until a transaction changes the past | base_currency, date |
| Benchmark series | `{PROJECT}/benchmarks_{CCY}.json` + session key | Until snapshots change or force refresh | project, base_ccy, snapshot count |
| Ticker metadata | `ticker_names/meta.json`, `dividends.json`, `earnings.json` | Persistent; earnings/ATH re-checked on TTL (24 h) | ticker |
| Streamlit session | `st.session_state["snapshots_{ccy}_{precision}"]` | Until tab closes or a transaction is added | base_ccy, precision |

### Cache invalidation on transaction insert

When a transaction is added for date `D`:

1. `storage.invalidate_portfolio_from(D)` streams through `portfolio.jsonl`,
   keeps only lines with `date < D`, writes atomically via `.tmp` rename.
2. The UI pops `st.session_state["snapshots_{base_ccy}_…"]` and the
   `benchmarks_…` keys.
3. The next render calls `build_portfolio()`, which resumes from the
   invalidated date.

Historical year files (`2022.json`, `2023.json`) are **never deleted or
invalidated** — Yahoo Finance does not rewrite history. Only the current
year's file is re-fetched.

### Session cache keys

The snapshot session key is `f"snapshots_{base_ccy}_{precision}"` — it does
**not** include the chart date range. Switching between "All time" and "Last
3 months" is a pure Python list slice over the full computed series
(`~0.1 ms` regardless of length). Only a display-currency or precision change
triggers a recompute.

---

## 9. Performance decisions

### Algorithm: forward pass over time (O(days + tx), not O(days × tx))

The naive approach calls `_holdings_at_day(all_transactions, day)` once per
day, replaying all transactions from the beginning each time. For a 6-year
daily portfolio with 150 transactions that is 2192 × 150 = 328 800 inner-loop
iterations.

The implemented approach keeps a running `balance` dict and a `tx_idx`
pointer. As the day advances, pending transactions are applied once and never
revisited:

```python
# O(days + transactions) — the pointer only moves forward
while tx_idx < n_tx and pending_tx[tx_idx]["date"] <= day_str:
    for e in pending_tx[tx_idx]["entries"]:
        balance[e["ticker"]] += e["amount"]
    tx_idx += 1
```

Cumulative invested uses the same pass — a single accumulator updated when the
invested rule marks an entry as a deposit/withdrawal.

### Price downloads: one batched request, not per-ticker threads

`ticker_data.ensure_batch()` computes exactly which `(ticker, year)` slabs are
missing, then downloads **all of them in a single `yf.download` call**
(`threads=True` inside yfinance, 3 retries, per-ticker fallback for symbols
the batch couldn't fetch). Since the requests are network-bound, letting the
Yahoo client fan out internally is simpler and faster than orchestrating a
thread pool in Negotium. London-listed (`.L`) symbols get an extra currency
check so pence quotes are normalised to GBP.

A smaller `ThreadPoolExecutor` remains in `ui/watchlist.py`, where quote
warm-up for watchlist entries is genuinely independent per ticker.

### JSON backend: orjson

`storage.py` imports `orjson` when available and falls back to stdlib `json`
transparently. `orjson` is a Rust-backed library that runs natively on Apple
Silicon:

| Operation | stdlib json | orjson | Speedup |
|-----------|-------------|--------|---------|
| `dumps`   | 5.3 µs      | 0.6 µs | 9×      |
| `loads`   | 4.3 µs      | 1.5 µs | 3×      |

All file handles are opened in binary mode (`rb` / `wb`) to skip Python-level
newline normalisation and UTF-8 codec calls per line. `orjson.dumps` returns
`bytes` directly, so the pipeline is: Python dict → bytes → disk, with no
intermediate string.

### Portfolio invalidation without loading the file

`storage.invalidate_portfolio_from(date)` streams `portfolio.jsonl` line by
line, checking only the date field near the start of each line against the
cutoff — it never parses ~1 MB of JSON just to drop a few trailing lines:

```python
date_bytes = stripped[9:19]   # b'YYYY-MM-DD' from {"date": "YYYY-MM-DD", ...}
if date_bytes.decode() < from_date:
    dst.write(line)
```

Output goes to a `.tmp` file atomically renamed over the original, so a crash
mid-invalidation cannot corrupt the file.

---

## 10. Dependency map

```
app.py
 └── ui/ (runtime, sidebar, dashboard, …)
      ├── config            (stdlib json, pathlib)
      ├── storage           (orjson or stdlib json, pathlib, threading)
      ├── ledger_core       (storage, config, ticker_translate, ticker_data)
      ├── portfolio_core    (storage, ticker_data, ledger_core)
      └── bossa/xtb/manual_import
           └── transactions, storage, config,
               isin_resolve (bossa), ticker_translate (xtb)

External:
 yfinance         → Yahoo Finance HTTPS API (prices, FX, dividends, earnings, info)
 streamlit        → local web server (default localhost:8501)
 plotly           → interactive charts rendered in the browser
 pandas           → DataFrame handling (yfinance output, XTB sheets)
 openpyxl         → XTB .xlsx parsing (python-calamine as fast engine)
 orjson           → fast JSON backend (optional, falls back to stdlib)
```

All external network traffic goes to Yahoo Finance. Streamlit serves entirely
on localhost — no data leaves the machine except price/metadata download
requests.

---

## 11. Benchmark numbers

Measured on Python 3.12 with orjson, using a synthetic portfolio of 2 stock
tickers (AAPL, MSFT), FX pairs (USDPLN, EURPLN, EURUSD), and 150 transactions
spread over 6 years (2192 daily data points):

| Operation | Time | Notes |
|---|---|---|
| Full 6-year daily build (first run) | ~83 ms | All days computed from scratch |
| Weekly startup (resume 7 missing days) | ~25 ms | Loads cache, computes 7 new days |
| Date range filter (e.g. "Last 3 months") | ~0.1 ms | Pure Python slice, no I/O |
| `load_portfolio` from disk (2192 lines) | ~53 ms | orjson parse of ~921 KB |
| `save_portfolio` to disk (2192 lines) | ~3.4 ms | orjson serialise + write |
| `load_price_year` (single ticker/year) | ~0.1 ms | orjson parse of ~260 trading days |
| Yahoo Finance download | 0.5–2 s | Network latency, one batched call for all tickers |

The weekly startup is the bottleneck in practice — almost all of the 25 ms is
reading `portfolio.jsonl` back from disk; the actual computation (7 days × N
tickers) is under 1 ms.

If `portfolio.jsonl` load time ever becomes noticeable (portfolios larger than
~10 years with many tickers), the natural next step is a binary columnar
format (Apache Arrow / Feather), which would cut those 53 ms to under 5 ms.





