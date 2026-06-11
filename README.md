# Negotium - Investment Tracker

Created by **Kacper Kaperek**. If you like this, buy me a coffee: [buymeacoffee.com/ACCOUNTNUMBER](https://buymeacoffee.com/ACCOUNTNUMBER)

Track portfolio value over time across USD, EUR, PLN positions.

## Setup

```bash
# Install dependencies (one time)
pip3 install yfinance streamlit plotly pandas --break-system-packages

# Or with uv (faster, recommended on M1):
# pip3 install uv --break-system-packages
# uv pip install yfinance streamlit plotly pandas
```

## Run

```bash
cd investment_tracker
streamlit run src/app.py
```

Opens at http://localhost:8501

## Imports

See [IMPORTS.md](IMPORTS.md) for how to import transactions from Bossa, XTB, or manually.

## File layout

```
investment_tracker/
├── config.json          ← created on first run
├── balance.json         ← current share/unit holdings per ticker
├── data/
│   └── {TICKER}/        ← price cache
│       ├── 2023.json
│       └── 2024.json
├── transactions.jsonl   ← append-only ledger (chronological)
├── portfolio.jsonl      ← computed daily snapshots (cache)
├── src/
│   ├── config.py        ← load/save config.json
│   ├── storage.py       ← JSONL helpers, price cache
│   ├── ticker_data.py   ← Yahoo Finance download + cache
│   ├── transactions.py  ← add/read transactions, balance
│   ├── portfolio.py     ← build portfolio time-series
│   ├── bossa_import.py  ← BOSSA CSV importer
│   └── app.py           ← Streamlit UI
└── tests/
    ├── test_runner.py   ← all tests + cleanup
    └── fixtures.py      ← shared test data
```

## Transaction format

`transactions.jsonl` — one JSON object per line, **chronological order required**:

```json
{"date": "2024-01-15", "entries": [{"ticker": "AAPL", "amount": 10.0}, {"ticker": "USD", "amount": -1710.0}]}
{"date": "2024-03-01", "entries": [{"ticker": "CDR.WA", "amount": 5.0}, {"ticker": "PLN", "amount": -625.0}]}
```

- `ticker` can be a stock symbol or a currency (`USD`, `EUR`, `PLN`) for cash
- negative `amount` = money leaving, positive = arriving
- Currency tickers are treated as cash (value = amount × 1 in that CCY)

## Config

`config.json`:

```json
{
  "name": "My Portfolio",
  "start_day": "2023-01-01",
  "default_currency": "PLN",
  "graph_precision": "1D"
}
```

`graph_precision`: `"1D"` (daily) or `"1W"` (weekly)
