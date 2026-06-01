from __future__ import annotations

from shadow_v8.models import Candle


def average_volume(candles: list[Candle]) -> float:
    if not candles:
        return 0.0
    return sum(c.volume for c in candles) / len(candles)


def has_breakout_volume(candles: list[Candle], lookback: int = 20, multiplier: float = 1.5) -> bool:
    return breakout_volume_ratio(candles, lookback) >= multiplier


def breakout_volume_ratio(candles: list[Candle], lookback: int = 20) -> float:
    if len(candles) < lookback + 1:
        return 0.0
    avg = average_volume(candles[-lookback - 1 : -1])
    return candles[-1].volume / avg if avg > 0 else 0.0


def has_volume_dry_up(candles: list[Candle], lookback: int = 20) -> bool:
    return volume_dry_up_ratio(candles, lookback) <= 0.7 if len(candles) >= lookback else False


def volume_dry_up_ratio(candles: list[Candle], lookback: int = 20) -> float:
    if len(candles) < lookback:
        return 1.0
    first = candles[-lookback : -lookback // 2]
    second = candles[-lookback // 2 :]
    old = average_volume(first)
    new = average_volume(second)
    return new / old if old > 0 else 1.0
