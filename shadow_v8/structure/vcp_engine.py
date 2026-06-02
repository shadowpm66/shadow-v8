from __future__ import annotations

from shadow_v8.models import Candle, Direction, VcpState
from shadow_v8.structure.indicators import atr
from shadow_v8.structure.volume_signature import breakout_volume_ratio, has_breakout_volume, volume_dry_up_ratio
from shadow_v8.utils import clamp


class VcpEngine:
    def evaluate(
        self,
        candles: list[Candle],
        lookback: int = 60,
        pivot: float | None = None,
        direction: Direction = "LONG",
        stop_distance_quality: str = "UNKNOWN",
    ) -> VcpState:
        if len(candles) < 30:
            return VcpState(reasons=["Not enough candles for VCP"])
        sample = candles[-lookback:]
        chunks = self._chunks(sample, 4)
        ranges = [max(c.high for c in chunk) - min(c.low for c in chunk) for chunk in chunks if chunk]
        contraction_count = 0
        for prev, cur in zip(ranges, ranges[1:]):
            if cur < prev:
                contraction_count += 1
        vols = [sum(c.volume for c in chunk) / len(chunk) for chunk in chunks if chunk]
        dry_up_ratio = volume_dry_up_ratio(sample, min(20, len(sample)))
        volume_dry = dry_up_ratio <= 0.7
        breakout_ratio = breakout_volume_ratio(sample, min(20, len(sample) - 1))
        breakout_volume = has_breakout_volume(sample, min(20, len(sample) - 1), multiplier=1.35)
        lows = [min(c.low for c in chunk) for chunk in chunks if chunk]
        highs = [max(c.high for c in chunk) for chunk in chunks if chunk]
        higher_lows = len(lows) >= 3 and lows[-1] >= lows[-2] >= lows[-3]
        lower_highs = len(highs) >= 3 and highs[-1] <= highs[-2] <= highs[-3]
        direction_constructive = (
            (direction == "LONG" and higher_lows)
            or (direction == "SHORT" and lower_highs)
            or (direction == "FLAT" and (higher_lows or lower_highs))
        )
        last = sample[-1].close
        atr_value = atr(candles) or 0.0
        atr_values = [self._chunk_atr(chunk) for chunk in chunks if len(chunk) >= 2]
        first_atr = atr_values[0] if atr_values else 0.0
        last_atr = atr_values[-1] if atr_values else 0.0
        atr_compression_pct = (1.0 - last_atr / first_atr) * 100.0 if first_atr > 0 else 0.0
        atr_compressing = len(atr_values) >= 2 and last_atr < first_atr * 0.8
        last_range = ranges[-1] if ranges else 0.0
        prior_range = ranges[0] if ranges else 0.0
        range_contracted_pct = (1.0 - last_range / prior_range) * 100.0 if prior_range > 0 else 0.0
        near_pivot = False
        stop_quality = stop_distance_quality
        if pivot:
            stop_distance_pct = abs(last - pivot) / max(last, 1e-9) * 100.0
            near_pivot = stop_distance_pct <= 5.0
        elif atr_value > 0 and last > 0:
            stop_distance_pct = (last_range / last) * 100.0
        else:
            stop_distance_pct = None
        if stop_quality == "UNKNOWN" and stop_distance_pct is not None:
            if stop_distance_pct <= 3.0:
                stop_quality = "GOOD"
            elif stop_distance_pct <= 6.0:
                stop_quality = "ACCEPTABLE"
            else:
                stop_quality = "WIDE"

        score = contraction_count * 16.0
        score += 18.0 if volume_dry else 0.0
        score += 10.0 if breakout_volume else 0.0
        score += 12.0 if direction != "SHORT" and higher_lows else 0.0
        score += 12.0 if direction == "SHORT" and lower_highs else 0.0
        score += 5.0 if direction == "FLAT" and (higher_lows or lower_highs) else 0.0
        score += 10.0 if range_contracted_pct >= 35.0 else 0.0
        score += 10.0 if atr_compressing else 0.0
        score += 8.0 if near_pivot else 0.0
        score += 8.0 if stop_quality == "GOOD" else 4.0 if stop_quality == "ACCEPTABLE" else -8.0 if stop_quality == "WIDE" else 0.0
        score = clamp(score, 0.0, 100.0)
        confirmation_missing: list[str] = []
        if contraction_count < 1:
            confirmation_missing.append("vcp_no_contraction")
        if not direction_constructive:
            confirmation_missing.append("vcp_direction_not_constructive")
        if not near_pivot:
            confirmation_missing.append("vcp_not_near_pivot")
        if stop_quality not in ("GOOD", "ACCEPTABLE"):
            confirmation_missing.append("vcp_stop_distance_not_valid")
        if not volume_dry:
            confirmation_missing.append("vcp_volume_not_dry")
        if not breakout_volume:
            confirmation_missing.append("vcp_breakout_volume_missing")
        if not atr_compressing:
            confirmation_missing.append("vcp_atr_not_compressing")
        if range_contracted_pct < 35.0:
            confirmation_missing.append("vcp_range_not_contracted")
        return VcpState(
            is_tight=score >= 60.0,
            tightness_score=score,
            contraction_count=contraction_count,
            volume_dry=volume_dry,
            higher_lows=higher_lows,
            lower_highs=lower_highs,
            stop_distance_quality=stop_quality,
            reasons=[
                f"{contraction_count} range contractions",
                "Volume dry-up" if volume_dry else "Volume not dry",
                "Breakout/reclaim volume" if breakout_volume else "Breakout/reclaim volume not confirmed",
                "Higher lows" if higher_lows else "Higher lows not confirmed",
                "Lower highs" if lower_highs else "Lower highs not confirmed",
                "ATR compression" if atr_compressing else "ATR compression not confirmed",
                f"Range contracted {range_contracted_pct:.1f}%",
                f"Stop distance quality {stop_quality}",
            ],
            metadata={
                "ranges": [round(r, 4) for r in ranges],
                "average_volumes": [round(v, 2) for v in vols],
                "direction": direction,
                "direction_constructive": direction_constructive,
                "range_contracted_pct": round(range_contracted_pct, 2),
                "atr_values": [round(value, 4) for value in atr_values],
                "atr_compression_pct": round(atr_compression_pct, 2),
                "atr_compressing": atr_compressing,
                "near_pivot": near_pivot,
                "volume_dry_up_ratio": round(dry_up_ratio, 4),
                "breakout_volume_ratio": round(breakout_ratio, 4),
                "breakout_volume": breakout_volume,
                "stop_distance_pct": round(stop_distance_pct, 3) if stop_distance_pct is not None else None,
                "atr": round(atr_value, 4) if atr_value else None,
                "confirmation_missing": confirmation_missing,
            },
        )

    def _chunks(self, values: list[Candle], count: int) -> list[list[Candle]]:
        size = max(1, len(values) // count)
        return [values[i : i + size] for i in range(0, len(values), size)][-count:]

    def _chunk_atr(self, candles: list[Candle]) -> float:
        if len(candles) < 2:
            return 0.0
        ranges = []
        for prev, cur in zip(candles, candles[1:]):
            ranges.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
        return sum(ranges) / len(ranges) if ranges else 0.0
