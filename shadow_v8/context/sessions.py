from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from shadow_v8.models import Candle


def session_label(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    hour = now.hour
    if 0 <= hour < 7:
        return "Asia"
    if 7 <= hour < 12:
        return "London"
    if 12 <= hour < 20:
        return "NY"
    return "Late NY"


def current_session_candles(candles: list[Candle]) -> list[Candle]:
    if not candles:
        return []
    label = session_label(candles[-1].timestamp)
    date = candles[-1].timestamp.date()
    result = [candle for candle in candles if candle.timestamp.date() == date and session_label(candle.timestamp) == label]
    return result or [candles[-1]]


def previous_session_candles(candles: list[Candle]) -> list[Candle]:
    if len(candles) < 2:
        return []
    current_label = session_label(candles[-1].timestamp)
    current_date = candles[-1].timestamp.date()
    previous: list[Candle] = []
    for candle in reversed(candles[:-1]):
        label = session_label(candle.timestamp)
        date = candle.timestamp.date()
        if date == current_date and label == current_label:
            continue
        if not previous:
            previous.append(candle)
            target_label = label
            target_date = date
            continue
        if label == target_label and date == target_date:
            previous.append(candle)
        else:
            break
    return list(reversed(previous))


def session_summary(candles: list[Candle]) -> dict[str, Any]:
    if not candles:
        return {}
    return {
        "open": candles[0].open,
        "high": max(c.high for c in candles),
        "low": min(c.low for c in candles),
        "close": candles[-1].close,
        "label": session_label(candles[-1].timestamp),
        "count": len(candles),
    }
