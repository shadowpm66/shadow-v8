from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

from shadow_v8.config import ROOT_DIR
from shadow_v8.models import AssetConfig
from shadow_v8.research.replay import Replay
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


def run_file(path: Path, *, symbol: str | None, asset_class: str, min_bars: int, allow_short: bool) -> dict[str, Any]:
    candles = load_csv_candles(path)
    replay_symbol = symbol or symbol_from_path(path)
    result = Replay(
        asset=build_asset(replay_symbol, asset_class, allow_short),
        candles=candles,
        min_bars=min_bars,
        input_source={
            "type": "csv",
            "path": str(path),
        },
    ).run()
    return result


def summary_row(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics", {})
    gate = result.get("gate_analytics", {})
    top_blocker = (gate.get("top_blockers") or [{}])[0].get("name")
    top_watch = (gate.get("top_watch_reasons") or [{}])[0].get("name")
    return {
        "symbol": result.get("symbol"),
        "asset_class": result.get("asset_class"),
        "bars_processed": result.get("bars_processed"),
        "trades": metrics.get("total_trades"),
        "net_r": metrics.get("net_r"),
        "expectancy": metrics.get("expectancy"),
        "skipped_setups": metrics.get("skipped_setup_count"),
        "allow_rate": gate.get("allow_rate"),
        "watch_rate": gate.get("watch_rate"),
        "block_rate": gate.get("block_rate"),
        "top_blocker": top_blocker,
        "top_watch_reason": top_watch,
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
            "top_blocker={top_blocker} top_watch_reason={top_watch_reason}".format(**row)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Shadow v8 replay validation over one or more OHLCV CSV files.")
    parser.add_argument("paths", nargs="+", type=Path, help="CSV files, directories containing CSV files, or glob patterns")
    parser.add_argument("--symbol", help="Optional symbol override. Use only with one CSV file.")
    parser.add_argument("--asset-class", default="crypto", choices=["crypto", "forex", "stock", "commodity", "tokenized_stock"])
    parser.add_argument("--min-bars", type=int, default=60)
    parser.add_argument("--allow-short", action="store_true")
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
        run_file(path, symbol=args.symbol, asset_class=args.asset_class, min_bars=args.min_bars, allow_short=args.allow_short)
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
