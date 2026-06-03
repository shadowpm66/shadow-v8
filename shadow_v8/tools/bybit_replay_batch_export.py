from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from shadow_v8.config import BROKERS, ROOT_DIR
from shadow_v8.tools.bybit_replay_export import INTERVAL_MINUTES, fetch_klines, write_csv
from shadow_v8.tools.replay_calibration_compare import (
    compare_file,
    evaluate_guard,
    print_summary as print_calibration_summary,
    summarize_rows as summarize_calibration_rows,
    write_json,
)
from shadow_v8.tools.replay_validate import run_file, summary_row, write_json as write_replay_json


DEFAULT_OUTPUT_DIR = ROOT_DIR / "runtime" / "replay_data"
DEFAULT_REPORT_DIR = ROOT_DIR / "runtime" / "replay_batch_reports"


def export_symbol(
    symbol: str,
    *,
    interval: str,
    category: str,
    limit: int,
    output_dir: Path,
    base_url: str,
    sleep_sec: float,
) -> dict[str, Any]:
    candles = fetch_klines(
        symbol=symbol,
        interval=interval,
        category=category,
        limit=limit,
        base_url=base_url,
        sleep_sec=sleep_sec,
    )
    if not candles:
        return {"symbol": symbol, "ok": False, "error": "No candles returned"}
    output_path = output_dir / f"{symbol}_{interval}.csv"
    write_csv(output_path, candles)
    return {
        "symbol": symbol,
        "ok": True,
        "path": str(output_path),
        "candles": len(candles),
        "first": candles[0].timestamp.isoformat(),
        "last": candles[-1].timestamp.isoformat(),
    }


