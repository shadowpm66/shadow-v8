from __future__ import annotations

from datetime import datetime, timedelta

from shadow_v8.context.zones import ContextEngine
from shadow_v8.models import Candle


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def synthetic_candles() -> list[Candle]:
    start = datetime.fromisoformat("2026-01-01T00:00:00")
    candles: list[Candle] = []
    price = 98.0
    for idx in range(80):
        timestamp = start + timedelta(hours=idx)
        drift = 0.03 if idx > 35 else 0.01
        wave = ((idx % 8) - 4) * 0.05
        open_ = price
        close = price + drift + wave
        high = max(open_, close) + 0.28
        low = min(open_, close) - 0.28
        volume = 100_000 + idx * 500
        candles.append(Candle(timestamp=timestamp, open=open_, high=high, low=low, close=close, volume=volume))
        price = close

    last = candles[-1]
    candles[-1] = Candle(
        timestamp=last.timestamp,
        open=99.8,
        high=100.22,
        low=99.68,
        close=100.0,
        volume=180_000,
    )
    return candles


def main() -> None:
    context = ContextEngine().evaluate(synthetic_candles(), direction="LONG")
    reference = context.metadata.get("reference_confluence", {})
    nearest = reference.get("nearest_reference") or {}
    flags = reference.get("flags") or []

    assert_true(context.quality_score > 0, "Context score should be positive")
    assert_true(context.zone_count > 0, "Context should build reference zones")
    assert_true(reference.get("nearby_count", 0) > 0, "Reference confluence should find nearby levels")
    assert_true(nearest.get("name") is not None, "Reference confluence should include nearest reference")
    assert_true("at_reference_level" in flags, "Price near 100 should flag at_reference_level")
    assert_true(
        any(row.get("kind") == "psych" for row in reference.get("nearby_references", [])),
        "Reference confluence should include psychological levels",
    )

    print("Reference confluence smoke complete")
    print("ok=True")
    print(f"context_score={context.quality_score}")
    print(f"nearest_reference={nearest.get('name')}")
    print(f"flags={flags}")


if __name__ == "__main__":
    main()
