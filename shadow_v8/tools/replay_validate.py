from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

from shadow_v8.config import ROOT_DIR
from shadow_v8.context.stage_engine import StageEngine
from shadow_v8.models import AssetConfig, Stage
from shadow_v8.research.replay import Replay
from shadow_v8.strategy.entry_policy import EntryPolicy
from shadow_v8.tools.replay_csv import load_csv_candles


DEFAULT_OUTPUT_DIR = ROOT_DIR / "runtime" / "replay_reports"


def build_asset(symbol: str, asset_class: str, allow_short: bool) -> AssetConfig:
    return AssetConfig(
        symbol=symbol,
        asset_class=asset_class,
        broker="paper",
        allow_long=True,
        allow_short=allow_short,
        max_risk_pct=0.03 if asset_class in ("crypto", "forex") else 0.015,
    )


def build_stage_engine(asset_class: str, allow_intraday_stage_calibration: bool) -> StageEngine:
    if allow_intraday_stage_calibration and asset_class in ("crypto", "forex"):
        return StageEngine(
            long_daily_stages=(Stage.STAGE_2, Stage.STAGE_1, Stage.STAGE_3, Stage.UNKNOWN),
            short_daily_stages=(Stage.STAGE_4, Stage.STAGE_3, Stage.STAGE_1, Stage.UNKNOWN),
        )
    return StageEngine()


def discover_csv_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.glob("*.csv")))
        else:
            matches = sorted(Path(item) for item in glob.glob(str(path)))
            files.extend(item for item in matches if item.is_file())
    return sorted(dict.fromkeys(files))