def validate_exports(exports: list[dict[str, Any]], *, min_bars: int, allow_short: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in exports:
        if not item.get("ok"):
            continue
        result = run_file(
            Path(str(item["path"])),
            symbol=str(item["symbol"]),
            asset_class="crypto",
            min_bars=min_bars,
            allow_short=allow_short,
        )
        rows.append(summary_row(result))
    return rows


def compare_exports(exports: list[dict[str, Any]], *, min_bars: int, allow_short: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in exports:
        if not item.get("ok"):
            continue
        rows.append(
            compare_file(
                Path(str(item["path"])),
                symbol=str(item["symbol"]),
                asset_class="crypto",
                min_bars=min_bars,
                allow_short=allow_short,
            )
        )
    return rows


def parse_symbols(raw: str) -> list[str]:
    symbols = [item.strip().upper() for item in raw.replace(";", ",").split(",")]
    return [item for item in symbols if item]


def summarize_batch(
    exports: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
    calibration_rows: list[dict[str, Any]],
    guard: dict[str, Any] | None,
) -> dict[str, Any]:
    exported_count = sum(1 for item in exports if item.get("ok"))
    failed_exports = [item.get("symbol") for item in exports if not item.get("ok")]
    validation_ranked = sorted(validation_rows, key=lambda row: float(row.get("net_r") or 0.0), reverse=True)
    zero_trade_symbols = [row.get("symbol") for row in validation_rows if int(row.get("trades") or 0) == 0]
    calibration_worse = [row.get("symbol") for row in calibration_rows if row.get("verdict") == "worse"]
    return {
        "exported_count": exported_count,
        "failed_exports": failed_exports,
        "validated_count": len(validation_rows),
        "best_net_r": validation_ranked[0] if validation_ranked else None,
        "worst_net_r": validation_ranked[-1] if validation_ranked else None,
        "zero_trade_symbols": zero_trade_symbols,
        "calibration_worse_symbols": calibration_worse,
        "guard_ok": None if guard is None else guard.get("ok"),
        "guard_failure_count": None if guard is None else guard.get("failure_count"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export and optionally validate multiple Bybit replay CSV files.")
    parser.add_argument("--symbols", default="ETHUSDT,BTCUSDT,SOLUSDT", help="Comma-separated Bybit symbols")
    parser.add_argument("--interval", default="15", choices=sorted(INTERVAL_MINUTES.keys(), key=lambda item: INTERVAL_MINUTES[item]))
    parser.add_argument("--category", default="linear", choices=["linear", "inverse", "spot"])
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--base-url", default=BROKERS["bybit"].base_url or "https://api.bybit.com")
    parser.add_argument("--sleep-sec", type=float, default=0.25, help="Pause between symbols to be gentle on public API")
    parser.add_argument("--validate", action="store_true", help="Run replay validation for each exported CSV")
    parser.add_argument("--compare-calibration", action="store_true", help="Run default vs calibration comparison for exports")
    parser.add_argument("--strict-guard", action="store_true", help="Fail if calibration worsens, regresses R, or adds trades")
    parser.add_argument("--min-bars", type=int, default=120)
    parser.add_argument("--allow-short", action="store_true")
    parser.add_argument("--no-write", action="store_true", help="Print results without writing report JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = parse_symbols(args.symbols)
    if not symbols:
        raise SystemExit("No symbols provided")

    exports: list[dict[str, Any]] = []
    for index, symbol in enumerate(symbols):
        exports.append(
            export_symbol(
                symbol,
                interval=args.interval,
                category=args.category,
                limit=args.limit,
                output_dir=args.output_dir,
                base_url=args.base_url,
                sleep_sec=args.sleep_sec,
            )
        )
        if index < len(symbols) - 1:
            time.sleep(args.sleep_sec)

    validation_rows = validate_exports(exports, min_bars=args.min_bars, allow_short=args.allow_short) if args.validate else []
    calibration_rows = (
        compare_exports(exports, min_bars=args.min_bars, allow_short=args.allow_short) if args.compare_calibration else []
    )
    guard = None
    if args.compare_calibration:
        guard = evaluate_guard(
            calibration_rows,
            fail_on_worse=args.strict_guard,
            max_net_r_regression=0.0 if args.strict_guard else None,
            max_added_trades=0 if args.strict_guard else None,
        )
    digest = summarize_batch(exports, validation_rows, calibration_rows, guard)

    payload = {
        "ok": all(item.get("ok") for item in exports) and (guard is None or guard["ok"]),
        "symbols": symbols,
        "digest": digest,
        "exports": exports,
        "validation": validation_rows,
        "calibration": {
            "aggregate": summarize_calibration_rows(calibration_rows) if calibration_rows else None,
            "guard": guard,
            "results": calibration_rows,
        },
    }
    if not args.no_write:
        write_replay_json(args.report_dir / "bybit_replay_batch.json", payload)
        if calibration_rows:
            write_json(
                args.report_dir / "calibration_compare.json",
                {"ok": guard["ok"] if guard else True, "aggregate": payload["calibration"]["aggregate"], "guard": guard, "results": calibration_rows},
            )

    print("Bybit replay batch export complete")
    print(f"ok={payload['ok']}")
    print(f"symbols={','.join(symbols)}")
    print(f"exports={sum(1 for item in exports if item.get('ok'))}/{len(exports)}")
    print(
        "digest: exported={exported_count} validated={validated_count} best={best} worst={worst} "
        "zero_trade_symbols={zero_trade_symbols} calibration_worse={calibration_worse_symbols} guard_ok={guard_ok}".format(
            exported_count=digest["exported_count"],
            validated_count=digest["validated_count"],
            best=(digest["best_net_r"] or {}).get("symbol"),
            worst=(digest["worst_net_r"] or {}).get("symbol"),
            zero_trade_symbols=digest["zero_trade_symbols"],
            calibration_worse_symbols=digest["calibration_worse_symbols"],
            guard_ok=digest["guard_ok"],
        )
    )
    for item in exports:
        print(
            "symbol={symbol} ok={ok} candles={candles} path={path}".format(
                symbol=item.get("symbol"),
                ok=item.get("ok"),
                candles=item.get("candles"),
                path=item.get("path"),
            )
        )
    if validation_rows:
        for row in validation_rows:
            print("validation: symbol={symbol} trades={trades} net_r={net_r} top_watch={top_watch_reason}".format(**row))
    if calibration_rows:
        print_calibration_summary(calibration_rows, guard)
    if guard is not None and not guard["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
