#  Negotium - Investment Tracker — Architecture

A local Python application that tracks a multi-currency stock portfolio over time.
No server, no database daemon, no background process. Everything lives in plain files
and starts from cold in under a second.

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
├── app.py           UI layer. Streamlit. Owns session state and user events.
├── config.py        Read / write config.json. No logic beyond that.
├── storage.py       All file I/O. The only module that touches the filesystem
│                    (except ticker_data, which also writes price cache files).
├── ticker_data.py   Yahoo Finance download + per-year price cache. FX pairs.
├── transactions.py  Transaction ledger: add, read, maintain chronological order.
└── portfolio.py     Build the portfolio value time-series. The core engine.
```

No module except `storage` and `ticker_data` reads or writes files directly.
`app.py` does not touch the filesystem at all — it calls the other modules.

---

## 2. File layout on disk

```
investment_tracker/         ← project root
├── data/config.json             app settings (name, start date, currency, precision)
├── data/balance.json            current holdings snapshot {ticker: float}
├── data/transactions.jsonl      append-only ledger, one JSON object per line
├── data/portfolio.jsonl         computed daily snapshots, one JSON object per line
└── data/
    ├── AAPL/
    │   ├── 2023.json       {YYYY-MM-DD: close_price} for every trading day
    │   └── 2024.json
    ├── USDPLN/
    │   └── 2024.json
    ├── EURPLN/
    │   └── 2024.json
    └── EURUSD/
        └── 2024.json
