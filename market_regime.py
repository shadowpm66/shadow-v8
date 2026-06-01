from __future__ import annotations

from typing import Literal

from shadow_v8.models import Candle
from shadow_v8.structure.indicators import atr


Regime = Literal["trend_norm", "trend_hot", "range_norm", "range_hot"]


def detect_market_regime(candles: list[Candle]) -> Regime:
    if len(candles) < 60:
        return "range_norm"
    atr_value = atr(candles) or 0.0
    price = candles[-1].close
    atr_pct = atr_value / price if price else 0.0
    slope = candles[-1].close - candles[-20].close
    trendish = abs(slope) / max(price, 1e-9) > 0.04
    hot = atr_pct > 0.025
    if trendish and hot:
        return "trend_hot"
    if trendish:
        return "trend_norm"
    if hot:
        return "range_hot"
    return "range_norm"

