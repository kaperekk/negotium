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
  "ticker_rules": ["AMZN.DE=AMZ.DE", "*.UK=*.L", "*.PL=*.WA", "*.US="],
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

### XTB suffix mapping (country codes → Yahoo exchange codes)

XTB exports **country-code suffixes**, Yahoo Finance expects **city / exchange
codes**. Rules matching XTB's codes live in `data/config.json`; ships with the
full set below. Two behaviours worth knowing:

- Rules **don't chain** — the rewritten result is not re-matched, so a Greek
  `*.GR=*.AT` ticker is safe even though `*.AT=*.VI` also exists (Athens vs
  Austria use `.AT` on opposite sides).
- Unused wildcard rules are **harmless** — a rule only fires when a ticker
  actually carries that suffix.
- No rule is needed when both sides use the same code: `.DE` (Xetra), `.HK`
  (Hong Kong).

| XTB (country) | Yahoo (exchange) | Market | Example |
|---|---|---|---|
| `.US` | *(none)* | United States | `AAPL.US` → `AAPL` |
| `.UK` | `.L` | United Kingdom (London) | `SHEL.UK` → `SHEL.L` |
| `.PL` | `.WA` | Poland (Warsaw) | `CDR.PL` → `CDR.WA` |
| `.NL` | `.AS` | Netherlands (Amsterdam) | `ASML.NL` → `ASML.AS` |
| `.FR` | `.PA` | France (Paris) | `OR.FR` → `OR.PA` |
| `.ES` | `.MC` | Spain (Madrid) | `SAN.ES` → `SAN.MC` |
| `.IT` | `.MI` | Italy (Milan) | `ISP.IT` → `ISP.MI` |
| `.PT` | `.LS` | Portugal (Lisbon) | `EDP.PT` → `EDP.LS` |
| `.BE` | `.BR` | Belgium (Brussels) | `ABI.BE` → `ABI.BR` |
| `.AT` | `.VI` | Austria (Vienna) | `OMV.AT` → `OMV.VI` |
| `.CH` | `.SW` | Switzerland (Zurich) | `NESN.CH` → `NESN.SW` |
| `.IE` | `.IR` | Ireland (Dublin) | `BIR.IE` → `BIR.IR` |
| `.SE` | `.ST` | Sweden (Stockholm) | `VOLV-B.SE` → `VOLV-B.ST` |
| `.NO` | `.OL` | Norway (Oslo) | `EQNR.NO` → `EQNR.OL` |
| `.DK` | `.CO` | Denmark (Copenhagen) | `NOVO-B.DK` → `NOVO-B.CO` |
| `.FI` | `.HE` | Finland (Helsinki) | `NOKIA.FI` → `NOKIA.HE` |
| `.CZ` | `.PR` | Czechia (Prague) | `CEZ.CZ` → `CEZ.PR` |
| `.HU` | `.BD` | Hungary (Budapest) | `OTP.HU` → `OTP.BD` |
| `.GR` | `.AT` | Greece (Athens) | `HTO.GR` → `HTO.AT` |
| `.TR` | `.IS` | Türkiye (Istanbul) | `THYAO.TR` → `THYAO.IS` |
| `.JP` | `.T` | Japan (Tokyo) | `7203.JP` → `7203.T` |
| `.SG` | `.SI` | Singapore | `D05.SG` → `D05.SI` |
| `.DE` | `.DE` | Germany (Xetra) — same code | — |
| `.HK` | `.HK` | Hong Kong — same code | — |

Each translated ticker is priced in the currency of its **Yahoo** suffix — see
the [currency table](#supported-currencies--exchange-suffixes) below.

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
| EUR | `.DE` `.F` `.PA` `.MI` `.AS` `.BR` `.LS` `.MC` `.VI` `.IR` `.HE` `.AT` |
| PLN | `.WA` |
| GBP | `.L` |
| CHF | `.SW` |
| SEK | `.ST` |
| NOK | `.OL` |
| DKK | `.CO` |
| CZK | `.PR` |
| HUF | `.BD` |
| TRY | `.IS` |
| JPY | `.T` |
| CNY | `.SS` `.SZ` |
| HKD | `.HK` |
| SGD | `.SG` `.SI` |
| CAD | `.TO` |
| AUD | `.AX` |
| KRW | `.KS` |
| BRL | `.SA` |
| MXN | `.MX` |

FX rates come from Yahoo Finance (`{CCY}PLN=X` pairs plus `EURUSD=X`); MXN and
HUF are triangulated through USD (Yahoo has no direct `HUFPLN=X` pair).
Details: [ARCHITECTURE.md](ARCHITECTURE.md#7-multi-currency-logic).

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