def symbol_from_path(path: Path) -> str:
    stem = path.stem.upper()
    for suffix in ("_15M", "-15M", "_15", "-15", "_1H", "-1H", "_D", "-D"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def run_file(
    path: Path,
    *,
    symbol: str | None,
    asset_class: str,
    min_bars: int,
    allow_short: bool,
    allow_near_entry_watch: bool = False,
    allow_intraday_stage_calibration: bool = False,
) -> dict[str, Any]:
    candles = load_csv_candles(path)
    replay_symbol = symbol or symbol_from_path(path)
    result = Replay(
        asset=build_asset(replay_symbol, asset_class, allow_short),
        candles=candles,
        min_bars=min_bars,
        stage_engine=build_stage_engine(asset_class, allow_intraday_stage_calibration),
        entry_policy=EntryPolicy(allow_near_entry_watch=allow_near_entry_watch),
        input_source={
            "type": "csv",
            "path": str(path),
            "allow_near_entry_watch": allow_near_entry_watch,
            "allow_intraday_stage_calibration": allow_intraday_stage_calibration,
        },
    ).run()
    return result


def summary_row(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics", {})
    gate = result.get("gate_analytics", {})
    top_blocker = (gate.get("top_blockers") or [{}])[0].get("name")
    top_watch = (gate.get("top_watch_reasons") or [{}])[0].get("name")
    top_stage_block_reason = (gate.get("top_stage_block_reasons") or [{}])[0].get("name")
    top_allowed_non_entry = (gate.get("top_allowed_non_entry_reasons") or [{}])[0].get("name")
    action_by_status = gate.get("action_by_status", {})
    pivot_shift_buckets = gate.get("pivot_shift_progress_buckets", {})
    top_pivot_shift_bucket = None
    if pivot_shift_buckets:
        top_pivot_shift_bucket = max(pivot_shift_buckets.items(), key=lambda item: int(item[1]))[0]
    watch_readiness_buckets = gate.get("watch_readiness_buckets", {})
    top_watch_readiness = None
    if watch_readiness_buckets:
        top_watch_readiness = max(watch_readiness_buckets.items(), key=lambda item: int(item[1]))[0]
    return {
        "symbol": result.get("symbol"),
        "asset_class": result.get("asset_class"),
        "schema_version": result.get("schema_version"),
        "bars_processed": result.get("bars_processed"),
        "trades": metrics.get("total_trades"),
        "net_r": metrics.get("net_r"),
        "expectancy": metrics.get("expectancy"),
        "skipped_setups": metrics.get("skipped_setup_count"),
        "allowed_setups": gate.get("allowed_setups"),
        "allowed_entries": action_by_status.get("ALLOW:ENTER", 0),
        "allowed_non_entries": sum(
            int(count)
            for key, count in action_by_status.items()
            if str(key).startswith("ALLOW:") and key != "ALLOW:ENTER"
        ),
        "allow_rate": gate.get("allow_rate"),
        "watch_rate": gate.get("watch_rate"),
        "block_rate": gate.get("block_rate"),
        "top_blocker": top_blocker,
        "top_stage_block_reason": top_stage_block_reason,
        "top_watch_reason": top_watch,
        "top_pivot_shift_bucket": top_pivot_shift_bucket,
        "top_watch_readiness": top_watch_readiness,
        "near_entry_watch_samples": len(gate.get("near_entry_watch_samples", [])),
        "top_allowed_non_entry_reason": top_allowed_non_entry,
        "validation_notes": gate.get("validation_notes", []),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_summary(rows: list[dict[str, Any]]) -> None:
    print("Replay validation complete")
    print("ok=True")
    print(f"files={len(rows)}")
    for row in rows:
        print(
            "symbol={symbol} bars={bars_processed} trades={trades} net_r={net_r} "
            "allow_rate={allow_rate} watch_rate={watch_rate} block_rate={block_rate} "
            "allowed_entries={allowed_entries} allowed_non_entries={allowed_non_entries} "
            "top_allowed_non_entry_reason={top_allowed_non_entry_reason} top_blocker={top_blocker} "
            "top_stage_block_reason={top_stage_block_reason} top_watch_reason={top_watch_reason} top_pivot_shift_bucket={top_pivot_shift_bucket} "
            "top_watch_readiness={top_watch_readiness} near_entry_watch_samples={near_entry_watch_samples}".format(**row)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Shadow v8 replay validation over one or more OHLCV CSV files.")
    parser.add_argument("paths", nargs="+", type=Path, help="CSV files, directories containing CSV files, or glob patterns")
    parser.add_argument("--symbol", help="Optional symbol override. Use only with one CSV file.")
    parser.add_argument("--asset-class", default="crypto", choices=["crypto", "forex", "stock", "commodity", "tokenized_stock"])
    parser.add_argument("--min-bars", type=int, default=60)
    parser.add_argument("--allow-short", action="store_true")
    parser.add_argument(
        "--allow-near-entry-watch",
        action="store_true",
        help="Calibration mode: allow strict near-entry WATCH setups to enter during replay only.",
    )
    parser.add_argument(
        "--allow-intraday-stage-calibration",
        action="store_true",
        help="Calibration mode: use crypto/forex intraday daily-stage compatibility during replay only.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-write", action="store_true", help="Print results without writing JSON reports")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = discover_csv_files(args.paths)
    if not files:
        raise SystemExit("No CSV files found")
    if args.symbol and len(files) != 1:
        raise SystemExit("--symbol can only be used with one CSV file")

    results = [
        run_file(
            path,
            symbol=args.symbol,
            asset_class=args.asset_class,
            min_bars=args.min_bars,
            allow_short=args.allow_short,
            allow_near_entry_watch=args.allow_near_entry_watch,
            allow_intraday_stage_calibration=args.allow_intraday_stage_calibration,
        )
        for path in files
    ]
    rows = [summary_row(result) for result in results]
    summary = {
        "ok": True,
        "file_count": len(files),
        "results": rows,
    }
    if not args.no_write:
        for path, result in zip(files, results):
            write_json(args.output_dir / f"{symbol_from_path(path).lower()}_replay.json", result)
        write_json(args.output_dir / "summary.json", summary)
    print_summary(rows)


if __name__ == "__main__":
    main()
