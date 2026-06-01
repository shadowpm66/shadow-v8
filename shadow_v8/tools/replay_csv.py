from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from shadow_v8.models import AssetConfig, Candle
from shadow_v8.research.replay import Replay


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
MIN_REAL_REPLAY_CANDLES = 60

COLUMN_ALIASES = {
    "timestamp": "timestamp",
    "time": "timestamp",
    "date": "timestamp",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


def load_csv_candles(path: Path) -> list[Candle]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Empty CSV or missing header row")

        columns = _normalize_columns(reader.fieldnames)
        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing:
            raise ValueError(f"Missing required CSV columns: {', '.join(missing)}")

        candles: list[Candle] = []
        for row_number, row in enumerate(reader, start=2):
            if not row or not any((value or "").strip() for value in row.values()):
                continue
            candles.append(_row_to_candle(row, columns, row_number))
    if not candles:
        raise ValueError("Empty CSV: no candle rows found")
    candles.sort(key=lambda item: item.timestamp)
    return candles


def _normalize_columns(fieldnames: list[str]) -> dict[str, str]:
    columns: dict[str, str] = {}
    for fieldname in fieldnames:
        normalized = COLUMN_ALIASES.get(fieldname.strip().lower())
        if normalized and normalized not in columns:
            columns[normalized] = fieldname
    return columns


def _row_to_candle(row: dict[str, str], columns: dict[str, str], row_number: int) -> Candle:
    timestamp_raw = _cell(row, columns["timestamp"])
    try:
        timestamp = datetime.fromisoformat(timestamp_raw)
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp on row {row_number}: {timestamp_raw!r}") from exc

    return Candle(
        timestamp=timestamp,
        open=_number(row, columns["open"], "open", row_number),
        high=_number(row, columns["high"], "high", row_number),
        low=_number(row, columns["low"], "low", row_number),
        close=_number(row, columns["close"], "close", row_number),
        volume=_number(row, columns["volume"], "volume", row_number),
    )


def _cell(row: dict[str, str], column: str) -> str:
    return (row.get(column) or "").strip()


def _number(row: dict[str, str], column: str, label: str, row_number: int) -> float:
    raw = _cell(row, column)
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value for {label} on row {row_number}: {raw!r}") from exc


def build_asset(symbol: str) -> AssetConfig:
    return AssetConfig(
        symbol=symbol,
        asset_class="crypto",
        broker="paper",
        allow_long=True,
        allow_short=False,
        max_risk_pct=0.01,
    )


def print_result(result: dict) -> None:
    metrics = result["metrics"]
    breakdowns = result["breakdowns"]
    gate_analytics = result.get("gate_analytics", {})
    print(f"schema_version={result['schema_version']}")
    print(f"ok={result['ok']}")
    print(f"symbol={result['symbol']}")
    print(f"bars_processed={result['bars_processed']}")
    print(f"trade_count={metrics['total_trades']}")
    print(f"skipped_setup_count={metrics['skipped_setup_count']}")
    print(f"win_rate={metrics['win_rate']}")
    print(f"net_r={metrics['net_r']}")
    print(f"average_r={metrics['average_r']}")
    print(f"best_r={metrics['best_r']}")
    print(f"worst_r={metrics['worst_r']}")
    print(f"max_drawdown_r={metrics['max_drawdown_r']}")
    print(f"profit_factor={metrics['profit_factor']}")
    print(f"expectancy={metrics['expectancy']}")
    print(f"average_trade_duration_bars={metrics['average_trade_duration_bars']}")
    print(f"action_counts={breakdowns['action_counts']}")
    print(f"setup_breakdown={breakdowns['setup_breakdown']}")
    print(f"grade_breakdown={breakdowns['grade_breakdown']}")
    print(f"risk_state_breakdown={breakdowns['risk_state_breakdown']}")
    print(f"gate_status_counts={gate_analytics.get('status_counts')}")
    print(f"gate_allow_rate={gate_analytics.get('allow_rate')}")
    print(f"gate_watch_rate={gate_analytics.get('watch_rate')}")
    print(f"gate_top_blockers={gate_analytics.get('top_blockers')}")
    print(f"gate_top_watch_reasons={gate_analytics.get('top_watch_reasons')}")
    print(f"gate_validation_notes={gate_analytics.get('validation_notes')}")
    if result["skipped_setups"]:
        confirmation = result["skipped_setups"][0]["confirmation"]
        vcp = confirmation.get("vcp", {})
        context = confirmation.get("context", {})
        gate = confirmation.get("trade_gate", {})
        nearest = context.get("nearest_zones", [{}])
        print(
            "sample_confirmation: base_confirmed={base_confirmed} pivot_confirmed={pivot_confirmed} "
            "nested_pattern={nested_pattern} stop_distance_quality={stop_distance_quality} "
            "vcp_tightness={vcp_tightness} contractions={contractions} volume_dry={volume_dry} "
            "breakout_volume={breakout_volume} context_score={context_score} nearest_zone={nearest_zone} "
            "gate_status={gate_status} gate_blockers={gate_blockers} gate_watch_reasons={gate_watch_reasons}".format(
                base_confirmed=confirmation["base"].get("confirmed"),
                pivot_confirmed=confirmation["pivot"].get("confirmed"),
                nested_pattern=confirmation["nested"].get("pattern"),
                stop_distance_quality=confirmation.get("stop_distance_quality"),
                vcp_tightness=vcp.get("tightness_score"),
                contractions=vcp.get("contraction_count"),
                volume_dry=vcp.get("volume_dry_up"),
                breakout_volume=vcp.get("breakout_volume"),
                context_score=context.get("quality_score"),
                nearest_zone=nearest[0].get("name") if nearest else None,
                gate_status=gate.get("status"),
                gate_blockers=gate.get("blockers"),
                gate_watch_reasons=gate.get("watch_reasons"),
            )
        )
    for idx, trade in enumerate(result["trades"], start=1):
        confirmation = trade.get("confirmation", {})
        vcp = confirmation.get("vcp", {})
        context = confirmation.get("context", {})
        gate = confirmation.get("trade_gate", {})
        nearest = context.get("nearest_zones", [{}])
        print(
            "trade_{idx}: direction={direction} entry={entry} exit={exit} stop={stop} "
            "duration_bars={duration_bars} r_multiple={r_multiple} mae={mae} mfe={mfe} "
            "base_confirmed={base_confirmed} pivot_confirmed={pivot_confirmed} nested_pattern={nested_pattern} "
            "vcp_tightness={vcp_tightness} contractions={contractions} volume_dry={volume_dry} "
            "breakout_volume={breakout_volume} context_score={context_score} nearest_zone={nearest_zone} "
            "gate_status={gate_status}".format(
                idx=idx,
                base_confirmed=confirmation.get("base", {}).get("confirmed"),
                pivot_confirmed=confirmation.get("pivot", {}).get("confirmed"),
                nested_pattern=confirmation.get("nested", {}).get("pattern"),
                vcp_tightness=vcp.get("tightness_score"),
                contractions=vcp.get("contraction_count"),
                volume_dry=vcp.get("volume_dry_up"),
                breakout_volume=vcp.get("breakout_volume"),
                context_score=context.get("quality_score"),
                nearest_zone=nearest[0].get("name") if nearest else None,
                gate_status=gate.get("status"),
                **trade,
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single-symbol Shadow v8 replay from OHLCV CSV data.")
    parser.add_argument("path", type=Path, help="CSV file with timestamp,open,high,low,close,volume columns")
    parser.add_argument("--symbol", default="CSVREPLAY", help="Symbol label for the replay")
    parser.add_argument("--min-bars", type=int, default=10, help="Minimum bars before replay decisions begin")
    parser.add_argument("--output", type=Path, help="Optional JSON file path for replay results")
    return parser.parse_args()


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    try:
        candles = load_csv_candles(args.path)
    except OSError as exc:
        raise SystemExit(f"CSV read error: {exc}") from exc
    except ValueError as exc:
        raise SystemExit(f"CSV validation error: {exc}") from exc
    if len(candles) < MIN_REAL_REPLAY_CANDLES:
        print(
            f"error=fewer_than_60_candles provided={len(candles)} minimum={MIN_REAL_REPLAY_CANDLES}",
            file=sys.stderr,
        )
    result = Replay(
        asset=build_asset(args.symbol),
        candles=candles,
        min_bars=args.min_bars,
        input_source={
            "type": "csv",
            "path": str(args.path),
        },
    ).run()
    if args.output:
        write_result(args.output, result)
    print_result(result)


if __name__ == "__main__":
    main()
