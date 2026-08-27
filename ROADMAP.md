# Negotium - Feature Roadmap

## Planned Features

### Correlation Matrix
- [ ] Compute pairwise correlation of daily returns across all holdings
- [ ] Display as interactive heatmap (Plotly)
- [ ] Configurable lookback period (1M, 3M, 6M, 1Y, All)
- [ ] Filter by asset class / currency

### Allocation Breakdown
- [ ] Sector allocation (GICS mapping via ticker)
- [ ] Geographic allocation (country of listing / revenue exposure)
- [ ] Asset class allocation (Equity, Bond, Cash, Crypto, Commodity)
- [ ] Currency exposure breakdown
- [ ] Drift detection vs target allocation

### Drawdown Analysis
- [ ] Maximum drawdown (peak-to-trough)
- [ ] Current drawdown from peak
- [ ] Drawdown duration & recovery time
- [ ] Ulcer Index / Pain Ratio
- [ ] Underwater chart (cumulative drawdown over time)
- [ ] Per-ticker and portfolio-level

### Watchlist with Price Alerts
- [ ] Add/remove tickers to watchlist (separate from portfolio)
- [ ] Price alerts: above/below target, % change, moving average cross
- [ ] Notification channels: in-app toast, email, webhook
- [ ] Alert history log
- [ ] Quick-add from watchlist to portfolio

### Dividend Indicator
- [ ] Upcoming ex-dividend dates for holdings
- [ ] Dividend yield (TTM / forward)
- [ ] Yield on cost (based on avg purchase price)
- [ ] Dividend calendar view (monthly)
- [ ] Dividend growth streak / history
- [ ] Total dividend income (YTD, All-time)
- [ ] DRIP tracking (reinvested vs cash)

---

## Implementation Notes

### Data Sources
- Yahoo Finance for prices/dividends (already integrated)
- Sector/Geographic: Need external mapping (yfinance `info` or static CSV)
- Alerts: Streamlit doesn't support background workers → use cron + email/webhook

### Architecture
- New module: `analytics.py` for correlation, allocation, drawdown
- New module: `watchlist.py` for watchlist + alerts
- New module: `dividends.py` for dividend tracking
- Extend `storage.py` with watchlist/alert persistence
- Add scheduled job (cron) for alert evaluation

### UI Placement
- Correlation/Allocation: New "Analytics" tab or expander in dashboard
- Drawdown: Extend portfolio chart with underwater view toggle
- Watchlist: New sidebar section or separate page
- Dividends: Holdings table column + dedicated dividend calendar view

---

## Priority Order
1. **Drawdown Analysis** - High value, reuses existing price data
2. **Allocation Breakdown** - Visual, easy to implement with static mappings
3. **Correlation Matrix** - Requires return series, medium complexity
4. **Dividend Indicator** - Uses existing Yahoo data, high user value
5. **Watchlist + Alerts** - Requires background job infrastructure

---

## Dependencies
- `scipy` or manual correlation (numpy.corrcoef)
- Sector mapping: static JSON or `yfinance` info calls (cached)
- Background scheduler: `apscheduler` or system cron
- Email: `smtplib` or webhook POST