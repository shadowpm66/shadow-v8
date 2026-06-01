# Shadow v8 Context and Roadmap

## 1. Project Identity

- Project name: Shadow v8
- GitHub repo: `shadowpm66/shadow-v8`
- Local project folder known from Codex Desktop: `C:\Users\phili\Documents\Codex\2026-05-22\i-will-send-you-our-code`
- Main package folder: `shadow_v8`
- EC2 deployment folder: `~/shadow-v8`
- EC2 region observed during setup: `ap-southeast-2`
- EC2 instance name observed during setup: `ShadowVPS`
- Dashboard port: `8501`
- Engine service name on EC2: `shadow-v8-engine.service`
- Dashboard service name on EC2: `shadow-v8-dashboard.service`

GitHub workflow used so far:

- A Shadow v8 scaffold ZIP was uploaded to GitHub.
- EC2 downloaded the ZIP from GitHub using `wget`.
- EC2 unzipped it into `~/shadow-v8`.
- Later updates were also pushed or uploaded through the GitHub ZIP workflow.
- Codex Desktop also has a local project folder with the same package structure.

Current branch/worktree status:

- The exact local branch/worktree could not be verified from the current Codex Desktop environment.
- A previous local attempt to run `git status` failed because `git` was not available in this Windows shell environment.
- Treat the local Codex folder, GitHub repo, and EC2 deployment as three potentially different copies until explicitly verified.
- Before future coding, confirm which copy is canonical: local Codex workspace, GitHub `main`, or EC2 `~/shadow-v8`.

Mismatch risk:

- There is a real risk of local/GitHub/EC2 drift because code has moved through uploaded ZIP files, GitHub commits/uploads, and EC2 downloads.
- Do not assume EC2 contains every local change or that local files match GitHub without checking.

## 2. Current Shadow v8 Purpose

Shadow v8 is a modular rebuild of the older Shadow trading engine. The goal is to turn a powerful but patch-heavy single-file system into a clean, explainable, testable trading framework.

Older Shadow versions had many decision rules inside one large engine file:

- scoring thresholds
- strict/hybrid modes
- anti-fade
- polarity guard
- box gate
- ICT forced path
- fast path
- chop veto
- context memory
- HTF bias
- session gates
- reclaim override
- A+/S override
- risk trim
- confluence score
- exit management

The problem was not that each rule was bad. The problem was that too many rules could influence the same trade decision in different places. Shadow v8 separates responsibilities so the main engine coordinates modules rather than owning every decision.

High-level trading philosophy:

- Structure first, not indicator first.
- W structures are primary long structures.
- M structures are primary short, exit, or rotation structures.
- VCP, base, pivot, stage, volume, and fundamentals support the structure decision.
- Stage and setup quality should come before entry.
- Risk decision should come before execution.
- Execution should never change strategy logic.
- Every entered, skipped, reduced, and exited setup should be explainable.

Multi-asset goal:

- Crypto first: ETH, BTC, SOL, BNB, XRP, LINK, AVAX, and other liquid markets.
- Stocks next: growth stocks with stage, base, VCP, W/M, sales/revenue acceleration, EPS acceleration, and earnings risk filters.
- Gold, indices, commodities, and future assets should be possible through data/execution adapters.
- The engine should eventually route to Bybit, IBKR, and other brokers without rewriting strategy logic.

Stock/fundamental expansion goal:

- Add a real stock scanner that combines daily/weekly technical setup with business quality.
- Screen for revenue/sales acceleration, EPS acceleration, margin quality, free cash flow, relative strength, and earnings timing.
- Avoid new stock entries directly before earnings unless explicitly allowed by tested rules.

## 3. Current Stage Path / Build Roadmap

### Stage 0: scaffold / architecture

Status: Done

Files/modules involved:

- `shadow_v8/config.py`
- `shadow_v8/models.py`
- `shadow_v8/main.py`
- `shadow_v8/state_store.py`
- package folders under `data`, `context`, `structure`, `strategy`, `execution`, `fundamentals`, `research`, `telemetry`, `dashboard`, and `tools`

What currently works:

- Modular folder structure exists.
- Main package imports and runs.
- `python -m compileall shadow_v8` has been run successfully in the workflow.
- EC2 can run the package from `~/shadow-v8`.

What still needs completion:

- Confirm local/GitHub/EC2 copies match.
- Add stronger tests for every module boundary.
- Remove or complete placeholder logic module by module.

