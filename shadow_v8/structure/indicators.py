from __future__ import annotations

from shadow_v8.models import Candle


def closes(candles: list[Candle]) -> list[float]:
    return [c.close for c in candles]


def highs(candles: list[Candle]) -> list[float]:
    return [c.high for c in candles]


def lows(candles: list[Candle]) -> list[float]:
    return [c.low for c in candles]


def volumes(candles: list[Candle]) -> list[float]:
    return [c.volume for c in candles]


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    ranges: list[float] = []
    for idx in range(1, len(candles)):
        cur = candles[idx]
        prev = candles[idx - 1]
        ranges.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    return sum(ranges[-period:]) / period


def pivot_lows(candles: list[Candle], left: int = 3, right: int = 3) -> list[int]:
    result: list[int] = []
    for idx in range(left, len(candles) - right):
        low = candles[idx].low
        if all(low < candles[idx - j].low for j in range(1, left + 1)) and all(
            low < candles[idx + j].low for j in range(1, right + 1)
        ):
            result.append(idx)
    return result


def pivot_highs(candles: list[Candle], left: int = 3, right: int = 3) -> list[int]:
    result: list[int] = []
    for idx in range(left, len(candles) - right):
        high = candles[idx].high
        if all(high > candles[idx - j].high for j in range(1, left + 1)) and all(
            high > candles[idx + j].high for j in range(1, right + 1)
        ):
            result.append(idx)
    return result

