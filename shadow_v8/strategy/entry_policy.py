from __future__ import annotations

from shadow_v8.models import AssetConfig, EntryDecision, RiskDecision, SetupDecision


class EntryPolicy:
    def decide(self, asset: AssetConfig, setup: SetupDecision, risk: RiskDecision) -> EntryDecision:
        gate = setup.metadata.get("trade_gate") or {}
        gate_status = gate.get("status")
        gate_blockers = gate.get("blockers") or []
        if setup.direction == "SHORT" and not asset.allow_short:
            return EntryDecision("SKIP", asset.symbol, setup.direction, "Shorts disabled for asset", setup=setup)
        if setup.direction == "LONG" and not asset.allow_long:
            return EntryDecision("SKIP", asset.symbol, setup.direction, "Longs disabled for asset", setup=setup)
        if gate_status == "BLOCK":
            reason = "Gate blocked: " + ", ".join(str(item) for item in gate_blockers[:4])
            return EntryDecision(
                "SKIP",
                asset.symbol,
                setup.direction,
                reason,
                setup=setup,
                metadata={"trade_gate": gate},
            )
        if risk.state == "OFF":
            return EntryDecision("SKIP", asset.symbol, setup.direction, risk.reason or "Risk state off", setup=setup)
        if setup.grade in ("S", "A+", "A"):
            return EntryDecision("ENTER", asset.symbol, setup.direction, "Setup approved", setup=setup)
        if setup.grade == "B":
            return EntryDecision("MONITOR", asset.symbol, setup.direction, "Setup close but not A-grade", setup=setup)
        return EntryDecision("WAIT", asset.symbol, setup.direction, "Setup not mature", setup=setup)

