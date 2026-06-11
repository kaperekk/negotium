# Imports

Negotium supports importing transaction history from multiple brokers and custom entry.

## Bossa (DM BOŚ)

### How to export

1. Log in to your DM BOŚ account at [bossa.pl](https://www.bossa.pl)
2. Go to **Historia finansowa** (Financial history)
3. Set the date range you want to export
4. Make sure **Pokaż** (Show) is set to display individual transactions
5. Click **Eksportuj do CSV** (Export to CSV)

### CSV format

Semicolon-separated (`;`) with these columns:

```csv
data;tytuł operacji;szczegóły;kwota;waluta
```

Example:

```csv
15.05.2026;Rozliczenie transakcji kupna:;iShares MSCI Global Semiconductors UCITS ETF (IE000I8KRLL9) 132 x 16.488 EUR nr Z00348421888;-;2 176.42;EUR
```

### Recognised operation types

| Polish operation title | Meaning | Negotium action |
|---|---|---|
| `Rozliczenie transakcji kupna:` | Share purchase | Buy |
| `Rozliczenie transakcji sprzedaży:` | Share sale | Sell |
| `Wymiana waluty {SRC}/{TGT} {rate}` | Currency exchange | FX swap |
| `Przelew do DM BOŚ` | Cash deposit | Cash deposit |

### Uploading

1. In the app, go to the **Import** tab
2. Select **BOSSA** as the broker
3. Upload your CSV file(s)
4. Select the currency for each file
5. Click the import button

---

## XTB

### How to export

1. Log in to your XTB account at [xstation5.xtb.com](https://xstation5.xtb.com)
2. Go to **Eksport (NEW)**
3. Select the time range you want to export
4. Select the accounts to include
5. Export the file

### Supported formats

XTB exports Excel files (`.xlsx`). Negotium supports multiple account exports (EUR, PLN, USD).

### Uploading

1. In the app, go to the **Import** tab
2. Select **XTB** as the broker
3. Upload your XLSX file(s)
4. The currency is auto-detected from the filename
5. Click the import button

---

## Custom import

Create a JSON file with transactions not covered by the automated importers.

### Format

`account_operation` marks a cash deposit or withdrawal (counts as invested capital, not a trade).

```json
[
  {
    "date": "2024-01-15",
    "entries": [
      {"ticker": "AAPL", "amount": 10.0},
      {"ticker": "USD", "amount": -1710.0}
    ]
  },
  {
    "date": "2024-02-01",
    "entries": [
      {"ticker": "USD", "amount": 5000.0, "account_operation": true}
    ]
  }
]
```

### Uploading

1. In the app, go to the **Import** tab
2. Select **Custom** as the broker
3. Upload your JSON file
4. Click the import button