### Stage 1: scanner and dry-run

Status: Partial

Files/modules involved:

- `shadow_v8/main.py`
- `shadow_v8/data/bybit_market_data.py`
- `shadow_v8/data/market_data.py`
- `shadow_v8/data/scanner.py`
- `shadow_v8/context/stage_engine.py`
- `shadow_v8/structure/*`
- `shadow_v8/strategy/scorer.py`
- `shadow_v8/strategy/entry_policy.py`
- `shadow_v8/strategy/risk_manager.py`

What currently works:

- Crypto scanner runs on EC2.
- Current observed universe includes `ETHUSDT`, `BTCUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `LINKUSDT`, and `AVAXUSDT`.
- Scanner writes dashboard JSON files.
- Most current setups are rejected or skipped due to Stage/score/risk rules, which is expected in dry-run/paper mode.

What still needs completion:

- Expand universe discovery beyond a static configured list.
- Add stronger daily/weekly setup validation.
- Add replay validation before trusting scan scores.
- Add real market data adapter quality checks.

### Stage 2: dashboard and Telegram

Status: Partial to Done

Files/modules involved:

- `shadow_v8/dashboard/app.py`
- `shadow_v8/dashboard/static/style.css`
- `shadow_v8/telemetry/dashboard_writer.py`
- `shadow_v8/telemetry/telegram_bot.py`
- `shadow_v8/telemetry/telegram_alerts.py`
- `shadow_v8/telemetry/commands.py`

What currently works:

- Dashboard runs on EC2 through systemd.
- Dashboard shows scanner results, risk limits, engine state, open positions, closed paper trades, recent decisions, and risk detail.
- Dashboard is accessible through the EC2 public IP on port `8501` with a token query parameter.
- Telegram alerts/commands were configured and confirmed working by the user.

What still needs completion:

- Harden dashboard authentication.
- Avoid putting tokens in browser history long term.
- Consider restricting security group source IP for dashboard access.
- Add richer dashboard views for setup history, trades, equity curve, and research logs.

### Stage 3: paper trading lifecycle

Status: Partial

Files/modules involved:

- `shadow_v8/execution/paper_order_manager.py`
- `shadow_v8/execution/execution_router.py`
- `shadow_v8/strategy/exit_policy.py`
- `shadow_v8/strategy/position_sizer.py`
- `shadow_v8/telemetry/dashboard_writer.py`
- `shadow_v8/tools/paper_lifecycle_test.py`

What currently works:

- Paper mode is active.
- Live trading is currently OFF.
- A controlled paper lifecycle test was run using a test symbol.
- The test demonstrated entry, partial take profit, break-even move, final target exit, and closed paper trade display.
- Dashboard shows closed paper trades.

What still needs completion:

- Paper entries must be driven by real scanner decisions over time, not only controlled tests.
- Open PnL, MFE, MAE, partials, and trailing behavior need longer observation.
- Paper/live parity needs formal tests before live mode.

### Stage 4: replay/backtest/simulator layer

Status: Not Started / Placeholder

Files/modules involved:

- `shadow_v8/research/replay.py`
- `shadow_v8/research/simulator.py`
- `shadow_v8/research/setup_database.py`
- future `shadow_v8/tools/replay_smoke.py`
- future replay fixtures under `runtime/replay` or `tests/fixtures`

What currently works:

- Placeholder research modules exist.
- The broader architecture expects replay and simulation to use the same signal, scoring, risk, entry, and exit modules as paper/live.

What still needs completion:

- Implement replay data loading.
- Implement bar-by-bar simulation.
- Implement position lifecycle simulation.
- Implement MAE/MFE/R logging.
- Implement replay reports.
- Add smoke tests and fixtures.
- Ensure no duplicate strategy logic is added to simulator.

### Replay Layer Progress Update

- A minimal replay/simulator layer has been implemented.
- `shadow_v8/tools/replay_smoke.py` now runs both:
  - fixture-based replay from `tests/fixtures/replay_sample.json`
  - synthetic replay that triggers one controlled `ENTER`
- `python -m compileall shadow_v8` passed when run with the bundled Codex Python executable.
- Fixture replay processed 32 bars, 0 trades, and 23 skipped setups.
- Synthetic replay processed 91 bars, 1 trade, 49 skipped setups, and `net_r` 9.166667.
- The synthetic `net_r` is not strategy performance. It comes from a controlled fixture designed to prove replay plumbing, not from real market evidence.
- `shadow_v8/tools/replay_unit_smoke.py` was added.
- `replay_unit_smoke.py` validates:
  - fixture replay returns `ok=True`
  - `bars_processed` exists
  - skipped setups are recorded
  - synthetic LONG position opens/closes
  - synthetic SHORT position opens/closes
  - LONG and SHORT R-multiple math works
  - MAE/MFE fields exist
- `python -m compileall shadow_v8` passed for the replay unit smoke update when run with the bundled Codex Python executable.
- `replay_unit_smoke.py` output:
  - `fixture_bars_processed=32`
  - `fixture_skipped_setups=23`
  - LONG trade: `r_multiple=2.0`, `mae=-2.0`, `mfe=6.0`
  - SHORT trade: `r_multiple=2.0`, `mae=-2.0`, `mfe=6.0`
- This is still mechanical validation only, not trading edge or profitability evidence.
- The next safe step is not live trading. The next safe step is either adding a real historical CSV/JSON loader and running one real-market replay, or adding formal pytest tests later.

### Stage 5: live crypto execution

Status: Partial / Not Live

Files/modules involved:

- `shadow_v8/execution/bybit_order_manager.py`
- `shadow_v8/execution/execution_router.py`
- `shadow_v8/execution/reconcile.py`
- `shadow_v8/strategy/risk_manager.py`
- `shadow_v8/strategy/position_sizer.py`

What currently works:

- Execution module framework exists.
- Older Shadow v7 OrderManager was strong and included Bybit signing, order placement, reduce-only exits, partials, stop updates, and reconciliation.
- v8 has an execution router and Bybit order manager module structure.

What still needs completion:

- Confirm v8 Bybit adapter is fully wired.
- Confirm live order placement, reduce-only exits, stop updates, symbol filters, and reconciliation in testnet or minimal-size safe environment.
- Do not enable live execution until replay and paper validation are clean.

### Stage 6: stock scanner + fundamentals

Status: Partial

Files/modules involved:

- `shadow_v8/fundamentals/sec_company_facts.py`
- `shadow_v8/fundamentals/earnings_engine.py`
- `shadow_v8/fundamentals/earnings_calendar.py`
- `shadow_v8/fundamentals/growth_engine.py`
- `shadow_v8/fundamentals/stock_filter.py`
- `shadow_v8/fundamentals/ibkr_fundamentals.py`
- `shadow_v8/data/stooq_market_data.py`
- `shadow_v8/tools/fundamentals_smoke.py`
- `shadow_v8/tools/stock_scan_smoke.py`

What currently works:

- Stock scan smoke workflow exists.
- A stock universe has been tested with names such as NVDA, MSFT, AMZN, META, AVGO, LLY, TSLA, PLTR, CRWD, ANET, and SMCI.
- SEC company facts loading worked for some symbols after setting a proper SEC user agent.
- Fallback stock fundamentals path exists but remains fragile.

What still needs completion:

- Dynamic stock universe discovery.
- Reliable stock candles.
- Full fundamentals scoring.
- Real earnings calendar source.
- Stronger handling of SEC, Yahoo, Stooq, and IBKR data failures.
- Relative strength and sector leadership.

### Stage 7: IBKR paper/live stock execution

Status: Not Started / Placeholder

Files/modules involved:

- `shadow_v8/execution/ibkr_order_manager.py`
- `shadow_v8/data/ibkr_market_data.py`
- `shadow_v8/fundamentals/ibkr_fundamentals.py`

What currently works:

- Module placeholders exist.
- IBKR is recognized as the likely stock broker path.

What still needs completion:

- IBKR connection setup.
- IBKR paper account integration.
- Order routing.
- Position reconciliation.
- Symbol qualification.
- Data permissions and market data checks.
- Live stock trading safety controls.

### Stage 8: portfolio/risk expansion

Status: Partial

Files/modules involved:

- `shadow_v8/strategy/risk_manager.py`
- `shadow_v8/strategy/position_sizer.py`
- `shadow_v8/state_store.py`
- `shadow_v8/telemetry/dashboard_writer.py`

What currently works:

- Basic risk limits exist.
- Dashboard shows total positions, crypto positions, daily R limit, risk state, and risk detail.
- Paper account balance and paper risk settings exist.

What still needs completion:

- Portfolio heat.
- Correlation controls.
- Sector concentration.
- Crypto and stock exposure separation.
- Daily/weekly drawdown guard.
- Multi-position conflict rules.
- Risk state history.

### Stage 9: institutional-grade testing and reporting

Status: Not Started / Partial

Files/modules involved:

- `shadow_v8/research/*`
- `shadow_v8/telemetry/research_logger.py`
- `shadow_v8/telemetry/digest.py`
- future `tests/*`
- future report/export modules

What currently works:

- Dashboard and research logger modules exist.
- Scanner and paper lifecycle output can be observed.

What still needs completion:

- Unit tests.
- Integration tests.
- Replay tests.
- Paper/live parity tests.
- Reporting for win rate, expectancy, drawdown, MAE, MFE, R multiples, and setup classes.
- Evidence database for skipped and entered setups.

## 4. Current Completed Work

EC2 status:

- EC2 instance is running.
- Project folder on EC2 is `~/shadow-v8`.
- Python virtual environment exists at `~/shadow-v8/venv`.
- Engine and dashboard were converted into systemd services.
- Both services were observed as `active (running)`.

Dashboard status:

- Dashboard runs on port `8501`.
- Dashboard bind host is `0.0.0.0`.
- Dashboard displays:
  - top setup
  - engine state
  - risk limits
  - actions count
  - positions/PnL
  - risk state
  - crypto scanner table
  - open positions
  - recent decisions
  - closed paper trades
  - risk detail
- Dashboard endpoint format is:

```bash
http://<EC2_PUBLIC_IP>:8501/?token=<DASHBOARD_TOKEN>
```

Do not commit or share the real dashboard token.

Telegram status:

- Telegram credentials were configured through `.env`.
- Telegram alerts were enabled.
- User confirmed Telegram commands work.
- Do not commit Telegram bot token or chat ID.

Paper mode status:

- Execution mode observed as paper.
- Live trading observed as OFF.
- A controlled paper lifecycle test completed successfully.
- Closed paper trade appeared in dashboard.

Crypto scan status:

- Crypto scanner is running.
- Current scan loop has been observed writing dashboard data.
- Current scan interval observed in logs: 300 seconds.
- Crypto scan decisions currently mostly show `SKIP` / `REJECT`, risk `OFF`.

Stock scan status:

- Stock scan smoke scripts exist and have been run in the workflow.
- Stock universe testing has occurred with major growth names.
- Stock scan is not yet production-ready.

Fundamentals fallback status:

- SEC Company Facts path exists and can load data when a proper SEC user agent is configured.
- Earlier SEC failures occurred with HTTP 403 when access/user-agent was not correct.
- Fallback paths such as Yahoo/demo fallback have appeared in logs, but are not fully reliable.

Systemd/service status commands:

```bash
systemctl is-active shadow-v8-engine
systemctl is-active shadow-v8-dashboard
sudo systemctl status shadow-v8-engine --no-pager
sudo systemctl status shadow-v8-dashboard --no-pager
sudo journalctl -u shadow-v8-engine -n 80 --no-pager
sudo journalctl -u shadow-v8-dashboard -n 80 --no-pager
```

Current working EC2 commands:

```bash
cd ~/shadow-v8
source venv/bin/activate
python -m shadow_v8.main
python -m shadow_v8.dashboard.app
```

For services:

```bash
sudo systemctl restart shadow-v8-engine
sudo systemctl restart shadow-v8-dashboard
```

## 5. Current Unfinished Work

Unfinished or incomplete:

- `shadow_v8/research/replay.py`
- `shadow_v8/research/simulator.py`
- replay/backtest layer
- bar-by-bar simulator
- simulator/live parity tests
- live Bybit execution validation in v8
- IBKR execution
- full stock fundamentals pipeline
- real dynamic stock universe discovery
- real stock scoring and ranking
- earnings calendar reliability
- relative strength and sector leadership
- portfolio-level risk
- unit tests
- integration tests
- replay tests
- stronger dashboard security
- stronger data source error handling
- placeholder modules that need inspection before trusting

Fragile or duplicated logic risks:

- Simulator must not duplicate strategy rules.
- Paper, replay, and live must all call the same stage, structure, scorer, risk, entry, and exit modules.
- Stock fundamentals fallback has shown parser and access issues.
- Dashboard and engine both read/write runtime files, so file schema should stay stable.

## 6. Current Architecture / Module Framework

### Core / config / state

Responsibility:

- Global settings, environment configuration, shared models, state persistence, utility helpers.

Key files:

- `shadow_v8/config.py`
- `shadow_v8/models.py`
- `shadow_v8/state_store.py`
- `shadow_v8/utils.py`
- `shadow_v8/main.py`

Status:

- Implemented / partial.

Connection:

- Main engine loads config, scans markets, calls strategy modules, writes dashboard data, and controls services.

### Data

Responsibility:

- Market data fetching and scanning.

Key files:

- `shadow_v8/data/market_data.py`
- `shadow_v8/data/bybit_market_data.py`
- `shadow_v8/data/ibkr_market_data.py`
- `shadow_v8/data/stooq_market_data.py`
- `shadow_v8/data/candle_cache.py`
- `shadow_v8/data/scanner.py`

Status:

- Crypto Bybit scan is partial/working.
- Stock data is partial.
- IBKR data is placeholder/partial.

Connection:

- Feeds candles into context, structure, and strategy modules.

### Context

Responsibility:

- Market state and levels: stage, sessions, pivots, ADR/AWR, zones, relative strength, market regime.

Key files:

- `shadow_v8/context/stage_engine.py`
- `shadow_v8/context/sessions.py`
- `shadow_v8/context/pivots.py`
- `shadow_v8/context/adr_awr.py`
- `shadow_v8/context/zones.py`
- `shadow_v8/context/relative_strength.py`
- `shadow_v8/context/market_regime.py`

Status:

- Partial.

Connection:

- Provides stage, zones, context score, and market regime to the scorer and entry policy.

### Structure

Responsibility:

- W/M detection, base detection, VCP, pivot confirmation, nested structure, volume signature, box logic, indicators.

Key files:

- `shadow_v8/structure/wm_detector.py`
- `shadow_v8/structure/base_engine.py`
- `shadow_v8/structure/vcp_engine.py`
- `shadow_v8/structure/pivot_confirmation.py`
- `shadow_v8/structure/nested_structure.py`
- `shadow_v8/structure/volume_signature.py`
- `shadow_v8/structure/box_engine.py`
- `shadow_v8/structure/indicators.py`

Status:

- Partial.

Connection:

- Produces structure signal and setup evidence for scoring, risk, and entry decisions.

### Strategy

Responsibility:

- Combine evidence, decide entry/wait/skip, size risk, and manage exits.

Key files:

- `shadow_v8/strategy/scorer.py`
- `shadow_v8/strategy/entry_policy.py`
- `shadow_v8/strategy/risk_manager.py`
- `shadow_v8/strategy/position_sizer.py`
- `shadow_v8/strategy/exit_policy.py`

Status:

- Partial.

Connection:

- Central decision layer for scanner, paper, replay, and future live execution.

### Fundamentals

Responsibility:

- Stock fundamentals, earnings filters, growth scoring, stock filter.

Key files:

- `shadow_v8/fundamentals/sec_company_facts.py`
- `shadow_v8/fundamentals/earnings_engine.py`
- `shadow_v8/fundamentals/earnings_calendar.py`
- `shadow_v8/fundamentals/growth_engine.py`
- `shadow_v8/fundamentals/stock_filter.py`
- `shadow_v8/fundamentals/ibkr_fundamentals.py`

Status:

- Partial.

Connection:

- Supports stock scanner and stock risk quality. It should not replace structure.

### Execution

Responsibility:

- Broker adapters, paper execution, routing, reconciliation.

Key files:

- `shadow_v8/execution/paper_order_manager.py`
- `shadow_v8/execution/bybit_order_manager.py`
- `shadow_v8/execution/ibkr_order_manager.py`
- `shadow_v8/execution/execution_router.py`
- `shadow_v8/execution/reconcile.py`

Status:

- Paper partial/working.
- Bybit partial/not live validated.
- IBKR placeholder/not started.

Connection:

- Receives approved execution decisions. It should not create strategy decisions.

### Research / replay / backtesting

Responsibility:

- Setup database, replay, simulation, evidence-based validation.

Key files:

- `shadow_v8/research/setup_database.py`
- `shadow_v8/research/replay.py`
- `shadow_v8/research/simulator.py`

Status:

- Placeholder / not started.

Connection:

- Must call the same strategy modules as paper/live.

### Telemetry

Responsibility:

- Telegram, dashboard writer, digest, research logging, commands.

Key files:

- `shadow_v8/telemetry/telegram_bot.py`
- `shadow_v8/telemetry/telegram_alerts.py`
- `shadow_v8/telemetry/commands.py`
- `shadow_v8/telemetry/dashboard_writer.py`
- `shadow_v8/telemetry/research_logger.py`
- `shadow_v8/telemetry/digest.py`

Status:

- Partial/working for dashboard and Telegram.

Connection:

- Reports engine state and decisions. It should not decide trades.

### Dashboard

Responsibility:

- Web monitor for scanner, risk, positions, PnL, recent decisions, and paper trade history.

Key files:

- `shadow_v8/dashboard/app.py`
- `shadow_v8/dashboard/static/style.css`

Status:

- Working / partial.

Connection:

- Reads runtime JSON files written by telemetry.

### Tools / tests / deployment

Responsibility:

- Smoke scripts, deployment docs, environment examples, future test suite.

Key files:

- `shadow_v8/tools/fundamentals_smoke.py`
- `shadow_v8/tools/stock_scan_smoke.py`
- `shadow_v8/tools/paper_lifecycle_test.py`
- `requirements.txt`
- `.env.example`
- `DEPLOY_AWS.md`
- `README.md`

Status:

- Smoke tools partial/working.
- Formal tests not complete.

Connection:

- Used to validate modules and EC2 behavior.

## 7. Trading Strategy Logic

### Currently implemented or partially working

- W/M structure scanning exists.
- W structures map to long bias.
- M structures map to short/exit/rotation bias.
- Weekly and daily stage labels exist.
- Stage logic is used in scanner scoring.
- VCP score exists.
- Base score exists.
- Pivot confirmation field exists.
- Structure score is shown in logs and dashboard.
- Risk state can be `FULL`, `REDUCED`, `DEFENSIVE`, or `OFF`.
- Entry decisions currently produce `ENTER`, `MONITOR`, `SKIP`, or similar actions.
- Most current crypto scanner decisions are `SKIP`/`REJECT`.
- Dashboard shows risk state and reason.
- Paper execution supports a controlled lifecycle with target close.

### Partially implemented

- W/M rotation.
- VCP tightness.
- Base detection.
- Pivot confirmation.
- Nested W within W and M within M.
- Volume dry-up.
- Breakout volume.
- Stage 2 / moving average trend qualification.
- Confluence scoring.
- Exit policy.
- Partial take profit.
- Break-even behavior.
- Trailing/locking logic.
- Opposite-structure exit.

These need replay and paper validation before live use.

### Intended but not fully implemented

- Clean setup hierarchy:
  1. Market state
  2. Stage permission
  3. Daily setup
  4. VCP tightness
  5. Structure signal
  6. Entry confirmation
  7. Risk decision
  8. Execution
  9. Exit management
  10. Research logging
- Daily open confluence.
- Session levels.
- Previous session open/close.
- ADR/AWR.
- Psychological high/low.
- Pivot zones.
- Vector candle zones and unrecovered vectors.
- Full risk tiering by timeframe alignment.
- Exit ladder priority:
  - hard stop
  - emergency flatten
  - failed breakout
  - opposite structure
  - stage/VWAP deterioration
  - partial take profit
  - break-even
  - profit lock
  - runner trail

## 8. Fundamentals Framework

### Currently implemented

- SEC Company Facts module exists.
- SEC user-agent configuration has been used.
- Fundamentals smoke testing has loaded data for some symbols.
- Revenue quarter count and EPS quarter count appear in logs.
- Fundamental grades such as A, B, F, and UNKNOWN appear in stock scan output.
- Stock filter can reject weak fundamentals.
- Earnings block flag exists in output.

### Stub / placeholder / partial

- EPS growth.
- EPS acceleration.
- Revenue/sales growth.
- Revenue acceleration.
- Earnings calendar.
- Earnings block days.
- Margin trend.
- Free cash flow checks.
- Relative strength.
- IBKR fundamentals.
- Yahoo/Stooq fallback reliability.

### Planned next

- Reliable earnings calendar source.
- Earnings avoidance rules for upcoming earnings.
- Margin expansion.
- FCF quality.
- ROE/ROIC.
- Debt risk.
- Dilution/share count risk.
- Valuation sanity filter.
- Sector and market leadership.
- Full dynamic stock universe discovery.
- Long-only stock default, with optional shorts only after explicit testing.

Current data sources used or touched:

- SEC Company Facts.
- Yahoo-style fallback or demo fallback.
- Stooq market data module.
- IBKR placeholder modules.

Planned data sources:

- SEC Company Facts for fundamentals.
- IBKR for stock data and execution if configured.
- A reliable earnings calendar provider.
- Possibly paid data later for institutional-grade coverage.

## 9. Testing and Validation

Tests or checks that have been run in the workflow:

- Python dependency installation on EC2.
- Package import/compile checks.
- Crypto scanner dry-run.
- Stock scan smoke workflow.
- Fundamentals smoke workflow.
- Controlled paper lifecycle test.
- Dashboard service startup.
- Engine service startup.
- Telegram command/alert confirmation by user.

Useful smoke commands:

```bash
cd ~/shadow-v8
source venv/bin/activate
python -m compileall shadow_v8
python -m shadow_v8.tools.stock_scan_smoke
python -m shadow_v8.tools.fundamentals_smoke NVDA
python -m shadow_v8.tools.paper_lifecycle_test
```

Useful EC2 service checks:

```bash
systemctl is-active shadow-v8-engine
systemctl is-active shadow-v8-dashboard
sudo journalctl -u shadow-v8-engine -n 80 --no-pager
sudo journalctl -u shadow-v8-dashboard -n 80 --no-pager
```

Known pass results:

- Engine service active.
- Dashboard service active.
- Dashboard accessible.
- Telegram commands working.
- Paper lifecycle test wrote a closed trade.
- SEC fundamentals can load for some symbols when configured correctly.

Known failures or issues:

- SEC returned HTTP 403 before proper access/user-agent handling.
- Yahoo/fallback path has shown parser/fallback issues.
- Dashboard can fail if manually started while systemd service already owns port 8501.
- Local branch/worktree could not be verified in Codex Desktop due to missing Git command.

Missing tests:

- Unit tests for every structure module.
- Unit tests for scorer, risk manager, entry policy, and exit policy.
- Integration tests for scanner to dashboard writer.
- Replay tests.
- Simulator tests.
- Paper/live parity tests.
- Bybit testnet or minimal-size validation tests.
- IBKR paper tests.

Simulator/live parity rule:

- Simulator must not reimplement strategy logic.
- Simulator should feed historical bars into the same engines used by paper/live:
  - context
  - structure
  - scorer
  - risk manager
  - entry policy
  - exit policy

## 10. Current Risks and Warnings

Live trading safety:

- Live trading should remain OFF until replay, paper, and smoke validation are clean.
- Do not enable live Bybit or IBKR execution from the current state without targeted tests.
- Paper mode must prove order lifecycle, exits, partials, stops, and risk state first.

Placeholder modules:

- Several modules exist but may be placeholders or first-pass implementations.
- Do not assume a module is production-ready because the file exists.

Duplicate/parallel logic risks:

- Avoid creating separate strategy rules inside simulator.
- Avoid one scoring path for scanner and another for paper/live.
- Avoid letting execution modules decide trade quality.

GitHub/worktree/branch risks:

- Local Codex workspace, GitHub repo, and EC2 folder may not match.
- Always verify file contents and deployment source before coding.

Dashboard/security risks:

- Dashboard uses token query parameter.
- Token should not be committed or shared.
- EC2 security group access should ideally be restricted to known IPs.
- `.env` must never be committed.

Overcomplexity risks:

- Shadow v8 should stay modular.
- Do not add another patch layer that reintroduces hidden conflicting logic.

Long-thread/compaction risk:

- This file exists because the prior chat became too long and was compacted.
- Future tasks should be smaller and module-specific.

Known bugs or fragility:

- SEC access can fail if user-agent or rate limits are wrong.
- Fallback stock parser can fail.
- Dashboard port collision can happen if manual process and systemd service both run.
- Current stock scanner is not yet a production-grade scanner.

## 11. Current Exact Next Step

The single best next engineering step is still the replay/backtest/simulator layer, but only after the user explicitly asks to resume coding.

Recommended next module to inspect first:

- `shadow_v8/research/simulator.py`
- `shadow_v8/research/replay.py`

Why it matters:

- Replay/backtest is the evidence layer.
- It validates W/M, VCP, stage, pivot confirmation, entry policy, risk, and exits before live trading.
- It protects against accidental overfitting and live-only bugs.

Files that should be touched next when coding resumes:

- `shadow_v8/research/simulator.py`
- `shadow_v8/research/replay.py`
- possibly `shadow_v8/tools/replay_smoke.py`
- possibly `README.md` or `DEPLOY_AWS.md` for documentation

Files that should not be touched for that step unless necessary:

- Bybit live execution
- IBKR live execution
- strategy rules
- dashboard authentication
- `.env`

Command to run after that future implementation:

```bash
python -m compileall shadow_v8
python -m shadow_v8.tools.replay_smoke
```

Expected output:

- compile completes without syntax errors.
- replay smoke prints number of bars processed.
- replay smoke prints entries, exits, net R, win rate, MAE/MFE summary.
- replay results are written to a runtime output file without touching live execution.

## 12. To-Do List

Immediate next 10 tasks:

1. Verify local/GitHub/EC2 code copies match.
2. Inspect `shadow_v8/research/simulator.py`.
3. Inspect `shadow_v8/research/replay.py`.
4. Define replay input format for candles.
5. Implement minimal bar-by-bar replay loop.
6. Make replay call existing context/structure/scorer/risk/entry/exit modules.
7. Add one replay smoke tool.
8. Add one small replay fixture.
9. Write replay output JSON with trades, skipped setups, MAE/MFE, and R.
10. Run compile and replay smoke only.

Medium-term next 10 tasks:

1. Add unit tests for stage engine.
2. Add unit tests for W/M detector.
3. Add unit tests for VCP engine.
4. Add tests for pivot confirmation.
5. Add tests for entry policy.
6. Add tests for risk manager.
7. Add tests for exit policy.
8. Add paper/live parity checks.
9. Add dashboard replay summary section.
10. Add research database storage for skipped setups.

Later / institutional-grade next 10 tasks:

1. Build full replay report with equity curve.
2. Add walk-forward testing.
3. Add multi-symbol portfolio simulation.
4. Add regime-based performance analysis.
5. Add setup-class expectancy report.
6. Add stock universe discovery.
7. Add reliable earnings calendar.
8. Add IBKR paper execution.
9. Add Bybit testnet/min-size validation.
10. Add production monitoring and alert audit logs.

## 13. Handoff Instructions for a New Codex Chat

Start a new Codex Desktop chat like this:

1. Open the repo/folder:

```text
C:\Users\phili\Documents\Codex\2026-05-22\i-will-send-you-our-code
```

2. Read this file first:

```text
SHADOW_V8_CONTEXT_AND_ROADMAP.md
```

3. Verify the project tree before coding:

```text
shadow_v8/
requirements.txt
README.md
DEPLOY_AWS.md
.env.example
```

4. Verify branch/worktree if Git is available.

5. Confirm whether the active source of truth is:

- local Codex workspace
- GitHub `shadowpm66/shadow-v8`
- EC2 `~/shadow-v8`

6. Do not touch:

- `.env`
- API keys
- Telegram tokens
- Bybit credentials
- account IDs
- live execution settings

7. Before coding, inspect the exact module requested.

8. Keep future tasks small:

- one module
- one smoke test
- one deployment action at most

9. Avoid a huge stuck thread:

- update this roadmap after major changes
- keep implementation requests focused
- do not combine replay, live trading, dashboard, and fundamentals in one request

10. Before deploying to EC2:

- run compile/smoke locally or in EC2 venv
- verify services
- restart only the requested service
- do not change security groups or credentials unless explicitly asked

## 14. Permanent Shadow Rules

- Structure first, not indicator first.
- W means long structure.
- M means short, exit, or rotation structure.
- W/M rotation stays central.
- VCP, base, pivot, and stage logic support structure. They do not replace it.
- Fundamentals support stock selection and risk quality. They do not replace price structure.
- HTF disagreement should usually reduce risk, not blindly block every trade.
- Stage comes before structure.
- Setup comes before entry.
- Risk comes before execution.
- Execution never changes strategy.
- Logs must explain entered trades.
- Logs must explain skipped trades.
- Logs must explain reduced-risk trades.
- Logs must explain exits.
- Simulator, paper, and live must use the same signal, scoring, risk, entry, and exit engines.
- No live trading unless paper, smoke, and replay validation are clean.
- No API keys, Telegram tokens, Bybit keys, account numbers, or private credentials in the repo.
