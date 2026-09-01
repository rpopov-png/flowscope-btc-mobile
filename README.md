# FlowScope BTC Cloud v1

Autonomous mobile-first FlowScope: cloud backend + iPhone PWA. No PC is required after deployment.

## Data
- Binance Spot BTCUSDT: price + taker-volume delta
- Binance USD-M BTCUSDT perpetual: futures taker-volume delta
- Bybit BTCUSDT linear: Open Interest + Funding fallback
- Farside: daily US spot BTC ETF net flow, 3-day sum, 5-day momentum
- Optional `COINGLASS_API_KEY` reserved for later aggregate OI / OI-weighted Funding integration

## Persistence
Set `DATABASE_URL` to PostgreSQL. Without it the app falls back to SQLite (not recommended for ephemeral cloud hosting).

## Render
`render.yaml` provisions a web service and Postgres. Use a paid always-on web plan if you want uninterrupted background collection; Render free web services can spin down after inactivity.

## iPhone
Open the HTTPS service URL in Safari -> Share -> Add to Home Screen.

## Important
The current z-score thresholds are engineering placeholders for pipeline validation. They are not statistically validated trading thresholds. Historical calibration/backtesting is still required before treating regime labels as an edge.