```

All files are human-readable JSON / JSONL. You can open any of them in a text
editor. The `data/` directory is the price cache — deleting any file inside it
just means it will be re-downloaded from Yahoo Finance on next startup.

---

## 3. File formats

### config.json

```json
{
  "name": "My Portfolio",
  "start_day": "2023-01-01",
  "default_currency": "PLN",
  "graph_precision": "1D"
}
```

`graph_precision` is `"1D"` (daily) or `"1W"` (weekly Fridays).

### transactions.jsonl — one line per date, chronological

```jsonl
{"date":"2023-01-03","entries":[{"ticker":"AAPL","amount":10.0},{"ticker":"USD","amount":-1250.0}]}
{"date":"2023-06-01","entries":[{"ticker":"CDR.WA","amount":5.0},{"ticker":"PLN","amount":-625.0}]}
```

- One line per calendar date. Multiple buys/sells on the same day are stored in
  one line as multiple entries.
- The file must stay in ascending date order. `transactions.add_transaction()`
  enforces this, rewriting the file if a past-date entry is inserted.
- `ticker` can be any stock symbol (`AAPL`, `CDR.WA`, `SAP.DE`) or a cash
  currency (`USD`, `EUR`, `PLN`).
- Negative `amount` = money or shares leaving (sell, cash out, wire transfer out).

### balance.json — current holdings

```json
{
  "AAPL": 10.0,
  "USD": -1250.0,
  "CDR.WA": 5.0,
  "PLN": -625.0
}
```

This is a derived file. It is rebuilt by replaying `transactions.jsonl` whenever
transactions change. Its only purpose is to avoid replaying the whole ledger every
time the UI needs current holdings. Entries with `|amount| < 1e-9` are excluded.

### data/{TICKER}/{YEAR}.json — price cache

```json
{
  "2024-01-02": 185.2,
  "2024-01-03": 184.4,
  "2024-01-04": 182.9
}
```

Only trading days appear (no weekends, no holidays). Stored as `float` with
6-decimal precision. One file per ticker per calendar year.

FX pairs use Yahoo Finance symbols mapped to internal names:

| Internal name | Yahoo symbol | Meaning           |
|---------------|--------------|-------------------|
| `USDPLN`      | `USDPLN=X`   | 1 USD → N PLN     |
| `EURPLN`      | `EURPLN=X`   | 1 EUR → N PLN     |
| `EURUSD`      | `EURUSD=X`   | 1 EUR → N USD     |

### portfolio.jsonl — computed daily snapshots

```json
{
  "date": "2024-01-03",
  "assets": [
    {
      "ticker": "AAPL",
      "amount": 10.0,
      "price": 185.2,
      "currency": "USD",
      "value_native": 1852.0,
      "value_base": 7437.08
    },
    {
      "ticker": "USD",
      "amount": -1250.0,
      "price": 1.0,
      "currency": "USD",
      "value_native": -1250.0,
      "value_base": -5017.5
    }
  ],
  "total_value": 2419.58,
  "invested": 0.0,
  "base_currency": "PLN"
}
```

- One line per day (or Friday if weekly precision).
- `value_native` = amount × price in the asset's own currency.
- `value_base` = `value_native` × FX rate → base currency.
- `total_value` = sum of all `value_base` entries.
- `invested` = cumulative sum of all positive cash inflows in base currency
  (used to draw the "invested capital" reference line on the chart).
- `base_currency` tags the snapshot so that snapshots for different display
  currencies are stored and retrieved independently.

---

## 4. Data flow — startup

```
start.sh
│
├─ 1. python3 tests/test_runner.py          (optional, --skip-tests to bypass)
│
└─ 2. streamlit run src/app.py
       │
       ├─ config.load()                     read config.json → cfg dict
       │
       ├─ transactions.get_all_transactions()
       │    └─ storage.read_jsonl(transactions.jsonl)
       │
       ├─ transactions.get_all_tickers()    scan ledger → set of ticker strings
       │                                    + required FX pairs
       │
       ├─ [parallel] ThreadPoolExecutor(max_workers=6)
       │    └─ ticker_data.ensure(ticker)   for each ticker:
       │         ├─ skip if storage.has_price_year(ticker, year) = True
       │         │   and not force_refresh (historical years cached forever)
       │         └─ yf.download(symbol, start, end)   (current year only)
       │              └─ storage.save_price_year(ticker, year, prices)
       │
       ├─ portfolio.build_portfolio()
       │    ├─ storage.load_portfolio()     read existing snapshots
       │    ├─ filter to base_currency      PLN / EUR / USD
       │    ├─ find resume_from date        last cached + 1 day
       │    └─ forward pass over new days   (see section 6)
       │         └─ storage.save_portfolio()
       │
       └─ render UI
            ├─ filter snapshots by chart date range  (pure Python, no I/O)
            ├─ plotly chart
            ├─ metric cards
            └─ holdings table
```

On a typical weekly startup (all historical data cached, only 7 new days to
compute), this entire sequence takes **25–50 ms** of Python compute time,
plus whatever Yahoo Finance takes to respond for the current-year price update
(~0.5–2 s per ticker, happening in parallel).

---

## 5. Data flow — add a transaction

```
UI form submit
│
└─ transactions.add_transaction(date, entries)
     │
     ├─ storage.read_jsonl(transactions.jsonl)   load full ledger
     │
     ├─ Three-way branch on date position:
     │
     │   A. date > last line date
     │      └─ storage.append_jsonl()            O(1) — just append
     │         storage.load_balance() + apply + storage.save_balance()
     │
     │   B. date == last line date
     │      └─ merge entries into last record
     │         storage.write_jsonl()             rewrite whole file
     │         _rebuild_balance()               replay all tx
     │
     │   C. date < last line date  (past insertion)
     │      └─ scan for insertion point
     │         storage.write_jsonl()             rewrite whole file
     │         _rebuild_balance()               replay all tx
     │
     └─ storage.invalidate_portfolio_from(date)
          └─ stream portfolio.jsonl, keep lines where date < insertion date
             write to .tmp, atomically rename over original
             (avoids loading 1 MB file into RAM just to trim it)
