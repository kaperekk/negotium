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

## Importing from Bossa (DM BOŚ)

Negotium can import transaction history exported from **DM BOŚ** (Bossa) brokerage.

### How to export from Bossa

1. Log in to your DM BOŚ account at [bossa.pl](https://www.bossa.pl)
2. Go to **Historia finansowa** (Financial history)
3. Set the date range you want to export (e.g. from your account start to today)
4. Make sure **Pokaż** (Show) is set to display individual transactions, not just summaries
5. Click **Eksportuj do CSV** (Export to CSV)
6. Save the file — it will be a **semicolon-separated** CSV

### CSV format

The exported CSV must be **semicolon-separated** (`;`) with these columns:

```csv
data;tytuł operacji;szczegóły;kwota;waluta
```

Example rows:

```csv
data;tytuł operacji;szczegóły;kwota;waluta
15.05.2026;Rozliczenie transakcji kupna:;iShares MSCI Global Semiconductors UCITS ETF (IE000I8KRLL9) 132 x 16.488 EUR nr Z00348421888;-;2 176.42;EUR
16.04.2026;Wymiana waluty PLN/EUR 4.2385;;;4 246.75;-;EUR
07.01.2026;Przelew do DM BOŚ;;;28 620.00;-;PLN
```

### Recognised operation types

| Polish operation title | Meaning | Negotium action |
|---|---|---|
| `Rozliczenie transakcji kupna:` | Share purchase | Buy (shares in, cash out) |
| `Rozliczenie transakcji sprzedaży:` | Share sale | Sell (shares out, cash in) |
| `Wymiana waluty {SRC}/{TGT} {rate}` | Currency exchange | FX swap (two entries) |
| `Przelew do DM BOŚ` | Cash deposit | Cash deposit |

### Uploading

1. In the app, go to the **Import** tab
2. Select **BOSSA** as the broker
3. Upload your CSV file(s)
4. Select the currency for each file (PLN, EUR, or Many if mixed)
5. Click the import button

If any ISINs cannot be resolved to Yahoo Finance tickers, a warning will list the unresolved ones. You can then add manual ticker mappings in the app.

### Supported instruments

Negotium resolves ISINs from the CSV details column to Yahoo Finance tickers automatically. Most European-listed ETFs and stocks are supported. If an ISIN is not found, you can add a manual mapping in the app.

---

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
