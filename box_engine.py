from __future__ import annotations

from shadow_v8.models import BaseState, Candle
from shadow_v8.structure.base_engine import BaseEngine


class BoxEngine:
    def __init__(self) -> None:
        self.base_engine = BaseEngine(min_bars=12, max_bars=40, max_depth_pct=18.0)

    def evaluate(self, candles: list[Candle]) -> BaseState:
        return self.base_engine.evaluate(candles)

