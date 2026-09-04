# Usage guide

Day-to-day operation of Negotium: projects, the sidebar, the dashboard, and
data refresh behaviour.

Part of the Negotium docs: [README](README.md) · [IMPORTS](IMPORTS.md) · [CONFIG](CONFIG.md) · [ARCHITECTURE](ARCHITECTURE.md)

## Projects

A project is an isolated data space — its own transaction ledger, balance,
portfolio snapshots, and benchmark series. Use one project per broker account
or strategy (e.g. `XTB`, `Retirement`).

- **Switch** — sidebar → *Project* dropdown.
- **Create** — sidebar → *Project* → **➕ New project**.
- Each project is a directory under `data/` (see [CONFIG.md](CONFIG.md#data-files)).
- The global config, price cache, and ticker metadata are **shared** by all projects.

## Sidebar controls

| Control | What it does |
|---|---|
| **Project** | Switch between projects or create a new one |
| **Currency** | Display currency: `PLN` / `EUR` / `USD` (initial value from config) |
| **Date range** | Start and end dates for the chart window |
| **⚙️ Settings** | Theme toggle (dark/light), ticker rules, ISIN mappings |
| **➕ Add transaction** | Manual single-date transaction entry |
| **📥 Import statement** | Upload XTB / BOSSA / Custom files (see [IMPORTS.md](IMPORTS.md)) |
| **🔄 Refresh** | Replay all stored import files, re-download current-year prices, rebuild |

## Adding a transaction manually

1. Sidebar → **➕ Add transaction**
2. Pick a date (today or any past date)
3. Add entries: a ticker and an amount — positive = buy / cash in,
   negative = sell / cash out
4. Mark **account operation** if this is a pure deposit or withdrawal
5. Submit

Rules worth knowing:

- One calendar date can hold many entries (a stock buy plus its cash leg, an
  FX swap, several fills on the same day).
- Past-dated entries are inserted at the correct chronological position; the
  ledger is rewritten and the portfolio recomputed from that date.
- Ticker symbols pass through your ticker rules (see
  [CONFIG.md](CONFIG.md#ticker-rules)) — enter symbols the way your broker
  writes them.
- `account_operation` entries always count toward invested capital; plain
  cash-only transactions count too; stock buys/sells never do.

## Dashboard

Top to bottom:

- **Metric cards** — current value, contributions, best performer, CAGR, IRR,
  plus a P&L toggle (amount ⇄ percent).
- **Portfolio chart** — portfolio value over time with the invested-capital
  reference line and optional benchmark overlays (S&P 500, NASDAQ 100, FTSE
  All-World, Emerging Markets, Bitcoin, Gold). Toggle amount / percent mode.
- **Holdings table** — one row per ticker with amount, price, value and P&L;
  **click a row** to open the trade-history dialog for that ticker (every
  transaction, dividends, price history chart).
- **Allocation breakdown** — current holdings as donut charts grouped by
  sector, geography, asset class, and currency (from cached ticker metadata).
- **Drawdown analysis** — peak-to-trough statistics plus an "underwater"
  chart of the portfolio series.
- **Watchlist** — bottom of page, see below.

## Watchlist

- Paste a Yahoo Finance link or a raw ticker symbol at the bottom of the page.
- Each entry shows the current price, change over the visible window, and a
  sparkline.
- Entries persist **per project** (stored in `data/projects.json`).
- Quotes are warmed in parallel and cached like any other price data.

## Refreshing data

- **Automatic** — when the last refresh is ≥ 24 h old, the app refreshes on
  startup: current-year prices are re-downloaded (historical years are never
  re-fetched) and the portfolio resumes from its last cached snapshot.
- **Manual (🔄 Refresh)** — additionally re-imports every file already uploaded
  to `data/{PROJECT}/imports/{broker}/`, then rebuilds. Safe: already-imported
  rows are skipped as duplicates.
- **After any transaction change** — the portfolio is invalidated from that
  date and only the affected tail is recomputed.

## Display currency and date range

- Switching PLN ⇄ EUR ⇄ USD reuses stored snapshots per currency — only the
  first switch computes.
- Changing the chart date range is instant: it slices the already-computed
  series (no I/O, no recomputation).
- The engine supports daily and weekly snapshots; the UI currently uses daily.

## Data ownership

Everything is plain human-readable files under `data/` — back up the folder
and you have backed up the app. `data/{PROJECT}/transactions.jsonl` is the
source of truth; every other project file is derived and can be rebuilt.
See [CONFIG.md](CONFIG.md#data-files) for a per-file reference.

