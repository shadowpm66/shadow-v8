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
    calibrate_intraday_stage: bool = False,
) -> dict[str, Any]:
    baseline_result = run_file(
        path,
        symbol=symbol,
        asset_class=asset_class,
        min_bars=min_bars,
        allow_short=allow_short,
        allow_near_entry_watch=False,
        allow_intraday_stage_calibration=False,
    )
    calibrated_result = run_file(
        path,
        symbol=symbol,
        asset_class=asset_class,
        min_bars=min_bars,
        allow_short=allow_short,
        allow_near_entry_watch=True,
        allow_intraday_stage_calibration=calibrate_intraday_stage,
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
        "calibration": {
            "allow_near_entry_watch": True,
            "allow_intraday_stage_calibration": calibrate_intraday_stage,
        },
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


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    verdict_counts = {"improved": 0, "unchanged": 0, "worse": 0}
    net_r_deltas: list[float] = []
    trade_deltas: list[int] = []
    worst_regression: dict[str, Any] | None = None
    best_improvement: dict[str, Any] | None = None

    for row in rows:
        verdict = str(row.get("verdict") or "unchanged")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        delta = row.get("delta") or {}
        net_r_delta = delta.get("net_r")
        trade_delta = int(delta.get("trades") or 0)
        trade_deltas.append(trade_delta)
        if net_r_delta is None:
            continue
        net_r = float(net_r_delta)
        net_r_deltas.append(net_r)
        if worst_regression is None or net_r < float(worst_regression["net_r_delta"]):
            worst_regression = {"symbol": row.get("symbol"), "net_r_delta": round(net_r, 6)}
        if best_improvement is None or net_r > float(best_improvement["net_r_delta"]):
            best_improvement = {"symbol": row.get("symbol"), "net_r_delta": round(net_r, 6)}

    total = len(rows)
    average_net_r_delta = round(sum(net_r_deltas) / len(net_r_deltas), 6) if net_r_deltas else None
    average_trade_delta = round(sum(trade_deltas) / len(trade_deltas), 6) if trade_deltas else None
    if verdict_counts.get("worse", 0):
        overall_verdict = "worse"
    elif verdict_counts.get("improved", 0) and not verdict_counts.get("worse", 0):
        overall_verdict = "improved"
    else:
        overall_verdict = "unchanged"
    return {
        "file_count": total,
        "overall_verdict": overall_verdict,
        "verdict_counts": verdict_counts,
        "average_net_r_delta": average_net_r_delta,
        "average_trade_delta": average_trade_delta,
        "worst_regression": worst_regression,
        "best_improvement": best_improvement,
    }


def evaluate_guard(
    rows: list[dict[str, Any]],
    *,
    fail_on_worse: bool,
    max_net_r_regression: float | None,
    max_added_trades: int | None,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for row in rows:
        delta = row.get("delta") or {}
        net_r_delta = delta.get("net_r")
        trade_delta = int(delta.get("trades") or 0)
        if fail_on_worse and row.get("verdict") == "worse":
            failures.append({"symbol": row.get("symbol"), "reason": "worse_verdict", "net_r_delta": net_r_delta})
        if max_net_r_regression is not None and net_r_delta is not None:
            if float(net_r_delta) < -abs(max_net_r_regression):
                failures.append(
                    {
                        "symbol": row.get("symbol"),
                        "reason": "net_r_regression",
                        "net_r_delta": net_r_delta,
                        "limit": -abs(max_net_r_regression),
                    }
                )
        if max_added_trades is not None and trade_delta > max_added_trades:
            failures.append(
                {
                    "symbol": row.get("symbol"),
                    "reason": "added_trades",
                    "trade_delta": trade_delta,
                    "limit": max_added_trades,
                }
            )
    return {
        "ok": not failures,
        "failures": failures,
        "failure_count": len(failures),
        "fail_on_worse": fail_on_worse,
        "max_net_r_regression": max_net_r_regression,
        "max_added_trades": max_added_trades,
    }


def guard_options_from_args(args: argparse.Namespace) -> dict[str, Any]:
    fail_on_worse = bool(args.fail_on_worse or args.strict_guard)
    max_net_r_regression = args.max_net_r_regression
    max_added_trades = args.max_added_trades
    if args.strict_guard:
        if max_net_r_regression is None:
            max_net_r_regression = 0.0
        if max_added_trades is None:
            max_added_trades = 0
    return {
        "fail_on_worse": fail_on_worse,
        "max_net_r_regression": max_net_r_regression,
        "max_added_trades": max_added_trades,
    }


def print_summary(rows: list[dict[str, Any]], guard: dict[str, Any] | None = None) -> None:
    aggregate = summarize_rows(rows)
    print("Replay calibration compare complete")
    print(f"ok={bool((guard or {'ok': True})['ok'])}")
    print(f"files={len(rows)}")
    print(
        "overall_verdict={overall_verdict} improved={improved} unchanged={unchanged} worse={worse} "
        "average_net_r_delta={average_net_r_delta} average_trade_delta={average_trade_delta} "
        "worst_regression={worst_regression} best_improvement={best_improvement}".format(
            overall_verdict=aggregate["overall_verdict"],
            improved=aggregate["verdict_counts"].get("improved", 0),
            unchanged=aggregate["verdict_counts"].get("unchanged", 0),
            worse=aggregate["verdict_counts"].get("worse", 0),
            average_net_r_delta=aggregate["average_net_r_delta"],
            average_trade_delta=aggregate["average_trade_delta"],
            worst_regression=aggregate["worst_regression"],
            best_improvement=aggregate["best_improvement"],
        )
    )
    if guard is not None:
        print(f"guard_ok={guard['ok']} guard_failures={guard['failure_count']} failures={guard['failures']}")
    for row in rows:
        baseline = row["baseline"]
        calibrated = row["calibrated"]
        delta = row["delta"]
        print(
            "symbol={symbol} verdict={verdict} baseline_trades={baseline_trades} "
            "calibrated_trades={calibrated_trades} trade_delta={trade_delta} "
            "baseline_net_r={baseline_net_r} calibrated_net_r={calibrated_net_r} "
            "net_r_delta={net_r_delta} baseline_top_watch={baseline_top_watch} "
            "calibrated_top_watch={calibrated_top_watch} intraday_stage={intraday_stage}".format(
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
                intraday_stage=(row.get("calibration") or {}).get("allow_intraday_stage_calibration"),
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
    parser.add_argument(
        "--calibrate-intraday-stage",
        action="store_true",
        help="Also test crypto/forex intraday stage compatibility in the calibrated replay.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-write", action="store_true", help="Print comparison without writing JSON")
    parser.add_argument(
        "--strict-guard",
        action="store_true",
        help="Preset: fail on worse verdict, any net R regression, or any added trade",
    )
    parser.add_argument("--fail-on-worse", action="store_true", help="Exit non-zero if any calibration verdict is worse")
    parser.add_argument(
        "--max-net-r-regression",
        type=float,
        help="Exit non-zero if any symbol loses more than this many R versus baseline",
    )
    parser.add_argument(
        "--max-added-trades",
        type=int,
        help="Exit non-zero if calibration adds more than this many trades for any symbol",
    )
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
            calibrate_intraday_stage=args.calibrate_intraday_stage,
        )
        for path in files
    ]
    guard_options = guard_options_from_args(args)
    guard = evaluate_guard(rows, **guard_options)
    summary = {
        "ok": guard["ok"],
        "file_count": len(files),
        "aggregate": summarize_rows(rows),
        "guard": guard,
        "results": rows,
    }
    if not args.no_write:
        write_json(args.output_dir / "calibration_compare.json", summary)
    print_summary(rows, guard)
    if not guard["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