```

After `add_transaction` returns, `app.py` pops the session state cache key for
the affected currency and calls `st.rerun()`. The next render rebuilds only from
the invalidated date onward.

---

## 6. Data flow — build portfolio

This is the most algorithmically significant function. The key insight is that
computing holdings for every day using a replay-from-scratch approach is O(days ×
transactions). Instead, a single forward pass gives O(days + transactions).

```
portfolio.build_portfolio(start, end, base_ccy, precision)
│
├─ Load existing snapshots from portfolio.jsonl
│  filtered to base_ccy
│
├─ Restore running state from last cached snapshot:
│   balance = {ticker: amount}  (from last snapshot's assets)
│   cumulative_contrib = last snapshot's invested
│
├─ Load pending transactions (date >= resume_from)
│
├─ For each day in range [resume_from .. end]:   ← FORWARD PASS
│   │
│   ├─ Apply all pending tx whose date <= today   (tx_idx pointer advances,
│   │   update balance dict in place               never resets)
│   │   if tx is a cash inflow: cumulative_contrib += amount × fx_rate
│   │
│   ├─ For each ticker in balance:
│   │   ├─ if cash (USD/EUR/PLN):
│   │   │    value_base = amount × get_fx_rate(ccy → base_ccy, day)
│   │   └─ if stock:
│   │        price      = _PriceCache.get(ticker, day)
│   │                     (loads year slab once, walks back ≤5 days for weekends)
│   │        value_base = amount × price × get_fx_rate(ticker_ccy → base_ccy, day)
│   │
│   └─ Append snapshot dict to new_snapshots list
│
├─ _merge_snapshots(existing, new_snapshots)
│   deduplicate by date, new wins, sort by date
│
└─ storage.save_portfolio(merged)
```

### _PriceCache — RAM layout

```
_data: {
  "AAPL":   { 2023: {"2023-01-03": 125.07, ...},   ← loaded on first access
              2024: {"2024-01-02": 185.20, ...} },  ← loaded when year changes
  "USDPLN": { 2023: {"2023-01-03": 4.38, ...},
              2024: {"2024-01-02": 4.01, ...} },
  ...
}
```

Each `(ticker, year)` slab is loaded from disk exactly once per `build_portfolio`
call. A 5-year portfolio with 10 tickers occupies roughly
`10 tickers × 5 years × 260 trading days × ~20 bytes per entry ≈ 260 KB` in RAM —
negligible on any machine.

---

## 7. Multi-currency logic

### Ticker currency detection

The price of a stock is always quoted in a specific currency. The app infers this
from the ticker suffix rather than storing it explicitly:

```python
*.WA   → PLN   (Warsaw Stock Exchange / GPW)
*.DE   → EUR   (Xetra Frankfurt)
*.F    → EUR   (Frankfurt general)
*.PA   → EUR   (Euronext Paris)
*.MI   → EUR   (Borsa Italiana)
*.AS   → EUR   (Euronext Amsterdam)
*.BR   → EUR   (Euronext Brussels)
*.LS   → EUR   (Euronext Lisbon)
(none) → USD   (default: NYSE / NASDAQ)
```

### FX conversion chain

For each asset on each day:

```
value_base = amount × price_in_native_ccy × fx_rate(native_ccy → base_ccy)
```

FX lookup order (implemented in `ticker_data.get_fx_rate`):

```
1. Direct pair exists in FX_YAHOO?   → use it
2. Reverse pair exists?              → 1 / reverse_rate
3. Triangulate via USD:
     EUR→PLN = EURUSD × USDPLN
     PLN→EUR = 1 / (EURUSD × USDPLN)
     PLN→USD = 1 / USDPLN
4. Fallback: 1.0  (same-currency, or rate unavailable)
```

FX rates are fetched and cached identically to stock prices — per-year JSON files
under `data/USDPLN/`, `data/EURPLN/`, `data/EURUSD/`.

### Weekend and holiday handling

Stock markets don't trade on weekends or public holidays. When a price for
date `D` is not found in the cache, `get_price` walks backward up to 5 calendar
days until it finds a valid close. This covers all weekends (2 days) and long
holiday weekends (up to 4 days in most markets). FX pairs use the same mechanism
since forex markets also close on weekends.

### Moving money between currencies

A currency exchange (e.g. converting USD to PLN) is recorded as two entries on
the same transaction line:

```jsonl
{"date":"2024-03-15","entries":[{"ticker":"USD","amount":-5000.0},{"ticker":"PLN","amount":19850.0}]}
```

The USD balance decreases by 5000, the PLN balance increases by 19850. The actual
exchange rate at the moment of transfer is implicitly captured in the ratio. The
portfolio engine tracks both cash positions independently and converts them to the
display currency using the market FX rate for that day, so historical P&L
correctly reflects what the exchange rate was at the time of transfer.

---

## 8. Caching strategy

There are four distinct caches, each with different scope and lifetime:

| Cache | Location | Lifetime | Keyed by |
|---|---|---|---|
| Price history | `data/{TICKER}/{YEAR}.json` | Permanent (historical years never re-fetched) | ticker, year |
| Current year prices | `data/{TICKER}/{current_year}.json` | Re-fetched on each startup (or Refresh button) | ticker |
| Portfolio snapshots | `portfolio.jsonl` | Until a transaction is added/modified | base_currency, date |
| Streamlit session | `st.session_state["snapshots_{ccy}_{precision}"]` | Until tab closes or transaction added | base_ccy, precision |

### Cache invalidation on transaction insert

When a transaction is added for date `D`:

1. `storage.invalidate_portfolio_from(D)` streams through `portfolio.jsonl`,
   keeps only lines with `date < D`, writes atomically via `.tmp` rename.
2. `app.py` pops `st.session_state["snapshots_{base_ccy}_{precision}"]`.
3. Next render calls `build_portfolio()` which resumes from the invalidated date.

Historical year price files (`2022.json`, `2023.json`) are **never deleted or
invalidated** — Yahoo Finance will not change historical closing prices for past
years. Only the current year's file is re-fetched on each startup.

### Session state cache key

The Streamlit session cache uses `f"snapshots_{base_ccy}_{precision}"` — it does
**not** include the chart date range. Switching between "All time" and "Last 3
months" is a pure Python list slice over the already-computed full series:

```python
snapshots = [s for s in all_snapshots if cs <= s["date"] <= ce]
```

This runs in ~0.1 ms regardless of portfolio length. Only switching between PLN /
EUR / USD display currency, or daily / weekly precision, triggers a recompute.

---

## 9. Performance decisions

### Algorithm: forward pass over time (O(n + t) vs O(n × t))

The original approach called `_holdings_at_day(all_transactions, day)` once per
day, replaying all transactions from the beginning each time. For a 6-year daily
portfolio with 150 transactions that is 2192 × 150 = 328 800 iterations of the
inner loop.

The rewritten approach maintains a running `balance` dict and a `tx_idx` pointer.
As the day advances, pending transactions are applied once and never revisited:

```python
# O(days + transactions) — pointer only moves forward
while tx_idx < n_tx and pending_tx[tx_idx]["date"] <= day_str:
    for e in pending_tx[tx_idx]["entries"]:
        balance[e["ticker"]] += e["amount"]
    tx_idx += 1
```

Cumulative invested uses the same pass — it is a single float accumulator
updated when a positive cash transaction is applied, eliminating a second O(n × t)
scan that the previous implementation performed.

### JSON backend: orjson

`storage.py` imports `orjson` when available and falls back to stdlib `json`
transparently. `orjson` is a Rust-backed library with ARM NEON vectorisation that
runs natively on Apple Silicon:

| Operation  | stdlib json | orjson | Speedup |
|------------|-------------|--------|---------|
| `dumps`    | 5.3 µs      | 0.6 µs | 9×      |
| `loads`    | 4.3 µs      | 1.5 µs | 3×      |

All file handles are opened in binary mode (`rb` / `wb`) to avoid a Python-level
UTF-8 encode/decode pass on every line. `orjson.dumps` returns `bytes` directly,
so the pipeline is: Python dict → bytes → disk, with no intermediate string.

### Parallel ticker downloads

Tickers are downloaded concurrently using `ThreadPoolExecutor(max_workers=6)`.
Since Yahoo Finance requests are network-bound (not CPU-bound), threading is the
right primitive — multiple sockets are open simultaneously, each waiting for HTTP
responses independently. For a 5-ticker portfolio this reduces download time from
~7 s (sequential) to ~2 s (parallel).

```python
with ThreadPoolExecutor(max_workers=6) as pool:
    futures = {pool.submit(_ensure_ticker, t): t for t in tickers_needed}
    for future in as_completed(futures):
        future.result()
```

### Binary mode I/O

Opening files in `rb`/`wb` mode avoids Python's text-mode overhead, which
includes newline normalisation and a UTF-8 codec call per read chunk. On M1 the
difference is small for individual files but adds up when reading thousands of
lines from `portfolio.jsonl`.

### Portfolio invalidation without loading the full file

`storage.invalidate_portfolio_from(date)` does not load `portfolio.jsonl` into a
Python list. It streams line by line, checking only the first 16 bytes of each
line (the date field in the JSON) against the cutoff date string. This avoids
parsing ~1 MB of JSON just to remove a few trailing lines.

```python
date_bytes = stripped[9:19]   # b'YYYY-MM-DD' from {"date": "YYYY-MM-DD", ...}
if date_bytes.decode() < from_date:
    dst.write(line)
```

The output is written to a `.tmp` file and atomically renamed over the original,
so a crash mid-invalidation cannot corrupt the file.

---

## 10. Dependency map

```
app.py
 ├── config          (stdlib json, pathlib)
 ├── storage         (orjson or stdlib json, pathlib)
 ├── ticker_data     (yfinance, storage)
 ├── transactions    (storage)
 └── portfolio       (storage, ticker_data, transactions)

External:
 yfinance      → Yahoo Finance HTTPS API (price history, FX rates)
 streamlit     → local web server on localhost:8501
 plotly        → interactive chart rendered in the browser
 pandas        → used by yfinance for DataFrame I/O (not used directly)
 orjson        → fast JSON backend (optional, falls back to stdlib)
```

All external network traffic is Yahoo Finance only. Streamlit serves entirely on
localhost — no data leaves your machine except the price download requests.

---

## 11. Benchmark numbers

Measured on Python 3.12 with orjson, using a synthetic portfolio of 2 stock
tickers (AAPL, MSFT), FX pairs (USDPLN, EURPLN, EURUSD), and 150 transactions
spread over 6 years (2192 daily data points).

| Operation | Time | Notes |
|---|---|---|
| Full 6-year daily build (first run) | ~83 ms | All days computed from scratch |
| Weekly startup (resume 7 missing days) | ~25 ms | Loads cache, computes 7 new days |
| Date range filter (e.g. "Last 3 months") | ~0.1 ms | Pure Python slice, no I/O |
| `load_portfolio` from disk (2192 lines) | ~53 ms | orjson parse of ~921 KB |
| `save_portfolio` to disk (2192 lines) | ~3.4 ms | orjson serialise + write |
| `load_price_year` (single ticker/year) | ~0.1 ms | orjson parse of ~260 trading days |
| Yahoo Finance download (one ticker) | 0.5–2 s | Network latency, not our code |

The weekly startup is the bottleneck in practice — and almost all of that 25 ms is
reading `portfolio.jsonl` back from disk. The actual computation (7 days × N
tickers) is under 1 ms.

If `portfolio.jsonl` load time ever becomes noticeable (portfolios larger than ~10
years with many tickers), the natural next step is to replace the JSONL format
with a binary columnar format (Apache Arrow / Feather), which would reduce that
53 ms to under 5 ms.
