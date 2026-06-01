# Shadow v8 Replay Update

## 1. What Was Added to replay.py

- Added a minimal `Replay` coordinator that processes historical candles bar by bar.
- Calls the existing Shadow modules:
  - `StageEngine`
  - `BaseEngine`
  - `VcpEngine`
  - `WmDetector`
  - `NestedStructureDetector`
  - `PivotConfirmationEngine`
  - `Scorer`
  - `RiskManager`
  - `EntryPolicy`
- Sends active positions through the simulator on each bar.
- Records non-entry decisions as skipped setups.
- Opens a synthetic position only when the existing `EntryPolicy` returns `ENTER`.
- Returns a structured summary with `ok`, symbol, bars processed, trades, skipped setups, win rate, and net R.

## 2. What Was Added to simulator.py

- Added a minimal synthetic position lifecycle manager.
- Uses fixed synthetic quantity of `1.0`.
- Opens a synthetic `PositionState` from an `EntryDecision`.
- Calls the existing `ExitPolicy` on each bar.
- Tracks MAE and MFE while the synthetic position is open.
- Closes on `ExitPolicy` hard stop.
- Closes any remaining open position at the end of replay.
- Calculates per-trade R-multiple and aggregate win rate / net R.

## 3. What replay_smoke.py Proves

- The replay layer can process one synthetic candle stream bar by bar.
- Replay calls the existing stage, structure, scoring, risk, entry, and exit modules.
- A synthetic trade can be opened through the real `EntryPolicy` path.
- The simulator can track MAE/MFE and calculate R-multiple.
- The smoke command runs without touching live execution, brokers, credentials, Telegram, dashboard auth, or EC2.

## 4. What replay_smoke.py Does NOT Prove

- It does not prove the strategy is profitable.
- It does not prove W/M, VCP, base, pivot, or stage rules are correct.
- It does not prove live or paper execution parity.
- It does not test real market data quality.
- It does not test multiple symbols, portfolios, slippage, fees, partial exits, trailing stops, or broker behavior.

## 5. Why the Synthetic +9.16R Result Is Not Strategy Performance

The +9.16R result comes from a hand-built synthetic candle fixture designed to prove plumbing. The candles were shaped so the existing modules would eventually produce one `ENTER` and one completed trade. This is useful for validating replay wiring, but it has no statistical meaning and should not be treated as evidence of edge, expectancy, or real market performance.

## 6. Next Safe Replay Improvement

The replay layer now includes gate analytics (`schema_version=1.5.1`) so skipped setups and trades can be reviewed by gate status, blocker, watch reason, warning, confirmation, and allowed non-entry reason. Gate status now separates `BLOCK`, `WATCH`, and `ALLOW`, which lets replay distinguish invalid setups from developing setups that should be monitored. The next safe improvement is to run real historical CSV data, starting with ETHUSDT 15m, and use the gate analytics to tune overly strict or overly loose strategy rules before live execution.

Replay validation can be run against one CSV file or a folder of CSV files:

```text
python -m shadow_v8.tools.replay_validate data/replay --min-bars 120 --output-dir runtime/replay_reports
```

CSV files should include `timestamp,open,high,low,close,volume`. Reports are written under `runtime/`, which is intentionally ignored by Git.

Public Bybit OHLCV candles can be exported for replay without API keys:

```text
python -m shadow_v8.tools.bybit_replay_export --symbol ETHUSDT --interval 15 --limit 1000 --validate --min-bars 120
```

The exporter writes CSV files under `runtime/replay_data/`, then optionally runs replay validation on the exported file. This is intended for historical validation only; it does not touch live trading, broker credentials, Telegram, dashboard auth, or EC2.

Replay validation summaries include `allowed_entries`, `allowed_non_entries`, and `top_allowed_non_entry_reason`. This is useful when a setup passes the trade gate but still does not enter, such as a valid short setup being skipped while replay is running in long-only mode. Add `--allow-short` when validating two-way crypto or forex behavior.

## 7. Files Changed

- `shadow_v8/research/replay.py`
- `shadow_v8/research/simulator.py`
- `shadow_v8/tools/replay_csv.py`
- `shadow_v8/tools/replay_smoke.py`
- `shadow_v8/tools/replay_unit_smoke.py`
- `shadow_v8/tools/replay_validate.py`
- `shadow_v8/tools/replay_validate_smoke.py`
- `shadow_v8/tools/bybit_replay_export.py`
- `SHADOW_V8_REPLAY_UPDATE.md`

## 8. Smoke Test Results

Commands run with the bundled Codex Python executable because `python` was not available on PATH in the Windows shell:

```text
python -m compileall shadow_v8
```

Result: passed.

```text
python -m shadow_v8.tools.replay_smoke
```

Output:

```text
Replay smoke complete (fixture)
ok=True
schema_version=1.5.1
trades=0
skipped_setups=23
gate_status_counts={'BLOCK': 23}
gate_allow_rate=0.0
gate_watch_rate=0.0
gate_top_blockers=[{'name': 'stage_blocks_long', 'count': 14}, ...]
gate_top_watch_reasons=[{'name': 'immature_base_or_vcp', 'count': 20}, ...]
gate_validation_notes=['No setups passed the trade gate', ...]
```
