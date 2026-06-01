from __future__ import annotations

from shadow_v8.models import Candle, StructureSignal
from shadow_v8.structure.indicators import pivot_highs, pivot_lows
from shadow_v8.utils import clamp


class WmDetector:
    def __init__(self, pivot_tolerance_pct: float = 4.0) -> None:
        self.pivot_tolerance_pct = pivot_tolerance_pct

    def detect(self, candles: list[Candle]) -> StructureSignal:
        w = self.detect_w(candles)
        m = self.detect_m(candles)
        if w.type != "NONE" and (m.type == "NONE" or w.quality_score >= m.quality_score):
            return w
        if m.type != "NONE":
            return m
        return StructureSignal(type="NONE", reasons=["No W/M structure detected"])

    def detect_w(self, candles: list[Candle]) -> StructureSignal:
        lows = pivot_lows(candles)
        if len(lows) < 2:
            return StructureSignal(type="NONE", reasons=["Need two pivot lows for W"])
        i1, i2 = lows[-2], lows[-1]
        if i2 <= i1:
            return StructureSignal(type="NONE", reasons=["Invalid W pivots"])
        leg1, leg2 = candles[i1], candles[i2]
        neckline = max(c.high for c in candles[i1 : i2 + 1])
        entry = candles[-1].close
        trap = leg2.low < leg1.low
        reclaim = entry >= neckline
        low_distance = abs(leg2.low - leg1.low) / max(leg1.low, 1e-9) * 100.0
        pivot_symmetry = low_distance <= self.pivot_tolerance_pct
        right_side_strength = self._right_side_strength(candles, i2, "LONG")
        midpoint_reclaim = entry > (neckline + min(leg1.low, leg2.low)) / 2.0
        score = 35.0
        score += 18.0 if trap else 10.0 if pivot_symmetry else 0.0
        score += 22.0 if reclaim else 8.0 if midpoint_reclaim else 0.0
        score += max(0.0, 14.0 - low_distance)
        score += right_side_strength * 0.15
        return StructureSignal(
            type="W",
            direction="LONG",
            entry=entry,
            neckline=neckline,
            base=min(leg1.low, leg2.low),
            trap=trap,
            quality_score=clamp(score, 0.0, 100.0),
            reasons=[
                "W pivot lows detected",
                "Second low undercut first low" if trap else "Second low held near first low",
                "Neckline reclaimed" if reclaim else "Neckline not reclaimed yet",
                "Right side strength improving" if right_side_strength >= 50 else "Right side still weak",
            ],
            metadata={
                "pivot_low_1": i1,
                "pivot_low_2": i2,
                "low_distance_pct": round(low_distance, 3),
                "pivot_symmetry": pivot_symmetry,
                "midpoint_reclaim": midpoint_reclaim,
                "neckline_ok": reclaim,
                "right_side_strength": round(right_side_strength, 2),
            },
        )

    def detect_m(self, candles: list[Candle]) -> StructureSignal:
        highs = pivot_highs(candles)
        if len(highs) < 2:
            return StructureSignal(type="NONE", reasons=["Need two pivot highs for M"])
        i1, i2 = highs[-2], highs[-1]
        if i2 <= i1:
            return StructureSignal(type="NONE", reasons=["Invalid M pivots"])
        leg1, leg2 = candles[i1], candles[i2]
        neckline = min(c.low for c in candles[i1 : i2 + 1])
        entry = candles[-1].close
        trap = leg2.high > leg1.high
        breakdown = entry <= neckline
        high_distance = abs(leg2.high - leg1.high) / max(leg1.high, 1e-9) * 100.0
        pivot_symmetry = high_distance <= self.pivot_tolerance_pct
        right_side_strength = self._right_side_strength(candles, i2, "SHORT")
        midpoint_loss = entry < (neckline + max(leg1.high, leg2.high)) / 2.0
        score = 35.0
        score += 18.0 if trap else 10.0 if pivot_symmetry else 0.0
        score += 22.0 if breakdown else 8.0 if midpoint_loss else 0.0
        score += max(0.0, 14.0 - high_distance)
        score += right_side_strength * 0.15
        return StructureSignal(
            type="M",
            direction="SHORT",
            entry=entry,
            neckline=neckline,
            base=max(leg1.high, leg2.high),
            trap=trap,
            quality_score=clamp(score, 0.0, 100.0),
            reasons=[
                "M pivot highs detected",
                "Second high swept first high" if trap else "Second high held near first high",
                "Neckline lost" if breakdown else "Neckline not lost yet",
                "Right side weakness improving" if right_side_strength >= 50 else "Right side still weak",
            ],
            metadata={
                "pivot_high_1": i1,
                "pivot_high_2": i2,
                "high_distance_pct": round(high_distance, 3),
                "pivot_symmetry": pivot_symmetry,
                "midpoint_loss": midpoint_loss,
                "neckline_ok": breakdown,
                "right_side_strength": round(right_side_strength, 2),
            },
        )

    def _right_side_strength(self, candles: list[Candle], pivot_index: int, direction: str) -> float:
        right = candles[pivot_index:]
        if len(right) < 4:
            return 0.0
        score = 0.0
        closes = [c.close for c in right]
        if direction == "LONG":
            score += 35.0 if closes[-1] > closes[0] else 0.0
            higher_closes = sum(1 for prev, cur in zip(closes, closes[1:]) if cur >= prev)
            score += min(35.0, higher_closes / max(len(closes) - 1, 1) * 35.0)
            score += 30.0 if right[-1].close > max(c.high for c in right[:-1]) else 0.0
        else:
            score += 35.0 if closes[-1] < closes[0] else 0.0
            lower_closes = sum(1 for prev, cur in zip(closes, closes[1:]) if cur <= prev)
            score += min(35.0, lower_closes / max(len(closes) - 1, 1) * 35.0)
            score += 30.0 if right[-1].close < min(c.low for c in right[:-1]) else 0.0
        return clamp(score, 0.0, 100.0)
