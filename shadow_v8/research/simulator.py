from __future__ import annotations

from datetime import datetime
from typing import Any

from shadow_v8.models import AssetConfig, Candle, EntryDecision, PositionState
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
        decision = self.exit_policy.decide(self.position, candle.close)
        if decision.action == "EXIT":
            return self.close_position(candle, decision.reason)
        return None

    def close_open_at_end(self, candle: Candle) -> dict[str, Any] | None:
        if self.position is None:
            return None
        self._mark_to_market(candle)
        return self.close_position(candle, "End of replay")

    def close_position(self, candle: Candle, reason: str) -> dict[str, Any]:
        if self.position is None:
            raise RuntimeError("No open synthetic position to close")
        position = self.position
        r_multiple = self._r_multiple(candle.close)
        setup_metadata = position.metadata.get("setup_metadata", {})
        trade = {
            "symbol": position.symbol,
            "direction": position.direction,
            "qty": position.qty,
            "entry": round(position.entry, 6),
            "exit": round(candle.close, 6),
            "stop": round(position.stop, 6),
            "opened_at": position.opened_at.isoformat(),
            "closed_at": candle.timestamp.isoformat(),
            "reason": reason,
            "setup_class": position.setup_class,
            "grade": position.grade,
            "setup_metadata": setup_metadata,
            "confirmation": self._confirmation_summary(setup_metadata),
            "duration_bars": int(position.metadata.get("bars_held", 0)),
            "duration_seconds": self._duration_seconds(position.opened_at, candle.timestamp),
            "mae": round(float(position.metadata.get("mae", 0.0)), 6),
            "mfe": round(float(position.metadata.get("mfe", 0.0)), 6),
            "r_multiple": round(r_multiple, 6),
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
        return abs(self.position.entry - self.position.stop)

    def _r_multiple(self, exit_price: float) -> float:
        if self.position is None:
            return 0.0
        risk = self._risk_per_unit()
        if risk <= 0:
            return 0.0
        if self.position.direction == "LONG":
            return (exit_price - self.position.entry) / risk
        return (self.position.entry - exit_price) / risk
