# Importing statements

Negotium imports transaction history from XTB and BOSSA, plus a custom JSON
format for everything else.

Part of the Negotium docs: [README](README.md) · [USAGE](USAGE.md) · [CONFIG](CONFIG.md) · [ARCHITECTURE](ARCHITECTURE.md)

## How importing works

1. Sidebar → **📥 Import statement** → pick the broker → upload file(s).
2. Uploads are saved to `data/{PROJECT}/imports/{broker}/` and kept there.
3. Rows are parsed, ticker symbols are translated through your ticker rules
   (see [CONFIG.md](CONFIG.md#ticker-rules)), and transactions are merged into
   the project ledger in chronological order.
4. Duplicates — same date, ticker and amount already in the ledger — are
   skipped and reported (`… imported, N skipped (duplicates)`).
5. The portfolio cache is invalidated and rebuilt from the earliest new date.

Imports are therefore **idempotent**: uploading the same file twice (or using
the sidebar **🔄 Refresh**, which replays every stored file) is safe.

| Broker | File type | Currency detection | Notes |
|---|---|---|---|
| XTB | `.xlsx` (Cash Operations sheet) | filename prefix, e.g. `EUR_history.xlsx` | multi-account exports supported |
| BOSSA | `.csv` (semicolon-separated) | per-transaction, from the file's `waluta` column | ISINs resolved via config mappings |
| Custom | `.json` | — | your own format, see below |

## XTB

### How to export

1. Log in at [xstation5.xtb.com](https://xstation5.xtb.com)
2. Go to **Eksport**
3. Select the time range and the accounts to include (EUR / PLN / USD)
4. Export the `.xlsx` file
5. **Name the file starting with the currency code** — e.g. `EUR_history.xlsx`.
   The prefix selects the account currency; an unrecognised prefix falls back
   to EUR.

### Recognised operations (Cash Operations sheet)

| Type column value | Negotium action |
|---|---|
| `Stock purchase` | Buy — share count parsed from the `OPEN BUY <n> @ <price>` comment; ticker + cash leg recorded |
| `Stock sell` | Sell — share count parsed from the `CLOSE BUY …` comment |
| `Deposit` / `Withdrawal` | Cash movement marked `account_operation` (counts toward invested capital) |
| `Transfer` | Cash movement marked `account_operation` |
| `Dividend` | Cash entry (no invested-capital impact) |
| `Free funds interest`, `Free funds interest tax`, `Withholding tax` | Cash entries |

Rows are merged per calendar date; rows without a recognised type or amount
are skipped and counted in the log.

### Uploading

1. Sidebar → **📥 Import statement** → Broker: **XTB**
2. Upload one or more `.xlsx` files (multi-account exports are fine)
3. Review the per-file result — imported count and skipped duplicates

## BOSSA (DM BOŚ)

### How to export

1. Log in to your DM BOŚ account at [bossa.pl](https://www.bossa.pl)
2. Go to **Historia finansowa** (Financial history)
3. Set the date range and make sure **Pokaż** lists individual transactions
4. Click **Eksportuj do CSV**

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
| `Wymiana waluty {SRC}/{TGT} {rate}` | Currency exchange | FX swap (two cash entries) |
| `Przelew do DM BOŚ` | Cash deposit | Deposit marked `account_operation` |

### ISIN resolution

BOSSA identifies instruments by **ISIN** (`IE000I8KRLL9`), which Yahoo Finance
cannot price directly. The importer looks each ISIN up in your **ISIN
mappings** (config → `isin_tickers`, see
[CONFIG.md](CONFIG.md#isin-mappings)) and uses the mapped ticker:

- Mapped ISIN → the transaction imports and prices with the mapped ticker.
- Unmapped ISIN → reported as unresolved and skipped; add a mapping and
  re-import (🔄 Refresh replays the stored file) to pick it up.

### Uploading

1. Sidebar → **📥 Import statement** → Broker: **BOSSA**
2. Upload one or more `.csv` files — the currency is read per transaction from
   the file's `waluta` column
3. Review the result; add any missing ISIN mappings and re-import if needed

## Custom import

Create a JSON file with transactions the automated importers don't cover.

### Format

An array of transactions; each has a `date` and `entries`. Setting
`account_operation: true` on an entry marks a deposit/withdrawal that counts
as invested capital rather than a trade (see the invested rule in
[ARCHITECTURE.md](ARCHITECTURE.md#3-file-formats)).

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

The file is validated before import (it must be a JSON array of well-formed
transactions). Ticker symbols pass through your ticker rules at import time.

### Uploading

1. Sidebar → **📥 Import statement** → Broker: **Custom**
2. Upload your `.json` file

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Unresolved ISIN …` reported | Add `ISIN=TICKER` under *Settings → ISIN mappings*, then **🔄 Refresh** |
| Prices missing for an imported ticker | The symbol doesn't match Yahoo Finance — add a ticker rule (see [CONFIG.md](CONFIG.md#ticker-rules)) |
| XTB file imported with the wrong currency | Rename the file with the correct prefix (e.g. `PLN_…xlsx`) and re-import |
| `N skipped (duplicates)` | Normal — those rows were already imported |
| Import changed history you didn't expect | Imports only append; check the ledger in `data/{PROJECT}/transactions.jsonl` |

