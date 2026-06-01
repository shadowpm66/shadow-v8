from __future__ import annotations

from shadow_v8.models import Candle


def average_range(candles: list[Candle], period: int = 20) -> float | None:
    if len(candles) < period:
        return None
    return sum(c.high - c.low for c in candles[-period:]) / period


def average_weekly_range(candles: list[Candle], period: int = 5) -> float | None:
    if len(candles) < period * 5:
        return None
    weekly_ranges: list[float] = []
    sample = candles[-period * 5 :]
    for idx in range(0, len(sample), 5):
        week = sample[idx : idx + 5]
        if len(week) < 2:
            continue
        weekly_ranges.append(max(c.high for c in week) - min(c.low for c in week))
    return sum(weekly_ranges[-period:]) / len(weekly_ranges[-period:]) if weekly_ranges else None
