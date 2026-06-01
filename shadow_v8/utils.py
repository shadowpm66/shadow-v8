from __future__ import annotations

from statistics import mean


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def pct_change(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / abs(old) * 100.0


def safe_mean(values: list[float]) -> float:
    clean = [v for v in values if v is not None]
    return mean(clean) if clean else 0.0

