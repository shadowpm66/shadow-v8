from __future__ import annotations

from shadow_v8.models import Candle, NestedStructureState
from shadow_v8.structure.wm_detector import WmDetector
from shadow_v8.utils import clamp


class NestedStructureDetector:
    def __init__(self) -> None:
        self.detector = WmDetector()

    def detect(self, candles: list[Candle]) -> NestedStructureState:
        if len(candles) < 60:
            return NestedStructureState(pattern="NONE", reasons=["Need more candles for nested structure"])
        outer_window = candles[-min(120, len(candles)) :]
        inner_window = candles[-min(45, len(candles)) :]
        outer = self.detector.detect(outer_window)
        inner = self.detector.detect(inner_window)
        if outer.type == "W" and inner.type == "W":
            pattern = "W_WITHIN_W"
        elif outer.type == "M" and inner.type == "M":
            pattern = "M_WITHIN_M"
        elif outer.type != "NONE" and inner.type != "NONE":
            pattern = "MIXED"
        else:
            pattern = "NONE"
        aligned_direction = outer.direction == inner.direction and outer.direction != "FLAT"
        inner_inside_outer = self._inner_inside_outer(outer, inner)
        confirmed = pattern in ("W_WITHIN_W", "M_WITHIN_M") and aligned_direction and inner_inside_outer
        score = clamp((outer.quality_score * 0.45 + inner.quality_score * 0.55), 0.0, 100.0) if confirmed else 0.0
        return NestedStructureState(
            pattern=pattern,
            confirmed=confirmed,
            outer_structure=outer if outer.type != "NONE" else None,
            inner_structure=inner if inner.type != "NONE" else None,
            quality_score=score,
            reasons=[
                f"Nested pattern: {pattern}",
                "Inner structure aligned" if aligned_direction else "Inner structure not aligned",
                "Inner structure inside outer base" if inner_inside_outer else "Inner structure not contained by outer base",
            ],
        )

    def _inner_inside_outer(self, outer, inner) -> bool:
        if outer.type == "NONE" or inner.type == "NONE":
            return False
        if outer.base is None or inner.base is None or outer.neckline is None or inner.neckline is None:
            return False
        outer_low = min(outer.base, outer.neckline)
        outer_high = max(outer.base, outer.neckline)
        inner_low = min(inner.base, inner.neckline)
        inner_high = max(inner.base, inner.neckline)
        return outer_low <= inner_low <= outer_high and outer_low <= inner_high <= outer_high
