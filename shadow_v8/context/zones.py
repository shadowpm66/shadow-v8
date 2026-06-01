from __future__ import annotations

from dataclasses import dataclass
from math import floor, log10
from typing import Any

from shadow_v8.context.adr_awr import average_range, average_weekly_range
from shadow_v8.context.market_regime import detect_market_regime
from shadow_v8.context.pivots import daily_open_pivots
from shadow_v8.context.sessions import current_session_candles, previous_session_candles, session_summary
from shadow_v8.models import Candle, ContextState, Direction
from shadow_v8.utils import clamp


@dataclass(frozen=True)
class Zone:
    name: str
    price: float
    band: float
    strength: float = 1.0
    kind: str = "level"

    def contains(self, price: float) -> bool:
        return abs(price - self.price) <= self.band


def nearest_zone(price: float, zones: list[Zone]) -> Zone | None:
    if not zones:
        return None
    return min(zones, key=lambda z: abs(price - z.price))


class ContextEngine:
    def __init__(self, max_nearest: int = 5) -> None:
        self.max_nearest = max_nearest

    def evaluate(self, candles: list[Candle], direction: Direction = "FLAT") -> ContextState:
        if not candles:
            return ContextState(reasons=["No candles for context"])
        last = candles[-1]
        price = last.close
        adr = average_range(candles, min(20, len(candles))) or max(last.high - last.low, price * 0.01)
        awr = average_weekly_range(candles) or adr * 5.0
        band = max(adr * 0.08, price * 0.002)

        zones = self._build_zones(candles, adr, awr, band)
        nearest = self._nearest_zones(price, zones, direction)
        score = self._context_score(nearest, direction)
        regime = detect_market_regime(candles)
        if regime == "trend_norm":
            score += 4.0
        elif regime == "range_hot":
            score -= 4.0
        elif regime == "trend_hot":
            score -= 2.0
        score = clamp(score, 0.0, 100.0)

        reasons = [
            f"Nearest zone {nearest[0]['name']}" if nearest else "No nearby zone",
            f"Context score {score:.1f}",
            f"Market regime {regime}",
        ]
        return ContextState(
            quality_score=round(score, 4),
            nearest_zones=nearest,
            zone_count=len(zones),
            regime=regime,
            reasons=reasons,
            metadata={
                "price": round(price, 6),
                "daily_open": round(self._daily_open(candles), 6),
                "day_high": round(max(c.high for c in self._current_day(candles)), 6),
                "day_low": round(min(c.low for c in self._current_day(candles)), 6),
                "adr": round(adr, 6),
                "awr": round(awr, 6),
                "band": round(band, 6),
                "zones": [self._zone_dict(zone, price, direction) for zone in zones],
            },
        )

    def _build_zones(self, candles: list[Candle], adr: float, awr: float, band: float) -> list[Zone]:
        last = candles[-1]
        day = self._current_day(candles)
        current_session = current_session_candles(candles)
        previous_session = previous_session_candles(candles)
        current_summary = session_summary(current_session)
        previous_summary = session_summary(previous_session)
        daily_open = self._daily_open(candles)
        zones = [
            Zone("Daily Open", daily_open, band, 1.0, "daily_open"),
            Zone("Day High", max(c.high for c in day), band, 0.9, "day_high"),
            Zone("Day Low", min(c.low for c in day), band, 0.9, "day_low"),
            Zone("ADR High", daily_open + adr, band, 0.85, "adr"),
            Zone("ADR Low", daily_open - adr, band, 0.85, "adr"),
            Zone("AWR High", daily_open + awr, band * 1.5, 0.75, "awr"),
            Zone("AWR Low", daily_open - awr, band * 1.5, 0.75, "awr"),
        ]
        if current_summary:
            zones.extend(
                [
                    Zone(f"{current_summary['label']} Session High", current_summary["high"], band, 0.95, "session"),
                    Zone(f"{current_summary['label']} Session Low", current_summary["low"], band, 0.95, "session"),
                ]
            )
        if previous_summary:
            zones.extend(
                [
                    Zone("Previous Session Open", previous_summary["open"], band, 0.8, "previous_session"),
                    Zone("Previous Session Close", previous_summary["close"], band, 0.8, "previous_session"),
                ]
            )
        zones.extend(Zone(name, price, band, 0.7, "pivot") for name, price in daily_open_pivots(daily_open, adr).items())
        zones.extend(self._psych_levels(last.close, band))
        zones.extend(self._vector_zones(candles, band))
        return self._dedupe_zones(zones)

    def _nearest_zones(self, price: float, zones: list[Zone], direction: Direction) -> list[dict[str, Any]]:
        ranked = sorted(zones, key=lambda zone: abs(price - zone.price))[: self.max_nearest]
        return [self._zone_dict(zone, price, direction) for zone in ranked]

    def _zone_dict(self, zone: Zone, price: float, direction: Direction) -> dict[str, Any]:
        distance = abs(price - zone.price)
        distance_pct = distance / max(price, 1e-9) * 100.0
        relation = "at"
        if zone.price < price:
            relation = "below"
        elif zone.price > price:
            relation = "above"
        directional_role = "neutral"
        if direction == "LONG":
            directional_role = "support" if zone.price <= price else "resistance"
        elif direction == "SHORT":
            directional_role = "resistance" if zone.price >= price else "support"
        score = max(0.0, 100.0 - (distance / max(zone.band, 1e-9)) * 25.0) * zone.strength
        return {
            "name": zone.name,
            "kind": zone.kind,
            "price": round(zone.price, 6),
            "band": round(zone.band, 6),
            "strength": round(zone.strength, 4),
            "distance": round(distance, 6),
            "distance_pct": round(distance_pct, 4),
            "contains_price": zone.contains(price),
            "relation": relation,
            "directional_role": directional_role,
            "score": round(clamp(score, 0.0, 100.0), 4),
        }

    def _context_score(self, nearest: list[dict[str, Any]], direction: Direction) -> float:
        if not nearest:
            return 0.0
        weighted = 0.0
        total_weight = 0.0
        for idx, zone in enumerate(nearest):
            weight = max(0.2, 1.0 - idx * 0.15)
            score = float(zone["score"])
            if zone["contains_price"]:
                score += 10.0
            if direction == "LONG" and zone["directional_role"] == "support":
                score += 8.0
            elif direction == "SHORT" and zone["directional_role"] == "resistance":
                score += 8.0
            weighted += clamp(score, 0.0, 100.0) * weight
            total_weight += weight
        return weighted / total_weight if total_weight else 0.0

    def _current_day(self, candles: list[Candle]) -> list[Candle]:
        date = candles[-1].timestamp.date()
        return [candle for candle in candles if candle.timestamp.date() == date] or [candles[-1]]

    def _daily_open(self, candles: list[Candle]) -> float:
        return self._current_day(candles)[0].open

    def _psych_levels(self, price: float, band: float) -> list[Zone]:
        if price <= 0:
            return []
        step = 10 ** max(0, floor(log10(price)) - 1)
        center = round(price / step) * step
        return [Zone(f"Psych {center + offset * step:g}", center + offset * step, band, 0.55, "psych") for offset in range(-3, 4)]

    def _vector_zones(self, candles: list[Candle], band: float) -> list[Zone]:
        if len(candles) < 25:
            return []
        sample = candles[-40:]
        avg_range = sum(c.high - c.low for c in sample[:-1]) / max(len(sample) - 1, 1)
        avg_volume = sum(c.volume for c in sample[:-1]) / max(len(sample) - 1, 1)
        zones: list[Zone] = []
        for idx, candle in enumerate(sample[:-1]):
            candle_range = candle.high - candle.low
            if avg_range <= 0 or avg_volume <= 0:
                continue
            is_vector = candle_range >= avg_range * 1.5 and candle.volume >= avg_volume * 1.35
            if not is_vector:
                continue
            later = sample[idx + 1 :]
            midpoint = (candle.high + candle.low) / 2.0
            recovered = any(c.low <= midpoint <= c.high for c in later)
            if not recovered:
                kind = "bullish" if candle.close >= candle.open else "bearish"
                zones.append(Zone(f"Unrecovered {kind.title()} Vector", midpoint, band * 1.25, 0.7, "vector"))
        return zones[-5:]

    def _dedupe_zones(self, zones: list[Zone]) -> list[Zone]:
        deduped: list[Zone] = []
        for zone in zones:
            if any(abs(zone.price - existing.price) <= min(zone.band, existing.band) * 0.25 and zone.name == existing.name for existing in deduped):
                continue
            deduped.append(zone)
        return deduped
