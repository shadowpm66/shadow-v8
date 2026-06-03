from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from shadow_v8.models import Candle
from shadow_v8.tools import bybit_replay_batch_export as batch


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fake_fetch_klines(**kwargs) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    price = 100.0
    for index in range(24):
        close = price + (0.5 if index % 2 == 0 else -0.25)
        candles.append(
            Candle(
                timestamp=start + timedelta(minutes=15 * index),
                open=price,
                high=max(price, close) + 0.5,
                low=min(price, close) - 0.5,
                close=close,
                volume=1000 + index,
            )
        )
        price = close
    return candles


def main() -> None:
    original_fetch = batch.fetch_klines
    batch.fetch_klines = fake_fetch_klines
    try:
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            symbols = batch.parse_symbols("ETHUSDT, BTCUSDT; SOLUSDT")
            assert_true(symbols == ["ETHUSDT", "BTCUSDT", "SOLUSDT"], "Batch parser should normalize symbols")
            exports = [
                batch.export_symbol(
                    symbol,
                    interval="15",
                    category="linear",
                    limit=24,
                    output_dir=output_dir,
                    base_url="https://example.invalid",
                    sleep_sec=0,
                )
                for symbol in symbols
            ]
            assert_true(all(item["ok"] for item in exports), "Mocked batch exports should succeed")
            assert_true(all(Path(str(item["path"])).exists() for item in exports), "Batch export should write CSV files")
            validation_rows = batch.validate_exports(exports, min_bars=10, allow_short=True)
            assert_true(len(validation_rows) == 3, "Batch validation should produce one row per export")
            digest = batch.summarize_batch(exports, validation_rows, [], None)
            assert_true(digest["exported_count"] == 3, "Batch digest should count exports")
            assert_true(digest["validated_count"] == 3, "Batch digest should count validations")
            assert_true(digest["best_net_r"] is not None, "Batch digest should expose best net R row")
            assert_true(digest["worst_net_r"] is not None, "Batch digest should expose worst net R row")
    finally:
        batch.fetch_klines = original_fetch

    print("Bybit replay batch export smoke complete")
    print("ok=True")
    print("symbols=3")
    print("validation_rows=3")
    print("digest=enabled")


if __name__ == "__main__":
    main()
