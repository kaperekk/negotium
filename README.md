# ⚡ Negotium — Investment Tracker

A local-first portfolio tracker: follow the value of your stock portfolio over
time across USD, EUR, PLN positions — with broker statement imports, benchmark
comparisons, drawdown analysis, and a per-project watchlist. No server, no
database daemon, no background process: everything lives in plain JSON/JSONL
files on your disk.

Created by **Kacper Kaperek**. If you like this, buy me a coffee:
[buymeacoffee.com/ACCOUNTNUMBER](https://buymeacoffee.com/ACCOUNTNUMBER)

## Features

- **Multi-project** — keep broker accounts (XTB, BOSSA, …) as independent projects with separate ledgers
- **Multi-currency** — exchange suffix → currency mapping for 13 markets; cash tracked as positions; display in PLN / EUR / USD
- **Broker imports** — XTB Excel, BOSSA CSV, custom JSON; idempotent re-imports (duplicates skipped)
- **Ticker translation** — rewrite broker symbols to Yahoo Finance format with rules; resolve ISINs for BOSSA
- **Portfolio chart** — daily time-series with invested-capital line and benchmark overlays (S&P 500, NASDAQ 100, FTSE All-World, EM, Bitcoin, Gold)
- **Metrics** — value, P&L, contributions, CAGR, IRR, best performer
- **Analysis** — allocation donuts (sector / geography / asset class / currency), drawdown "underwater" chart, per-ticker trade history with dividends
- **Watchlist** — track any Yahoo Finance ticker with price, change and sparkline (per project)
- **Fast & local** — historical prices cached forever, only the current year re-fetches; everything except price downloads stays on localhost

## Quick start

```bash
./start.sh
```

The launcher finds Python 3.10+, installs missing dependencies, runs the test
suite, and opens the app at http://localhost:8501.

| Option | Effect |
|---|---|
| `--skip-tests` | skip the test suite on launch |
| `--tests-only` | run tests and exit |
| `--port N` | use port N (default 8501) |
| `--reset` | wipe all data and start fresh |
| `-h`, `--help` | show help |

## Requirements

- **Python 3.10+** (macOS / Linux; the launcher prefers 3.14 and falls back to 3.13 / 3.12 / 3.11)
- Internet access to **Yahoo Finance** for prices, FX rates, dividends and company metadata — the only outbound traffic; the UI itself is served on localhost
- Dependencies installed automatically on first run: `yfinance`, `streamlit`, `plotly`, `pandas`, `orjson`, `openpyxl`, `python-calamine`

## Documentation

| Doc | Read it for |
|---|---|
| [USAGE.md](USAGE.md) | Daily use: projects, sidebar, transactions, dashboard, watchlist, refresh |
| [IMPORTS.md](IMPORTS.md) | Importing statements from XTB, BOSSA, or your own JSON |
| [CONFIG.md](CONFIG.md) | Settings reference: ticker rules, ISIN mappings, currencies, data files |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How it works inside: modules, data flow, caching, performance |

## Project layout

```
negotium/
├── start.sh                  ← launcher (finds python, installs deps, runs tests)
├── data/
│   ├── config.json           ← global config (all projects share it)
│   ├── projects.json         ← project registry (created_at, last_refresh, watchlist)
│   ├── prices/               ← shared price cache: prices/{TICKER}/{YEAR}.json
│   ├── ticker_names.json     ← company names per ticker
│   ├── ticker_meta.json      ← sector / country / asset class per ticker
│   ├── dividends.json        ← dividend history per ticker
│   ├── earnings.json         ← next earnings date per ticker
│   └── {PROJECT}/            ← one directory per project
│       ├── transactions.jsonl    ← ledger — the source of truth
│       ├── balance.json          ← derived current holdings
│       ├── portfolio.jsonl       ← derived daily snapshots
│       ├── benchmarks_{CCY}.json ← derived benchmark series
│       └── imports/{broker}/     ← uploaded statement files
├── src/                      ← application code (see ARCHITECTURE.md)
│   ├── app.py …              ← Streamlit entry + core modules
│   └── ui/                   ← Streamlit view layer, one module per section
└── tests/
    ├── conftest.py           ← shared fixtures (isolated temp dirs)
    └── test_*.py             ← 145 tests, pytest
```

## The 60-second data model

One line per calendar date in `transactions.jsonl` — positive amounts buy,
negative amounts sell (or spend cash):

```json
{"date": "2024-01-15", "entries": [{"ticker": "AAPL", "amount": 10.0}, {"ticker": "USD", "amount": -1710.0}]}
{"date": "2024-03-01", "entries": [{"ticker": "USD", "amount": -5000.0}, {"ticker": "PLN", "amount": 19850.0}]}
```

- `ticker` is a stock symbol or a cash currency (`USD` / `EUR` / `PLN`)
- the second line is a currency exchange: USD out, PLN in
- everything else in `data/` is derived from this ledger and can be rebuilt

Full format details: [CONFIG.md](CONFIG.md#data-files).
