# Configuration reference

All settings live in one global file — `data/config.json` — shared by every
project. Per-project state (creation date, last refresh, watchlist) lives in
`data/projects.json`.

Part of the Negotium docs: [README](README.md) · [USAGE](USAGE.md) · [IMPORTS](IMPORTS.md) · [ARCHITECTURE](ARCHITECTURE.md)

## Global config — `data/config.json`

```json
{
  "default_currency": "PLN",
  "theme": "dark",
  "ticker_rules": ["AMZN.DE=AMZ.DE", "*.PL=*.WA", ".US="],
  "isin_tickers": ["IE00B4L5Y983=IWDA.AS"]
}
```

| Key | Purpose |
|---|---|
| `default_currency` | Display currency on first load: `PLN` / `EUR` / `USD` |
| `theme` | UI theme: `"dark"` or `"light"` (toggle in Sidebar → ⚙️ Settings) |
| `ticker_rules` | Ticker symbol translation rules — see [below](#ticker-rules) |
| `isin_tickers` | ISIN → ticker mappings for the BOSSA importer — see [below](#isin-mappings) |

Notes:

- There is **no per-project config** — every project shares this file.
- The last auto-refresh timestamp is **not** stored here; it lives per project
  in `data/projects.json` (`last_refresh`).
- Missing keys are filled from defaults on load. Edit via the UI
  (Sidebar → ⚙️ Settings) or by hand while the app is stopped.

## Ticker rules

Brokers often export ticker symbols in a format Yahoo Finance doesn't
understand (Xetra uses `.DE`, Warsaw uses `.WA`, XTB strips suffixes entirely).
Ticker rules rewrite symbols **when transactions are entered or imported**, so
prices resolve correctly.

Rules are evaluated **top-to-bottom, first match wins**. Each rule is
`PATTERN=REPLACEMENT`, one per line in *Settings → Ticker rules*:

| Form | Example | Meaning |
|------|---------|---------|
| Exact match | `AMZN.DE=AMZ.DE` | Rewrite `AMZN.DE` → `AMZ.DE` |
| Suffix swap (`*.`) | `*.PL=*.WA` | Any ticker ending `.PL` keeps its base, suffix becomes `.WA` (`SNT.PL` → `SNT.WA`) |
| Suffix strip (`.`) | `.US=` | Any ticker ending `.US` loses the suffix (`AAPL.US` → `AAPL`); an empty replacement deletes the matched part |

- `*` on the left stands for "any base symbol"; on the right it is replaced by
  that same base.
- A leading `.` without `*` matches a literal suffix to strip or rewrite.
- Symbols that match no rule pass through unchanged.
- Rules apply at entry time — transactions already stored in the ledger are
  not rewritten retroactively.

> Tip: use suffix rules to normalise a whole exchange at once (`*.PL=*.WA`)
> and exact rules for one-off fixes (`AMZN.DE=AMZ.DE`).

## ISIN mappings

BOSSA statements identify instruments by **ISIN** (e.g. `IE00B4L5Y983`), not by
ticker symbol. ISINs can't be looked up on Yahoo Finance directly, so map each
ISIN to the ticker Negotium should use for pricing. One `ISIN=TICKER` per line:

```
IE00B4L5Y983=IWDA.AS
US5949181085=MSFT.US
```

- When the BOSSA importer meets an ISIN it looks it up here and prices the
  position with the mapped ticker.
- ISINs without a mapping are reported as unresolved and skipped (the cash
  leg still imports) until you add a mapping and re-import via 🔄 Refresh.

## Supported currencies & exchange suffixes

Cash positions are `USD`, `EUR`, `PLN`. A stock's price currency is inferred
from its ticker suffix; unknown suffixes fall back to USD (with a warning):

| Currency | Ticker suffixes |
|---|---|
| USD | *(no suffix, or unknown suffix)* |
| EUR | `.DE` `.F` `.PA` `.MI` `.AS` `.BR` `.LS` `.MC` `.VI` `.IR` |
| PLN | `.WA` |
| GBP | `.L` |
| CHF | `.SW` |
| JPY | `.T` |
| CNY | `.SS` `.SZ` |
| HKD | `.HK` |
| SGD | `.SG` `.SI` |
| CAD | `.TO` |
| AUD | `.AX` |
| KRW | `.KS` |
| BRL | `.SA` |
| MXN | `.MX` |

FX rates come from Yahoo Finance (`{CCY}PLN=X` pairs plus `EURUSD=X`); MXN is
triangulated through USD. Details: [ARCHITECTURE.md](ARCHITECTURE.md#7-multi-currency-logic).

## Project registry — `data/projects.json`

```json
{
  "XTB": {
    "created_at": "2026-08-24T23:22:43.053550",
    "last_refresh": "2026-09-02",
    "watchlist": ["AMZN", "TSLA", "CRI.WA"]
  }
}
```

- `created_at` — when the project was created.
- `last_refresh` — drives the 24 h auto-refresh check.
- `watchlist` — the per-project watchlist symbols.

## Data files

| Path | Purpose | Safe to delete? |
|---|---|---|
| `data/config.json` | Global config | Resets to defaults |
| `data/projects.json` | Project registry, watchlists | Projects disappear from UI (directories remain) |
| `data/prices/{TICKER}/{YEAR}.json` | Shared price cache — stocks and FX pairs | ✓ re-downloaded |
| `data/ticker_names.json` | `{ticker: company name}` | ✓ re-fetched |
| `data/ticker_meta.json` | `{ticker: {sector, country, asset_class}}` | ✓ re-fetched |
| `data/dividends.json` | `{ticker: {date: dividend_per_share}}` | ✓ re-fetched |
| `data/earnings.json` | `{ticker: next earnings date}` | ✓ re-fetched |
| `data/{PROJECT}/transactions.jsonl` | **The ledger — source of truth** | ✗ this is your data |
| `data/{PROJECT}/balance.json` | Derived current holdings | rebuilt from ledger |
| `data/{PROJECT}/portfolio.jsonl` | Derived daily snapshots | rebuilt from ledger |
| `data/{PROJECT}/benchmarks_{CCY}.json` | Derived benchmark series | rebuilt on next chart render |
| `data/{PROJECT}/imports/{broker}/` | Uploaded statement files | kept for replay; deleting loses the re-import source |

`./start.sh --reset` wipes `data/` entirely.

