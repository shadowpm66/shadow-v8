from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from shadow_v8.config import BROKERS, ROOT_DIR
from shadow_v8.models import Candle
from shadow_v8.tools.replay_validate import run_file, summary_row


DEFAULT_OUTPUT_DIR = ROOT_DIR / "runtime" / "replay_data"
INTERVAL_MINUTES = {
    "1": 1,
    "3": 3,
    "5": 5,
    "15": 15,
    "30": 30,
    "60": 60,
    "120": 120,
    "240": 240,
    "360": 360,
    "720": 720,
    "D": 1440,
}


def fetch_klines(
    *,
    symbol: str,
    interval: str,
    category: str,
    limit: int,
    base_url: str,
    sleep_sec: float = 0.1,
) -> list[Candle]:
    if interval not in INTERVAL_MINUTES:
        raise ValueError(f"Unsupported interval {interval!r}; expected one of {', '.join(INTERVAL_MINUTES)}")
    url = f"{base_url.rstrip('/')}/v5/market/kline"
    remaining = limit
    end_ms: int | None = None
    rows_by_timestamp: dict[int, Candle] = {}

    while remaining > 0:
        batch_limit = min(1000, remaining)
        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": batch_limit,
        }
        if end_ms is not None:
            params["end"] = end_ms
        with urlopen(f"{url}?{urlencode(params)}", timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("retCode") != 0:
            raise RuntimeError(f"Bybit kline error {payload.get('retCode')}: {payload.get('retMsg')}")
        rows = payload.get("result", {}).get("list", []) or []
        if not rows:
            break
        oldest_ms = None
        for row in rows:
            timestamp_ms = int(row[0])
            rows_by_timestamp[timestamp_ms] = Candle(
                timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            oldest_ms = timestamp_ms if oldest_ms is None else min(oldest_ms, timestamp_ms)
        remaining = limit - len(rows_by_timestamp)
        if oldest_ms is None or len(rows) < batch_limit:
            break
        end_ms = oldest_ms - 1
        time.sleep(sleep_sec)

    return [rows_by_timestamp[key] for key in sorted(rows_by_timestamp)]


def write_csv(path: Path, candles: list[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for candle in candles:
            writer.writerow(
                [
                    candle.timestamp.isoformat(),
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export public Bybit OHLCV candles for Shadow v8 replay validation.")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--interval", default="15", choices=sorted(INTERVAL_MINUTES.keys(), key=lambda item: INTERVAL_MINUTES[item]))
    parser.add_argument("--category", default="linear", choices=["linear", "inverse", "spot"])
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--base-url", default=BROKERS["bybit"].base_url or "https://api.bybit.com")
    parser.add_argument("--validate", action="store_true", help="Run replay validation after writing the CSV")
    parser.add_argument("--min-bars", type=int, default=120)
    parser.add_argument("--allow-short", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candles = fetch_klines(
        symbol=args.symbol.upper(),
        interval=args.interval,
        category=args.category,
        limit=args.limit,
        base_url=args.base_url,
    )
    if not candles:
        raise SystemExit("No candles returned by Bybit")
    output_path = args.output_dir / f"{args.symbol.upper()}_{args.interval}.csv"
    write_csv(output_path, candles)
    print("Bybit replay export complete")
    print("ok=True")
    print(f"symbol={args.symbol.upper()}")
    print(f"interval={args.interval}")
    print(f"candles={len(candles)}")
    print(f"first={candles[0].timestamp.isoformat()}")
    print(f"last={candles[-1].timestamp.isoformat()}")
    print(f"path={output_path}")

    if args.validate:
        result = run_file(
            output_path,
            symbol=args.symbol.upper(),
            asset_class="crypto",
            min_bars=args.min_bars,
            allow_short=args.allow_short,
        )
        row = summary_row(result)
        print(
            "validation: trades={trades} net_r={net_r} allow_rate={allow_rate} "
            "watch_rate={watch_rate} block_rate={block_rate} top_blocker={top_blocker} "
            "top_watch_reason={top_watch_reason}".format(**row)
        )


if __name__ == "__main__":
    main()
