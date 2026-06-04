from __future__ import annotations

from shadow_v8.models import AssetConfig, EntryDecision, RiskDecision, SetupDecision


class EntryPolicy:
    def __init__(
        self,
        allow_near_entry_watch: bool = False,
        allow_countertrend_reclaim_entry: bool = False,
    ) -> None:
        self.allow_near_entry_watch = allow_near_entry_watch
        self.allow_countertrend_reclaim_entry = allow_countertrend_reclaim_entry

    def decide(self, asset: AssetConfig, setup: SetupDecision, risk: RiskDecision) -> EntryDecision:
        gate = setup.metadata.get("trade_gate") or {}
        gate_status = gate.get("status")
        gate_blockers = gate.get("blockers") or []
        gate_watch_reasons = gate.get("watch_reasons") or []
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
        if gate_status == "WATCH":
            if self.allow_near_entry_watch and risk.state != "OFF" and self._near_entry_watch(setup, gate):
                reason = "Near-entry watch override: " + ", ".join(str(item) for item in gate_watch_reasons[:4])
                return EntryDecision(
                    "ENTER",
                    asset.symbol,
                    setup.direction,
                    reason,
                    setup=setup,
                    metadata={"trade_gate": gate, "near_entry_watch_override": True},
                )
            if (
                self.allow_countertrend_reclaim_entry
                and risk.state != "OFF"
                and self._countertrend_reclaim_watch(setup, gate)
            ):
                reason = "Countertrend reclaim calibration: " + ", ".join(str(item) for item in gate_watch_reasons[:4])
                return EntryDecision(
                    "ENTER",
                    asset.symbol,
                    setup.direction,
                    reason,
                    setup=setup,
                    metadata={"trade_gate": gate, "countertrend_reclaim_override": True},
                )
            reason = "Gate watching: " + ", ".join(str(item) for item in gate_watch_reasons[:4])
            return EntryDecision(
                "MONITOR",
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

    def _near_entry_watch(self, setup: SetupDecision, gate: dict) -> bool:
        watch_reasons = set(str(item) for item in gate.get("watch_reasons", []))
        warnings = set(str(item) for item in gate.get("warnings", []))
        confirmations = set(str(item) for item in gate.get("confirmations", []))
        if setup.grade not in ("S+", "S", "A+"):
            return False
        if setup.final_score < 90:
            return False
        if watch_reasons != {"pivot_not_retested"}:
            return False
        if "missing_volume_quality" in warnings:
            return False
        required_confirmations = {"constructive_base_or_vcp", "volume_quality"}
        if not required_confirmations.issubset(confirmations):
            return False
        if "context_supportive" not in confirmations:
            return False
        vcp = setup.metadata.get("vcp_confirmation") or {}
        if not bool(vcp.get("directional_close_shift")):
            return False
        pivot = setup.metadata.get("pivot_confirmation") or {}
        pivot_metadata = pivot.get("metadata") or {}
        shift_state = str(pivot.get("shift_progress_state") or pivot_metadata.get("shift_progress_state") or "")
        shift_bucket = str(pivot.get("shift_progress_bucket") or pivot_metadata.get("shift_progress_bucket") or "")
        if shift_state in {"adverse", "not_ready"} or shift_bucket == "not_ready":
            return False
        shift_progress = pivot.get("shift_progress")
        if shift_progress is None:
            shift_progress = pivot_metadata.get("shift_progress")
        if shift_progress is not None and float(shift_progress) < 0:
            return False
        if not any(item.startswith("stage_") and item.endswith("_permission") for item in confirmations):
            return False
        if not any(item in confirmations for item in ("stop_distance_good", "stop_distance_acceptable")):
            return False
        return True

    def _countertrend_reclaim_watch(self, setup: SetupDecision, gate: dict) -> bool:
        watch_reasons = set(str(item) for item in gate.get("watch_reasons", []))
        warnings = set(str(item) for item in gate.get("warnings", []))
        confirmations = set(str(item) for item in gate.get("confirmations", []))
        blockers = set(str(item) for item in gate.get("blockers", []))
        if setup.direction not in ("LONG", "SHORT"):
            return False
        if setup.grade not in ("S+", "S", "A+"):
            return False
        if setup.final_score < 88:
            return False
        if "countertrend_reclaim_calibration" not in watch_reasons:
            return False
        if "countertrend_reclaim_candidate" not in confirmations:
            return False
        if blockers:
            return False
        if "missing_volume_quality" in warnings:
            return False
        required_confirmations = {"constructive_base_or_vcp", "volume_quality"}
        if not required_confirmations.issubset(confirmations):
            return False
        if not any(item in confirmations for item in ("context_supportive", "reference_confluence")):
            return False
        if not any(item in confirmations for item in ("stop_distance_good", "stop_distance_acceptable")):
            return False
        pivot = setup.metadata.get("pivot_confirmation") or {}
        if not bool(pivot.get("reclaimed_or_lost")):
            return False
        if not bool(pivot.get("confirmed")):
            return False
        pivot_metadata = pivot.get("metadata") or {}
        shift_state = str(pivot.get("shift_progress_state") or pivot_metadata.get("shift_progress_state") or "")
        shift_bucket = str(pivot.get("shift_progress_bucket") or pivot_metadata.get("shift_progress_bucket") or "")
        if shift_state in {"adverse", "not_ready"} or shift_bucket == "not_ready":
            return False
        return True
