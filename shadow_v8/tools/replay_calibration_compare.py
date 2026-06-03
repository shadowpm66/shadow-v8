from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from shadow_v8.config import ROOT_DIR
from shadow_v8.tools.replay_validate import discover_csv_files, run_file, summary_row, symbol_from_path


DEFAULT_OUTPUT_DIR = ROOT_DIR / "runtime" / "replay_calibration"


def _delta(calibrated: Any, baseline: Any) -> Any:
    if calibrated is None or baseline is None:
        return None
    return round(float(calibrated) - float(baseline), 6)


def compare_file(
    path: Path,
    *,
    symbol: str | None,
    asset_class: str,
    min_bars: int,
    allow_short: bool,
) -> dict[str, Any]:
    baseline_result = run_file(
        path,
        symbol=symbol,
        asset_class=asset_class,
        min_bars=min_bars,
        allow_short=allow_short,
        allow_near_entry_watch=False,
    )
    calibrated_result = run_file(
        path,
        symbol=symbol,
        asset_class=asset_class,
        min_bars=min_bars,
        allow_short=allow_short,
        allow_near_entry_watch=True,
    )
    baseline = summary_row(baseline_result)
    calibrated = summary_row(calibrated_result)
    net_r_delta = _delta(calibrated.get("net_r"), baseline.get("net_r"))
    trade_delta = int(calibrated.get("trades") or 0) - int(baseline.get("trades") or 0)
    if net_r_delta is None or net_r_delta == 0:
        verdict = "unchanged"
    elif net_r_delta > 0:
        verdict = "improved"
    else:
        verdict = "worse"
    return {
        "path": str(path),
        "symbol": calibrated.get("symbol") or baseline.get("symbol") or symbol_from_path(path),
        "asset_class": asset_class,
        "baseline": baseline,
        "calibrated": calibrated,
        "delta": {
            "trades": trade_delta,
            "net_r": net_r_delta,
            "expectancy": _delta(calibrated.get("expectancy"), baseline.get("expectancy")),
            "allow_rate": _delta(calibrated.get("allow_rate"), baseline.get("allow_rate")),
            "watch_rate": _delta(calibrated.get("watch_rate"), baseline.get("watch_rate")),
            "block_rate": _delta(calibrated.get("block_rate"), baseline.get("block_rate")),
            "near_entry_watch_samples": int(calibrated.get("near_entry_watch_samples") or 0)
            - int(baseline.get("near_entry_watch_samples") or 0),
        },
        "verdict": verdict,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_summary(rows: list[dict[str, Any]]) -> None:
    print("Replay calibration compare complete")
    print("ok=True")
    print(f"files={len(rows)}")
    for row in rows:
        baseline = row["baseline"]
        calibrated = row["calibrated"]
        delta = row["delta"]
        print(
            "symbol={symbol} verdict={verdict} baseline_trades={baseline_trades} "
            "calibrated_trades={calibrated_trades} trade_delta={trade_delta} "
            "baseline_net_r={baseline_net_r} calibrated_net_r={calibrated_net_r} "
            "net_r_delta={net_r_delta} baseline_top_watch={baseline_top_watch} "
            "calibrated_top_watch={calibrated_top_watch}".format(
                symbol=row["symbol"],
                verdict=row["verdict"],
                baseline_trades=baseline.get("trades"),
                calibrated_trades=calibrated.get("trades"),
                trade_delta=delta.get("trades"),
                baseline_net_r=baseline.get("net_r"),
                calibrated_net_r=calibrated.get("net_r"),
                net_r_delta=delta.get("net_r"),
                baseline_top_watch=baseline.get("top_watch_reason"),
                calibrated_top_watch=calibrated.get("top_watch_reason"),
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare default replay behavior against the near-entry calibration switch."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="CSV files, directories containing CSV files, or glob patterns")
    parser.add_argument("--symbol", help="Optional symbol override. Use only with one CSV file.")
    parser.add_argument("--asset-class", default="crypto", choices=["crypto", "forex", "stock", "commodity", "tokenized_stock"])
    parser.add_argument("--min-bars", type=int, default=60)
    parser.add_argument("--allow-short", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-write", action="store_true", help="Print comparison without writing JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = discover_csv_files(args.paths)
    if not files:
        raise SystemExit("No CSV files found")
    if args.symbol and len(files) != 1:
        raise SystemExit("--symbol can only be used with one CSV file")
    rows = [
        compare_file(
            path,
            symbol=args.symbol,
            asset_class=args.asset_class,
            min_bars=args.min_bars,
            allow_short=args.allow_short,
        )
        for path in files
    ]
    summary = {"ok": True, "file_count": len(files), "results": rows}
    if not args.no_write:
        write_json(args.output_dir / "calibration_compare.json", summary)
    print_summary(rows)


if __name__ == "__main__":
    main()
