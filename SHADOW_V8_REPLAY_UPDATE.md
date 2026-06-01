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

The next safe improvement is to add a tiny neutral fixture or fixture loader that reads candle data from a local JSON/CSV file, then compare expected replay fields in a smoke or unit-style check. Keep it one symbol and one timeframe first, and continue using the existing strategy modules without duplicating strategy logic inside replay or simulator.

## 7. Files Changed

- `shadow_v8/research/replay.py`
- `shadow_v8/research/simulator.py`
- `shadow_v8/tools/replay_smoke.py`
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
Replay smoke complete
ok=True
symbol=TESTUSDT
bars_processed=91
trades=1
skipped_setups=49
win_rate=1.0
net_r=9.166667
trade_1: direction=LONG entry=138 exit=149 mae=-1.2 mfe=12.2 r_multiple=9.166667
```
