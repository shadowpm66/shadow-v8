from __future__ import annotations

from shadow_v8.models import BaseState, Candle, Direction
from shadow_v8.structure.indicators import atr
from shadow_v8.utils import clamp


class BaseEngine:
    def __init__(
        self,
        min_bars: int = 15,
        max_bars: int = 90,
        max_depth_pct: float = 35.0,
        tight_range_atr_mult: float = 1.25,
        min_tight_closes: int = 5,
    ) -> None:
        self.min_bars = min_bars
        self.max_bars = max_bars
        self.max_depth_pct = max_depth_pct
        self.tight_range_atr_mult = tight_range_atr_mult
        self.min_tight_closes = min_tight_closes

    def evaluate(self, candles: list[Candle], direction: Direction = "LONG") -> BaseState:
        if len(candles) < self.min_bars:
            return BaseState(found=False, reasons=["Not enough candles for base detection"])

        window = candles[-self.max_bars :]
        best: BaseState | None = None
        atr_value = atr(candles) or 0.0

        for size in range(self.min_bars, min(len(window), self.max_bars) + 1):
            sample = window[-size:]
            high = max(c.high for c in sample)
            low = min(c.low for c in sample)
            last = sample[-1].close
            if last <= 0 or high <= low:
                continue

            depth_pct = (high - low) / last * 100.0
            if depth_pct > self.max_depth_pct:
                continue

            recent = sample[-min(8, len(sample)) :]
            recent_range = max(c.high for c in recent) - min(c.low for c in recent)
            range_tight = atr_value > 0 and recent_range <= atr_value * self.tight_range_atr_mult
            closes = [c.close for c in recent]
            close_tight_pct = ((max(closes) - min(closes)) / max(last, 1e-9)) * 100.0
            close_position = (last - low) / max(high - low, 1e-9)
            near_pivot = last >= high - (high - low) * 0.25 if direction == "LONG" else last <= low + (high - low) * 0.25
            support_rising = self._higher_lows(sample)
            resistance_falling = self._lower_highs(sample)

            volume_dry = False
            if len(sample) >= 20:
                old_vol = sum(c.volume for c in sample[-20:-10]) / 10
                new_vol = sum(c.volume for c in sample[-10:]) / 10
                volume_dry = new_vol < old_vol * 0.75 if old_vol > 0 else False

            pivot = high if direction == "LONG" else low
            tight_closes = self._tight_close_count(sample)
            stop_distance_pct = self._stop_distance_pct(last, high, low, direction)
            stop_distance_quality = self._stop_distance_quality(stop_distance_pct)
            confirmation_missing: list[str] = []
            if not range_tight:
                confirmation_missing.append("range_not_tight")
            if tight_closes < self.min_tight_closes:
                confirmation_missing.append("not_enough_tight_closes")
            if not near_pivot:
                confirmation_missing.append("not_near_pivot")
            if stop_distance_quality not in ("GOOD", "ACCEPTABLE"):
                confirmation_missing.append("stop_distance_not_valid")
            base_confirmed = (
                range_tight
                and tight_closes >= self.min_tight_closes
                and near_pivot
                and stop_distance_quality in ("GOOD", "ACCEPTABLE")
            )
            tightness_score = clamp(100.0 - depth_pct * 1.8 - close_tight_pct * 4.0, 0.0, 100.0)
            if range_tight:
                tightness_score += 10.0
            if volume_dry:
                tightness_score += 10.0
            if tight_closes >= self.min_tight_closes:
                tightness_score += 8.0
            tightness_score = clamp(tightness_score, 0.0, 100.0)

            quality = tightness_score
            if size >= 25:
                quality += 5.0
            if depth_pct <= 20:
                quality += 5.0
            if near_pivot:
                quality += 8.0
            if direction == "LONG" and support_rising:
                quality += 7.0
            if direction == "SHORT" and resistance_falling:
                quality += 7.0
            if base_confirmed:
                quality += 8.0
            elif stop_distance_quality == "WIDE":
                quality -= 8.0
            quality = clamp(quality, 0.0, 100.0)

            state = BaseState(
                found=True,
                high=high,
                low=low,
                mid=(high + low) / 2.0,
                pivot=pivot,
                duration_bars=size,
                depth_pct=depth_pct,
                tightness_score=tightness_score,
                volume_dry_up=volume_dry,
                quality_score=quality,
                reasons=[
                    f"Base depth {depth_pct:.1f}%",
                    f"Duration {size} bars",
                    "Recent range tight" if range_tight else "Recent range not tight",
                    "Volume dry-up" if volume_dry else "No volume dry-up",
                    "Price tight near pivot" if near_pivot else "Price not yet near pivot",
                    f"Stop distance {stop_distance_quality}",
                    "Base confirmed" if base_confirmed else "Base not confirmed",
                    "Rising lows" if support_rising else "Rising lows not confirmed",
                ],
                metadata={
                    "confirmed": base_confirmed,
                    "close_position_in_base": round(close_position, 3),
                    "close_tight_pct": round(close_tight_pct, 3),
                    "tight_close_count": tight_closes,
                    "min_tight_closes": self.min_tight_closes,
                    "range_tight": range_tight,
                    "range_atr_multiple": round(recent_range / atr_value, 3) if atr_value > 0 else None,
                    "tight_range_atr_mult": self.tight_range_atr_mult,
                    "near_pivot": near_pivot,
                    "stop_distance_pct": round(stop_distance_pct, 3) if stop_distance_pct is not None else None,
                    "stop_distance_quality": stop_distance_quality,
                    "support_rising": support_rising,
                    "resistance_falling": resistance_falling,
                    "confirmation_missing": confirmation_missing,
                },
            )

            if best is None or state.quality_score > best.quality_score:
                best = state

        return best or BaseState(found=False, reasons=["No valid base found"])

    def _tight_close_count(self, candles: list[Candle]) -> int:
        if len(candles) < 2:
            return 0
        count = 0
        for prev, cur in zip(candles[-10:-1], candles[-9:]):
            spread_pct = abs(cur.close - prev.close) / max(cur.close, 1e-9) * 100.0
            if spread_pct <= 1.0:
                count += 1
        return count

    def _higher_lows(self, candles: list[Candle]) -> bool:
        if len(candles) < 12:
            return False
        chunks = self._chunks(candles, 3)
        lows = [min(c.low for c in chunk) for chunk in chunks if chunk]
        return len(lows) == 3 and lows[2] >= lows[1] >= lows[0]

    def _lower_highs(self, candles: list[Candle]) -> bool:
        if len(candles) < 12:
            return False
        chunks = self._chunks(candles, 3)
        highs = [max(c.high for c in chunk) for chunk in chunks if chunk]
        return len(highs) == 3 and highs[2] <= highs[1] <= highs[0]

    def _chunks(self, candles: list[Candle], count: int) -> list[list[Candle]]:
        size = max(1, len(candles) // count)
        return [candles[i : i + size] for i in range(0, len(candles), size)][-count:]

    def _stop_distance_pct(self, last: float, high: float, low: float, direction: Direction) -> float | None:
        if last <= 0:
            return None
        if direction == "SHORT":
            return max(0.0, high - last) / last * 100.0
        return max(0.0, last - low) / last * 100.0

    def _stop_distance_quality(self, distance_pct: float | None) -> str:
        if distance_pct is None:
            return "UNKNOWN"
        if distance_pct <= 4.0:
            return "GOOD"
        if distance_pct <= 8.0:
            return "ACCEPTABLE"
        return "WIDE"
