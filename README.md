# Shadow v8

Modular trading engine scaffold.

Phase 1 includes the package structure, typed models, configuration, first-pass structure engines, stage scoring, fundamentals stubs, strategy decisions, research logging, dashboard JSON output, and a dry-run engine loop.

This version is intentionally dry-run first. Live execution adapters are separated behind execution modules so Bybit, IBKR, and future brokers can be connected without mixing execution plumbing into strategy logic.

Phase 2 adds paper execution. Set `SHADOW_EXECUTION_MODE=paper` to let approved v8 decisions create paper positions in `runtime/positions.json`; set it back to `scan_only` to disable that. Crypto live trading defaults to off until the v8 live adapter is wired and tested.

Phase 3 adds Telegram alerts for top setups, `MONITOR` setups, paper entries, and engine warnings. Alerts are off until `TELEGRAM_ALERTS_ENABLED=true` and Telegram credentials are present in `.env`.

Phase 4 adds Telegram command controls. With Telegram credentials enabled, use `/status`, `/top`, `/positions`, `/risk`, `/pause`, and `/resume` from the authorized chat. `/pause` blocks new entries but keeps the scanner and dashboard running.

Phase 5 adds paper trade lifecycle management. Paper positions now track hard stops, partial take profit, break-even moves, trailing stops, target exits, realized R, MAE/MFE, and closed trade history in the dashboard.

Phase 6 adds an operator test harness. Run `python -m shadow_v8.tools.paper_lifecycle_test` to create one fake paper trade, simulate partial/BE/target exit, refresh dashboard history, and send paper lifecycle Telegram alerts when enabled.

Phase 7 adds official SEC Company Facts fundamentals. The SEC adapter maps stock tickers to CIKs, fetches XBRL company facts, extracts quarterly revenue, EPS, margins, and free cash flow, then feeds the existing growth engine for sales/EPS acceleration scoring. Run `python -m shadow_v8.tools.fundamentals_smoke NVDA` to test one stock. Set `STOCK_FUNDAMENTALS_SOURCE=sec`, `STOCK_FUNDAMENTALS_SYMBOL=NVDA`, and `SEC_USER_AGENT` in `.env` to let the engine use SEC data for the dry-run stock filter.

Phase 8 adds stock daily/weekly market data for the technical engine. Set `STOCK_MARKET_DATA_SOURCE=stooq` to load daily candles and weekly resamples for stock Stage/VCP/W-M/base checks while SEC Company Facts handles fundamentals. The provider tries Stooq first, then Yahoo chart data as an automatic fallback. If both feeds are unavailable, the scanner marks the source as a demo fallback so it is visible in logs and dashboard data.

The dashboard shows scanner rankings, setup quality, engine health, risk limits, risk states, tracked paper/live positions, open PnL, and recent decisions.
