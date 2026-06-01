from __future__ import annotations


def size_by_risk(balance: float, risk_pct: float, entry: float, stop: float) -> float:
    risk_dollars = balance * risk_pct
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        return 0.0
    return risk_dollars / stop_distance


def size_by_allocation(balance: float, position_pct: float, entry: float) -> float:
    if entry <= 0 or position_pct <= 0:
        return 0.0
    return (balance * position_pct) / entry
