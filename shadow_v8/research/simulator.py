from __future__ import annotations

from datetime import datetime
from typing import Any

from shadow_v8.config import EXECUTION_CONFIG
from shadow_v8.models import AssetConfig, Candle, EntryDecision, PositionState, StructureSignal
from shadow_v8.strategy.exit_policy import ExitPolicy


class Simulator:
    def __init__(self, exit_policy: ExitPolicy | None = None, qty: float = 1.0) -> None:
        self.exit_policy = exit_policy or ExitPolicy()
        self.qty = qty
        self.position: PositionState | None = None
        self.trades: list[dict[str, Any]] = []

    def has_open_position(self) -> bool:
        return self.position is not None

    def open_position(self, asset: AssetConfig, decision: EntryDecision, candle: Candle) -> PositionState:
        entry = decision.entry if decision.entry is not None else candle.close
        stop = decision.stop
        if stop is None:
            stop = candle.low if decision.direction == "LONG" else candle.high
        position = PositionState(
            symbol=asset.symbol,
            asset_class=asset.asset_class,
            broker="paper",
            direction=decision.direction,
            qty=self.qty,
            entry=entry,
            stop=stop,
            opened_at=candle.timestamp,
            setup_class=decision.setup.setup_class if decision.setup else "",
            grade=decision.setup.grade if decision.setup else "",
            metadata={
                "entry_reason": decision.reason,
                "entry_score": decision.setup.final_score if decision.setup else None,
                "setup_metadata": decision.setup.metadata if decision.setup else {},
                "mae": 0.0,
                "mfe": 0.0,
                "max_r": 0.0,
                "min_r": 0.0,
                "bars_held": 0,
                "initial_qty": self.qty,
                "initial_stop": stop,
                "initial_risk_per_unit": abs(entry - stop),
                "realized_r": 0.0,
                "closed_qty": 0.0,
                "lifecycle_events": [],
                "target": decision.target,
            },
        )
        self.position = position
        self._mark_to_market(candle)
        return position

    def on_bar(self, candle: Candle) -> dict[str, Any] | None:
        if self.position is None:
            return None
        self.position.metadata["bars_held"] = int(self.position.metadata.get("bars_held", 0)) + 1
        self._mark_to_market(candle)
        if self._stop_hit(candle):
            return self.close_position_at_price(candle, self.position.stop, "Replay hard stop")
        self._maybe_partial(candle)
        self._maybe_break_even()
        self._maybe_trail(candle.close)
        if self._target_hit(candle):
            target = float(self.position.metadata["target"])
            return self.close_position_at_price(candle, target, "Replay target")
        decision = self.exit_policy.decide(self.position, candle.close)
        if decision.action == "EXIT":
            return self.close_position(candle, decision.reason)
        return None

    def apply_structure_exit(self, candle: Candle, structure: StructureSignal) -> dict[str, Any] | None:
        if self.position is None or not self._is_opposite_structure(structure):
            return None
        event = {
            "type": "EXIT_SIGNAL",
            "reason": "Replay opposite structure exit",
            "structure_type": structure.type,
            "structure_direction": structure.direction,
            "quality_score": round(float(structure.quality_score), 6),
            "neckline": round(float(structure.neckline), 6) if structure.neckline is not None else None,
        }
        self._append_lifecycle_event(event)
        return self.close_position(candle, "Replay opposite structure exit")

    def close_open_at_end(self, candle: Candle) -> dict[str, Any] | None:
        if self.position is None:
            return None
        self._mark_to_market(candle)
        self._maybe_partial(candle)
        self._maybe_break_even()
        self._maybe_trail(candle.close)
        return self.close_position(candle, "End of replay")

    def close_position(self, candle: Candle, reason: str) -> dict[str, Any]:
        return self.close_position_at_price(candle, candle.close, reason)

    def close_position_at_price(self, candle: Candle, exit_price: float, reason: str) -> dict[str, Any]:
        if self.position is None:
            raise RuntimeError("No open synthetic position to close")
        self._mark_to_market(candle)
        position = self.position
        r_multiple = self._total_r_multiple(exit_price)
        exit_type = self._exit_type(reason)
        exit_diagnostics = self._exit_diagnostics(position, reason, r_multiple)
        setup_metadata = position.metadata.get("setup_metadata", {})
        trade = {
            "symbol": position.symbol,
            "direction": position.direction,
            "qty": position.qty,
            "initial_qty": round(float(position.metadata.get("initial_qty", position.qty)), 6),
            "closed_qty": round(float(position.metadata.get("closed_qty", 0.0)) + position.qty, 6),
            "entry": round(position.entry, 6),
            "exit": round(exit_price, 6),
            "stop": round(position.stop, 6),
            "initial_stop": round(float(position.metadata.get("initial_stop", position.stop)), 6),
            "opened_at": position.opened_at.isoformat(),
            "closed_at": candle.timestamp.isoformat(),
            "reason": reason,
            "exit_reason": reason,
            "exit_type": exit_type,
            "setup_class": position.setup_class,
            "grade": position.grade,
            "setup_metadata": setup_metadata,
            "confirmation": self._confirmation_summary(setup_metadata),
            "duration_bars": int(position.metadata.get("bars_held", 0)),
            "duration_seconds": self._duration_seconds(position.opened_at, candle.timestamp),
            "mae": round(float(position.metadata.get("mae", 0.0)), 6),
            "mfe": round(float(position.metadata.get("mfe", 0.0)), 6),
            "r_multiple": round(r_multiple, 6),
            "realized_r": round(float(position.metadata.get("realized_r", 0.0)), 6),
            "partial_taken": bool(position.partial_taken),
            "break_even_moved": bool(position.break_even_moved),
            "lifecycle_events": list(position.metadata.get("lifecycle_events", [])),
            "exit_diagnostics": exit_diagnostics,
        }
        self.trades.append(trade)
        self.position = None
        return trade

    def summary(self) -> dict[str, Any]:
        wins = [trade for trade in self.trades if trade["r_multiple"] > 0]
        net_r = sum(float(trade["r_multiple"]) for trade in self.trades)
        return {
            "trades": self.trades,
            "trade_count": len(self.trades),
            "win_rate": round(len(wins) / len(self.trades), 4) if self.trades else 0.0,
            "net_r": round(net_r, 6),
        }

    def run(self) -> dict[str, Any]:
        return self.summary()

    def _duration_seconds(self, opened_at: datetime, closed_at: datetime) -> float:
        return round((closed_at - opened_at).total_seconds(), 6)

    def _confirmation_summary(self, setup_metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "base": setup_metadata.get("base_confirmation", {}),
            "vcp": setup_metadata.get("vcp_confirmation", {}),
            "pivot": setup_metadata.get("pivot_confirmation", {}),
            "nested": setup_metadata.get("nested_confirmation", {}),
            "context": setup_metadata.get("context_confluence", {}),
            "stop_distance_quality": setup_metadata.get("stop_distance_quality", "UNKNOWN"),
            "trade_gate": setup_metadata.get("trade_gate", {}),
        }

    def _mark_to_market(self, candle: Candle) -> None:
        if self.position is None:
            return
        position = self.position
        risk = self._risk_per_unit()
        if risk <= 0:
            return
        if position.direction == "LONG":
            mfe = candle.high - position.entry
            mae = candle.low - position.entry
        else:
            mfe = position.entry - candle.low
            mae = position.entry - candle.high
        position.metadata["mfe"] = max(float(position.metadata.get("mfe", 0.0)), mfe)
        position.metadata["mae"] = min(float(position.metadata.get("mae", 0.0)), mae)
        position.metadata["max_r"] = max(float(position.metadata.get("max_r", 0.0)), mfe / risk)
        position.metadata["min_r"] = min(float(position.metadata.get("min_r", 0.0)), mae / risk)

    def _risk_per_unit(self) -> float:
        if self.position is None:
            return 0.0
        return float(self.position.metadata.get("initial_risk_per_unit") or abs(self.position.entry - self.position.stop))

    def _r_multiple(self, exit_price: float) -> float:
        if self.position is None:
            return 0.0
        risk = self._risk_per_unit()
        if risk <= 0:
            return 0.0
        if self.position.direction == "LONG":
            return (exit_price - self.position.entry) / risk
        return (self.position.entry - exit_price) / risk

    def _total_r_multiple(self, exit_price: float) -> float:
        if self.position is None:
            return 0.0
        realized = float(self.position.metadata.get("realized_r", 0.0))
        remaining_qty = float(self.position.qty)
        initial_qty = float(self.position.metadata.get("initial_qty") or remaining_qty or 1.0)
        remaining_fraction = remaining_qty / initial_qty if initial_qty > 0 else 1.0
        return realized + (self._r_multiple(exit_price) * remaining_fraction)

    def _exit_type(self, reason: str) -> str:
        normalized = reason.lower().strip()
        if "opposite structure" in normalized:
            return "opposite_structure"
        if "hard stop" in normalized:
            return "hard_stop"
        if "end of replay" in normalized:
            return "end_of_replay"
        if "target" in normalized:
            return "target"
        if "partial" in normalized:
            return "partial_take_profit"
        if "break" in normalized and "even" in normalized:
            return "break_even_stop"
        if "trail" in normalized:
            return "trailing_stop"
        return "policy_exit"

    def _exit_diagnostics(self, position: PositionState, reason: str, r_multiple: float) -> dict[str, Any]:
        max_r = float(position.metadata.get("max_r", 0.0))
        min_r = float(position.metadata.get("min_r", 0.0))
        partial_trigger = float(EXECUTION_CONFIG["paper_partial_r"])
        break_even_trigger = float(EXECUTION_CONFIG["paper_break_even_r"])
        trail_trigger = float(EXECUTION_CONFIG["paper_trail_start_r"])
        exit_type = self._exit_type(reason)
        return {
            "exit_type": exit_type,
            "exit_reason": reason,
            "r_multiple": round(r_multiple, 6),
            "max_r": round(max_r, 6),
            "min_r": round(min_r, 6),
            "mae": round(float(position.metadata.get("mae", 0.0)), 6),
            "mfe": round(float(position.metadata.get("mfe", 0.0)), 6),
            "bars_held": int(position.metadata.get("bars_held", 0)),
            "hit_hard_stop": exit_type == "hard_stop",
            "opposite_structure_exit": exit_type == "opposite_structure",
            "closed_at_end": exit_type == "end_of_replay",
            "partial_candidate": max_r >= partial_trigger,
            "break_even_candidate": max_r >= break_even_trigger,
            "trail_candidate": max_r >= trail_trigger,
            "partial_trigger_r": partial_trigger,
            "break_even_trigger_r": break_even_trigger,
            "trail_trigger_r": trail_trigger,
        }

    def _is_opposite_structure(self, structure: StructureSignal) -> bool:
        if self.position is None:
            return False
        if float(structure.quality_score) < 50.0:
            return False
        metadata = structure.metadata or {}
        if metadata.get("neckline_ok") is False:
            return False
        if self.position.direction == "LONG":
            return structure.direction == "SHORT" and structure.type == "M"
        if self.position.direction == "SHORT":
            return structure.direction == "LONG" and structure.type == "W"
        return False

    def _maybe_partial(self, candle: Candle) -> dict[str, Any] | None:
        if self.position is None or self.position.partial_taken:
            return None
        trigger_r = float(EXECUTION_CONFIG["paper_partial_r"])
        fraction = max(0.0, min(1.0, float(EXECUTION_CONFIG["paper_partial_fraction"])))
        risk = self._risk_per_unit()
        if trigger_r <= 0 or fraction <= 0 or risk <= 0:
            return None
        position = self.position
        hit = (
            (candle.high - position.entry) / risk >= trigger_r
            if position.direction == "LONG"
            else (position.entry - candle.low) / risk >= trigger_r
        )
        if not hit:
            return None
        close_qty = round(position.qty * fraction, 8)
        if close_qty <= 0 or close_qty >= position.qty:
            return None
        exit_price = position.entry + risk * trigger_r if position.direction == "LONG" else position.entry - risk * trigger_r
        initial_qty = float(position.metadata.get("initial_qty") or position.qty)
        realized_r = (close_qty / initial_qty) * trigger_r if initial_qty > 0 else 0.0
        position.qty = round(position.qty - close_qty, 8)
        position.partial_taken = True
        position.metadata["closed_qty"] = round(float(position.metadata.get("closed_qty", 0.0)) + close_qty, 8)
        position.metadata["realized_r"] = round(float(position.metadata.get("realized_r", 0.0)) + realized_r, 6)
        event = {
            "type": "PARTIAL",
            "reason": "Replay partial take profit",
            "price": round(exit_price, 6),
            "qty": close_qty,
            "r_gain": round(realized_r, 6),
            "trigger_r": trigger_r,
        }
        self._append_lifecycle_event(event)
        return event

    def _maybe_break_even(self) -> dict[str, Any] | None:
        if self.position is None or self.position.break_even_moved:
            return None
        if float(self.position.metadata.get("max_r", 0.0)) < float(EXECUTION_CONFIG["paper_break_even_r"]):
            return None
        position = self.position
        better = (position.direction == "LONG" and position.entry > position.stop) or (
            position.direction == "SHORT" and position.entry < position.stop
        )
        if not better:
            return None
        position.stop = round(position.entry, 8)
        position.break_even_moved = True
        event = {
            "type": "MOVE_STOP",
            "reason": "Replay stop to break-even",
            "new_stop": round(position.stop, 6),
        }
        self._append_lifecycle_event(event)
        return event

    def _maybe_trail(self, last_price: float) -> dict[str, Any] | None:
        if self.position is None:
            return None
        max_r = float(self.position.metadata.get("max_r", 0.0))
        start = float(EXECUTION_CONFIG["paper_trail_start_r"])
        giveback = float(EXECUTION_CONFIG["paper_trail_giveback_r"])
        risk = self._risk_per_unit()
        if max_r < start or giveback <= 0 or risk <= 0:
            return None
        position = self.position
        if position.direction == "LONG":
            new_stop = position.entry + max(0.0, max_r - giveback) * risk
            if new_stop <= position.stop or new_stop >= last_price:
                return None
        else:
            new_stop = position.entry - max(0.0, max_r - giveback) * risk
            if new_stop >= position.stop or new_stop <= last_price:
                return None
        position.stop = round(new_stop, 8)
        event = {
            "type": "MOVE_STOP",
            "reason": "Replay trailing stop",
            "new_stop": round(position.stop, 6),
        }
        self._append_lifecycle_event(event)
        return event

    def _stop_hit(self, candle: Candle) -> bool:
        if self.position is None:
            return False
        if self.position.direction == "LONG":
            return candle.low <= self.position.stop
        if self.position.direction == "SHORT":
            return candle.high >= self.position.stop
        return False

    def _target_hit(self, candle: Candle) -> bool:
        if self.position is None or self.position.metadata.get("target") is None:
            return False
        target = float(self.position.metadata["target"])
        if self.position.direction == "LONG":
            return candle.high >= target
        if self.position.direction == "SHORT":
            return candle.low <= target
        return False

    def _append_lifecycle_event(self, event: dict[str, Any]) -> None:
        if self.position is None:
            return
        event = dict(event)
        event["bars_held"] = int(self.position.metadata.get("bars_held", 0))
        self.position.metadata.setdefault("lifecycle_events", []).append(event)
