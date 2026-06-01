from __future__ import annotations

from shadow_v8.models import ExitDecision, PositionState


class ExitPolicy:
    def decide(self, position: PositionState, last_price: float | None) -> ExitDecision:
        if last_price is None:
            return ExitDecision("HOLD", position.symbol, "No price")
        if position.direction == "LONG" and last_price <= position.stop:
            return ExitDecision("EXIT", position.symbol, "Hard stop")
        if position.direction == "SHORT" and last_price >= position.stop:
            return ExitDecision("EXIT", position.symbol, "Hard stop")
        return ExitDecision("HOLD", position.symbol, "No exit condition")

