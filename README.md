# Negotium - Investment Tracker

Created by **Kacper Kaperek**. If you like this, buy me a coffee: [buymeacoffee.com/ACCOUNTNUMBER](https://buymeacoffee.com/ACCOUNTNUMBER)

Track portfolio value over time across USD, EUR, PLN positions. Supports multiple projects (e.g. separate broker accounts), with BOSSA, XTB, and custom JSON importers.

## Quick start

```bash
./start.sh
```

The launcher finds Python 3.10+, installs missing dependencies, runs tests, and opens the app at http://localhost:8501.

**Options:**
- `--skip-tests` — skip test suite on launch
- `--tests-only` — run tests and exit
- `--port N` — change the port (default 8501)
- `--reset` — wipe all data and start fresh

## Imports

See [IMPORTS.md](IMPORTS.md) for how to import transactions from BOSSA, XTB, or manually.

## File layout

```
negotium/
├── start.sh                 ← launcher (finds python, installs deps, runs tests)
├── data/
│   ├── config.json          ← global config
│   ├── projects.json        ← project registry
│   ├── prices/              ← shared price cache
│   │   └── {TICKER}/{YEAR}.json
│   └── {PROJECT}/           ← per-project directory
│       ├── config.json      ← project overrides
│       ├── transactions.jsonl
│       ├── portfolio.jsonl
│       ├── balance.json
│       └── imports/
├── src/
│   ├── app.py               ← Streamlit UI
│   ├── config.py            ← load/save config (global + per-project)
│   ├── storage.py           ← JSONL helpers, price cache, project management
│   ├── ticker_data.py       ← Yahoo Finance download + cache
│   ├── ticker_translate.py  ← rule-based ticker symbol translation
│   ├── transactions.py      ← add/read/delete transactions, balance
│   ├── portfolio.py         ← build portfolio time-series
│   ├── bossa_import.py      ← BOSSA CSV importer
│   ├── xtb_import.py        ← XTB Excel importer
│   ├── manual_import.py     ← manual JSON importer
│   ├── isin_resolve.py      ← ISIN to ticker resolver
│   └── fixtures.py          ← test helpers
└── tests/
    └── test_runner.py       ← 55 tests covering all modules
```

## Transaction format

`transactions.jsonl` — one JSON object per line, **chronological order required**:

```json
{"date": "2024-01-15", "entries": [{"ticker": "AAPL", "amount": 10.0}, {"ticker": "USD", "amount": -1710.0}]}
{"date": "2024-03-01", "entries": [{"ticker": "CDR.WA", "amount": 5.0}, {"ticker": "PLN", "amount": -625.0}]}
```

- `ticker` can be a stock symbol or a currency (`USD`, `EUR`, `PLN`) for cash
- negative `amount` = money leaving, positive = arriving
- Currency tickers are treated as cash (value = amount x 1 in that CCY)
- `account_operation` (optional boolean) — marks deposits/withdrawals that count toward invested capital

## Config

Global `data/config.json`:

```json
{
  "name": "My Portfolio",
  "start_day": "2020-01-01",
  "default_currency": "PLN",
  "graph_precision": "1D",
  "ticker_rules": ["AMZN.DE=AMZ.DE", "*.PL=*.WA"],
  "isin_tickers": ["IE00B4L5Y983=IWDA.L"]
}
```

- `graph_precision`: `"1D"` (daily) or `"1W"` (weekly)
- `ticker_rules`: translation rules applied top-to-bottom, first match wins (exact match or suffix swap/strip)
- `isin_tickers`: ISIN-to-ticker mappings used by the BOSSA importer

Per-project overrides go in `data/{project}/config.json`.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed module relationships, data flow, caching strategy, and performance notes.
