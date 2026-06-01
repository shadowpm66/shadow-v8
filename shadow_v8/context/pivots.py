from __future__ import annotations


def daily_open_pivots(daily_open: float, adr: float) -> dict[str, float]:
    return {
        "M0": daily_open - 0.75 * adr,
        "M1": daily_open - 0.50 * adr,
        "M2": daily_open - 0.25 * adr,
        "M3": daily_open + 0.25 * adr,
        "M4": daily_open + 0.50 * adr,
        "M5": daily_open + 0.75 * adr,
        "DO": daily_open,
        "ADR_H": daily_open + adr,
        "ADR_L": daily_open - adr,
    }

