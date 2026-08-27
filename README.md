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
│       ├── transactions.jsonl
│       ├── portfolio.jsonl
│       ├── balance.json
│       └── imports/
├── src/
│   ├── app.py               ← Streamlit UI
│   ├── config.py            ← load/save config (single global file)
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

All settings live in a single global file: `data/config.json`. There is no per-project config — every project shares the same config.

```json
{
  "name": "My Portfolio",
  "start_day": "2020-01-01",
  "default_currency": "PLN",
  "graph_precision": "1D",
  "ticker_rules": ["AMZN.DE=AMZ.DE", "*.PL=*.WA", ".US="],
  "isin_tickers": ["IE00B4L5Y983=IWDA.L", "US5949181085=MSFT.US"]
}

> Note: the last auto-refresh timestamp is **not** stored here — it lives per-project in `data/projects.json` (`last_refresh` field on each project entry).
```

- `graph_precision`: `"1D"` (daily) or `"1W"` (weekly)
- `ticker_rules`: translation rules applied top-to-bottom, first match wins
- `isin_tickers`: ISIN-to-ticker mappings used by the BOSSA importer

### Ticker rules

Brokers often export ticker symbols in a format that doesn't match what Yahoo Finance expects (e.g. Xetra uses `.DE`, Warsaw uses `.WA`). Ticker rules rewrite symbols on import so prices resolve correctly.

Rules are evaluated top-to-bottom and the **first matching rule wins**. Each rule is `PATTERN=REPLACEMENT` (one per line in the UI's *Settings → Ticker rules* box). Three forms are supported:

| Form | Example | Meaning |
|------|---------|---------|
| Exact match | `AMZN.DE=AMZ.DE` | Rewrite `AMZN.DE` → `AMZ.DE` |
| Suffix swap (`*.`) | `*.PL=*.WA` | Any ticker ending in `.PL` gets that suffix replaced with `.WA` (e.g. `SNT.PL` → `SNT.WA`) |
| Suffix strip (`.`) | `.US=` | Any ticker ending in `.US` loses the suffix (e.g. `AAPL.US` → `AAPL`); an empty replacement deletes the matched part |

The `*` on the left stands for "any base symbol", and on the right it's replaced by that same base. A leading `.` (without `*`) matches a literal suffix to strip/rewrite. Symbols that match no rule are left unchanged.

> Tip: use suffix rules to normalise a whole exchange at once (e.g. `*.PL=*.WA` for all Warsaw listings) and exact rules for one-off fixes.

### ISIN tickers

BOSSA statements identify instruments by **ISIN** (e.g. `IE00B4L5Y983`), not by ticker symbol. Because ISINs can't be looked up on Yahoo Finance directly, you map each ISIN to the ticker Negotium should use for pricing.

Each entry is `ISIN=TICKER` (one per line):

```
IE00B4L5Y983=IWDA.L
US5949181085=MSFT.US
```

When the BOSSA importer encounters an ISIN, it looks it up in this list and uses the mapped ticker to download prices. ISINs without a mapping are reported as unresolved and skipped from the chart until you add a rule.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed module relationships, data flow, caching strategy, and performance notes.
