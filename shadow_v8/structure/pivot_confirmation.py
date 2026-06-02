from __future__ import annotations

from shadow_v8.models import Candle, Direction, PivotConfirmation
from shadow_v8.structure.indicators import atr


class PivotConfirmationEngine:
    def __init__(self, retest_tolerance_pct: float = 1.0, shift_atr_mult: float = 0.6) -> None:
        self.retest_tolerance_pct = retest_tolerance_pct
        self.shift_atr_mult = shift_atr_mult

    def evaluate(self, candles: list[Candle], pivot: float | None, direction: Direction) -> PivotConfirmation:
        if pivot is None or len(candles) < 8:
            return PivotConfirmation(pivot=pivot, reasons=["No pivot or not enough candles"])
        recent = candles[-8:]
        last = candles[-1]
        atr_value = atr(candles) or 0.0
        tolerance = max(pivot * self.retest_tolerance_pct / 100.0, atr_value * 0.25)
        if direction == "LONG":
            reclaimed = any(c.close > pivot for c in recent[:-3])
            retest_candles = [
                c
                for c in recent[-5:-1]
                if (pivot - tolerance) <= c.low <= (pivot + tolerance) or c.low <= pivot <= c.high
            ]
            retested = bool(retest_candles)
            retest_hold = retested and last.close > pivot and last.low >= pivot - tolerance
            prior_high = max(c.high for c in recent[:-1])
            shift_distance = last.close - max(pivot, prior_high)
            shift = retest_hold and shift_distance >= max(0.0, atr_value * self.shift_atr_mult)
            strength = (shift_distance / max(atr_value, pivot * 0.01)) * 100.0 if shift else 0.0
            distance_to_pivot = pivot - last.close
            state = self._state(
                confirmed=bool(reclaimed and retested and retest_hold and shift),
                reclaimed=reclaimed,
                retested=retested,
                retest_hold=retest_hold,
                direction=direction,
            )
        elif direction == "SHORT":
            reclaimed = any(c.close < pivot for c in recent[:-3])
            retest_candles = [
                c
                for c in recent[-5:-1]
                if (pivot - tolerance) <= c.high <= (pivot + tolerance) or c.low <= pivot <= c.high
            ]
            retested = bool(retest_candles)
            retest_hold = retested and last.close < pivot and last.high <= pivot + tolerance
            prior_low = min(c.low for c in recent[:-1])
            shift_distance = min(pivot, prior_low) - last.close
            shift = retest_hold and shift_distance >= max(0.0, atr_value * self.shift_atr_mult)
            strength = (shift_distance / max(atr_value, pivot * 0.01)) * 100.0 if shift else 0.0
            distance_to_pivot = last.close - pivot
            state = self._state(
                confirmed=bool(reclaimed and retested and retest_hold and shift),
                reclaimed=reclaimed,
                retested=retested,
                retest_hold=retest_hold,
                direction=direction,
            )
        else:
            reclaimed = retested = retest_hold = shift = False
            strength = 0.0
            shift_distance = 0.0
            distance_to_pivot = 0.0
            retest_candles = []
            state = "no_trade_direction"
        retest_timestamp = retest_candles[-1].timestamp.isoformat() if retest_candles else None
        shift_distance_atr = shift_distance / atr_value if atr_value > 0 else None
        shift_required = atr_value * self.shift_atr_mult if atr_value > 0 else 0.0
        shift_required_atr = self.shift_atr_mult if atr_value > 0 else None
        shift_progress = shift_distance / shift_required if shift_required > 0 else None
        if shift:
            shift_progress_state = "confirmed"
        elif retest_hold and shift_distance < 0:
            shift_progress_state = "adverse"
        elif retest_hold and shift_distance > 0:
            shift_progress_state = "insufficient"
        elif retest_hold:
            shift_progress_state = "not_started"
        else:
            shift_progress_state = "not_ready"
        if shift_progress_state == "confirmed":
            shift_progress_bucket = "confirmed"
        elif shift_progress_state in ("adverse", "not_ready"):
            shift_progress_bucket = shift_progress_state
        elif shift_progress is not None and shift_progress >= 0.5:
            shift_progress_bucket = "near_confirmation"
        elif shift_progress is not None and shift_progress >= 0.25:
            shift_progress_bucket = "building"
        elif shift_progress is not None and shift_progress > 0:
            shift_progress_bucket = "early"
        else:
            shift_progress_bucket = "not_started"
        distance_to_pivot_pct = distance_to_pivot / max(pivot, 1e-9) * 100.0 if pivot else None
        distance_to_pivot_atr = distance_to_pivot / atr_value if atr_value > 0 else None
        return PivotConfirmation(
            pivot=pivot,
            reclaimed_or_lost=reclaimed,
            retested=retested,
            retest_hold=retest_hold,
            shift_away=shift,
            shift_strength=strength,
            confirmed=reclaimed and retested and retest_hold and shift,
            reasons=[
                "Pivot reclaimed/lost" if reclaimed else "Pivot not reclaimed/lost",
                "Pivot retested" if retested else "Pivot not retested",
                "Retest held" if retest_hold else "Retest did not hold",
                "Shift away confirmed" if shift else "Shift away not confirmed",
            ],
            metadata={
                "tolerance": round(tolerance, 4),
                "atr": round(atr_value, 4) if atr_value else None,
                "shift_distance": round(shift_distance, 4),
                "shift_distance_atr": round(shift_distance_atr, 4) if shift_distance_atr is not None else None,
                "shift_required": round(shift_required, 4) if shift_required else None,
                "shift_required_atr": round(shift_required_atr, 4) if shift_required_atr is not None else None,
                "shift_progress": round(shift_progress, 4) if shift_progress is not None else None,
                "shift_progress_state": shift_progress_state,
                "shift_progress_bucket": shift_progress_bucket,
                "distance_to_pivot": round(distance_to_pivot, 4),
                "distance_to_pivot_pct": round(distance_to_pivot_pct, 4) if distance_to_pivot_pct is not None else None,
                "distance_to_pivot_atr": round(distance_to_pivot_atr, 4) if distance_to_pivot_atr is not None else None,
                "state": state,
                "shift_atr_mult": self.shift_atr_mult,
                "retest_count": len(retest_candles),
                "last_retest_timestamp": retest_timestamp,
                "retest_tolerance_pct": self.retest_tolerance_pct,
            },
        )

    def _state(
        self,
        *,
        confirmed: bool,
        reclaimed: bool,
        retested: bool,
        retest_hold: bool,
        direction: Direction,
    ) -> str:
        if confirmed:
            return "confirmed"
        if not reclaimed:
            return "awaiting_reclaim" if direction == "LONG" else "awaiting_loss"
        if not retested:
            return "awaiting_retest"
        if not retest_hold:
            return "retest_failed"
        return "awaiting_shift_away"
