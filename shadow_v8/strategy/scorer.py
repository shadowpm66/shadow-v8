from __future__ import annotations

from typing import Any

from shadow_v8.models import (
    BaseState,
    ContextState,
    EarningsState,
    FundamentalState,
    NestedStructureState,
    PivotConfirmation,
    SetupDecision,
    Stage,
    StageState,
    StructureSignal,
    VcpState,
)
from shadow_v8.utils import clamp


class Scorer:
    def score(
        self,
        symbol: str,
        stage: StageState,
        base: BaseState,
        vcp: VcpState,
        structure: StructureSignal,
        nested: NestedStructureState,
        pivot: PivotConfirmation,
        context: ContextState | None = None,
        fundamentals: FundamentalState | None = None,
        earnings: EarningsState | None = None,
    ) -> SetupDecision:
        reasons: list[str] = []
        technical = 0.0
        base_confirmed = bool(base.metadata.get("confirmed")) if base.metadata else False
        stop_distance_quality = self._stop_distance_quality(base, vcp)
        if stage.weekly_stage == Stage.STAGE_2 and structure.direction == "LONG":
            technical += 18
            reasons.append("Weekly Stage 2")
        if stage.weekly_stage == Stage.STAGE_4 and structure.direction == "SHORT":
            technical += 18
            reasons.append("Weekly Stage 4")
        if base.found:
            technical += base.quality_score * 0.20
            reasons.extend(base.reasons[:2])
            if base_confirmed:
                technical += 6
                reasons.append("Base confirmed near pivot")
            if stop_distance_quality == "GOOD":
                technical += 4
                reasons.append("Stop distance good")
            elif stop_distance_quality == "WIDE":
                technical -= 6
                reasons.append("Stop distance wide")
        if vcp.is_tight:
            technical += vcp.tightness_score * 0.18
            reasons.append("VCP tight")
        elif vcp.contraction_count >= 2:
            technical += min(10.0, vcp.tightness_score * 0.10)
            reasons.append("VCP forming")
        if vcp.volume_dry:
            technical += 4
            reasons.append("Volume dry-up")
        if bool(vcp.metadata.get("breakout_volume")):
            technical += 5
            reasons.append("Breakout volume confirmed")
        if bool(vcp.metadata.get("atr_compressing")):
            technical += 4
            reasons.append("ATR compression")
        if structure.direction == "LONG" and vcp.higher_lows:
            technical += 3
            reasons.append("VCP higher lows")
        if structure.direction == "SHORT" and vcp.lower_highs:
            technical += 3
            reasons.append("VCP lower highs")
        if self._constructive_vcp(vcp, structure.direction, stop_distance_quality):
            technical += 6
            reasons.append("Constructive VCP near pivot")
        if structure.type != "NONE":
            technical += structure.quality_score * 0.20
            reasons.append(f"{structure.type} structure")
        if nested.confirmed:
            technical += nested.quality_score * 0.12
            reasons.append(nested.pattern)
        if pivot.confirmed:
            technical += 18
            reasons.append("Pivot retest and shift-away confirmed")
        elif pivot.retest_hold:
            technical += 10
            reasons.append("Pivot retest held")
        if context:
            technical += context.quality_score * 0.10
            if context.nearest_zones:
                reasons.append(f"Context confluence near {context.nearest_zones[0]['name']}")
            if context.regime == "trend_norm":
                reasons.append("Constructive market regime")

        fundamental_score = 0.0
        if fundamentals:
            if fundamentals.revenue_accelerating:
                fundamental_score += 35
                reasons.append("Revenue accelerating")
            if fundamentals.eps_accelerating:
                fundamental_score += 35
                reasons.append("EPS accelerating")
            if fundamentals.fcf_positive:
                fundamental_score += 10
            if fundamentals.gross_margin_expanding or fundamentals.operating_margin_expanding:
                fundamental_score += 10
        if earnings and earnings.blocked_for_earnings:
            reasons.append("Upcoming earnings block")

        technical = clamp(technical, 0, 100)
        fundamental_score = clamp(fundamental_score, 0, 100)
        if fundamentals:
            final = technical * 0.65 + fundamental_score * 0.35
        else:
            final = technical
        if earnings and earnings.blocked_for_earnings:
            final = min(final, 50)

        trade_gate = self._trade_gate(
            stage=stage,
            base=base,
            vcp=vcp,
            structure=structure,
            pivot=pivot,
            context=context,
            earnings=earnings,
            stop_distance_quality=stop_distance_quality,
        )
        if trade_gate["status"] == "BLOCK":
            final = min(final, 54)
            reasons.append(f"Gate blocked: {', '.join(trade_gate['blockers'][:3])}")
        elif trade_gate["status"] == "WATCH":
            final = max(final, 55) if final >= 45 else final
            reasons.append(f"Gate watching: {', '.join(trade_gate['watch_reasons'][:3])}")
        elif trade_gate["warnings"]:
            reasons.append(f"Gate warnings: {', '.join(trade_gate['warnings'][:3])}")

        grade = "REJECT"
        if final >= 90:
            grade = "S"
        elif final >= 85:
            grade = "A+"
        elif final >= 75:
            grade = "A"
        elif final >= 65:
            grade = "B"
        elif final >= 55:
            grade = "C"

        setup_class = self._setup_class(stage, vcp, structure, nested, pivot, fundamentals)
        return SetupDecision(
            symbol=symbol,
            direction=structure.direction,
            setup_class=setup_class,
            grade=grade,
            technical_score=technical,
            fundamental_score=fundamental_score,
            final_score=clamp(final, 0, 100),
            reasons=reasons,
            metadata={
                "base_confirmation": self._base_confirmation(base, stop_distance_quality),
                "vcp_confirmation": self._vcp_confirmation(vcp),
                "pivot_confirmation": self._pivot_confirmation(pivot),
                "nested_confirmation": self._nested_confirmation(nested),
                "context_confluence": self._context_confluence(context),
                "stop_distance_quality": stop_distance_quality,
                "trade_gate": trade_gate,
            },
        )

    def _setup_class(
        self,
        stage: StageState,
        vcp: VcpState,
        structure: StructureSignal,
        nested: NestedStructureState,
        pivot: PivotConfirmation,
        fundamentals: FundamentalState | None,
    ) -> str:
        parts: list[str] = []
        parts.append(stage.weekly_stage.value.upper())
        if fundamentals and (fundamentals.revenue_accelerating or fundamentals.eps_accelerating):
            parts.append("ACCELERATION")
        if vcp.is_tight:
            parts.append("VCP")
        if structure.type != "NONE":
            parts.append(structure.type)
        if nested.confirmed:
            parts.append(nested.pattern)
        elif nested.pattern in ("W_WITHIN_W", "M_WITHIN_M", "MIXED"):
            parts.append(nested.pattern)
        if pivot.confirmed:
            parts.append("RETEST_SHIFT")
        elif pivot.retest_hold:
            parts.append("RETEST_HOLD")
        return "_".join(parts) if parts else "NONE"

    def _stop_distance_quality(self, base: BaseState, vcp: VcpState) -> str:
        base_quality = str(base.metadata.get("stop_distance_quality", "UNKNOWN")) if base.metadata else "UNKNOWN"
        if base_quality != "UNKNOWN":
            return base_quality
        return vcp.stop_distance_quality

    def _base_confirmation(self, base: BaseState, stop_distance_quality: str) -> dict:
        return {
            "found": base.found,
            "confirmed": bool(base.metadata.get("confirmed")) if base.metadata else False,
            "quality_score": round(base.quality_score, 4),
            "duration_bars": base.duration_bars,
            "depth_pct": round(base.depth_pct, 4) if base.depth_pct is not None else None,
            "pivot": round(base.pivot, 6) if base.pivot is not None else None,
            "near_pivot": bool(base.metadata.get("near_pivot")) if base.metadata else False,
            "tight_close_count": int(base.metadata.get("tight_close_count", 0)) if base.metadata else 0,
            "min_tight_closes": int(base.metadata.get("min_tight_closes", 0)) if base.metadata else 0,
            "range_tight": bool(base.metadata.get("range_tight")) if base.metadata else False,
            "close_range_tight": bool(base.metadata.get("close_range_tight")) if base.metadata else False,
            "tight_structure": bool(base.metadata.get("tight_structure")) if base.metadata else False,
            "confirmation_mode": base.metadata.get("confirmation_mode", "none") if base.metadata else "none",
            "range_atr_multiple": base.metadata.get("range_atr_multiple") if base.metadata else None,
            "tight_range_atr_mult": base.metadata.get("tight_range_atr_mult") if base.metadata else None,
            "close_tight_pct": base.metadata.get("close_tight_pct") if base.metadata else None,
            "stop_distance_pct": base.metadata.get("stop_distance_pct") if base.metadata else None,
            "stop_distance_quality": stop_distance_quality,
            "confirmation_missing": list(base.metadata.get("confirmation_missing", [])) if base.metadata else [],
        }

    def _pivot_confirmation(self, pivot: PivotConfirmation) -> dict:
        return {
            "pivot": round(pivot.pivot, 6) if pivot.pivot is not None else None,
            "reclaimed_or_lost": pivot.reclaimed_or_lost,
            "retested": pivot.retested,
            "retest_hold": pivot.retest_hold,
            "shift_away": pivot.shift_away,
            "confirmed": pivot.confirmed,
            "shift_strength": round(pivot.shift_strength, 4),
            "metadata": pivot.metadata,
        }

    def _vcp_confirmation(self, vcp: VcpState) -> dict:
        return {
            "is_tight": vcp.is_tight,
            "tightness_score": round(vcp.tightness_score, 4),
            "contraction_count": vcp.contraction_count,
            "volume_dry_up": vcp.volume_dry,
            "breakout_volume": bool(vcp.metadata.get("breakout_volume")),
            "breakout_volume_ratio": vcp.metadata.get("breakout_volume_ratio"),
            "volume_dry_up_ratio": vcp.metadata.get("volume_dry_up_ratio"),
            "higher_lows": vcp.higher_lows,
            "lower_highs": vcp.lower_highs,
            "direction_constructive": bool(vcp.metadata.get("direction_constructive")),
            "atr_compressing": bool(vcp.metadata.get("atr_compressing")),
            "atr_compression_pct": vcp.metadata.get("atr_compression_pct"),
            "range_contracted_pct": vcp.metadata.get("range_contracted_pct"),
            "stop_distance_quality": vcp.stop_distance_quality,
            "near_pivot": bool(vcp.metadata.get("near_pivot")),
            "ranges": vcp.metadata.get("ranges", []),
            "average_volumes": vcp.metadata.get("average_volumes", []),
            "confirmation_missing": list(vcp.metadata.get("confirmation_missing", [])),
        }

    def _constructive_vcp(self, vcp: VcpState, direction: str, stop_distance_quality: str) -> bool:
        direction_ok = (
            (direction == "LONG" and vcp.higher_lows)
            or (direction == "SHORT" and vcp.lower_highs)
            or direction == "FLAT"
        )
        return (
            vcp.contraction_count >= 1
            and direction_ok
            and bool(vcp.metadata.get("near_pivot"))
            and stop_distance_quality in ("GOOD", "ACCEPTABLE")
        )

    def _base_vcp_watch_reasons(
        self,
        base: BaseState,
        vcp: VcpState,
        direction: str,
        stop_distance_quality: str,
        base_mode: str = "none",
    ) -> list[str]:
        reasons: list[str] = []
        base_confirmed = bool(base.metadata.get("confirmed")) if base.metadata else False
        if not base.found:
            reasons.append("base_not_found")
        elif not base_confirmed:
            reasons.append("base_not_confirmed")
        elif base_mode == "close_compression":
            reasons.append("close_compression_needs_vcp_confirmation")

        if not vcp.is_tight:
            reasons.append("vcp_not_tight")
        if vcp.contraction_count < 1:
            reasons.append("vcp_no_contraction")

        direction_ok = (
            (direction == "LONG" and vcp.higher_lows)
            or (direction == "SHORT" and vcp.lower_highs)
            or direction == "FLAT"
        )
        if not direction_ok:
            reasons.append("vcp_direction_not_constructive")
        if not bool(vcp.metadata.get("near_pivot")):
            reasons.append("vcp_not_near_pivot")
        if stop_distance_quality not in ("GOOD", "ACCEPTABLE"):
            reasons.append("stop_distance_not_valid")
        return reasons or ["immature_base_or_vcp"]

    def _nested_confirmation(self, nested: NestedStructureState) -> dict:
        return {
            "pattern": nested.pattern,
            "confirmed": nested.confirmed,
            "quality_score": round(nested.quality_score, 4),
            "outer_type": nested.outer_structure.type if nested.outer_structure else "NONE",
            "outer_direction": nested.outer_structure.direction if nested.outer_structure else "FLAT",
            "outer_quality_score": round(nested.outer_structure.quality_score, 4) if nested.outer_structure else 0.0,
            "inner_type": nested.inner_structure.type if nested.inner_structure else "NONE",
            "inner_direction": nested.inner_structure.direction if nested.inner_structure else "FLAT",
            "inner_quality_score": round(nested.inner_structure.quality_score, 4) if nested.inner_structure else 0.0,
        }

    def _context_confluence(self, context: ContextState | None) -> dict:
        if context is None:
            return {
                "quality_score": 0.0,
                "nearest_zones": [],
                "zone_count": 0,
                "regime": "UNKNOWN",
                "metadata": {},
            }
        return {
            "quality_score": round(context.quality_score, 4),
            "nearest_zones": context.nearest_zones,
            "zone_count": context.zone_count,
            "regime": context.regime,
            "metadata": context.metadata,
            "reasons": context.reasons,
        }

    def _trade_gate(
        self,
        *,
        stage: StageState,
        base: BaseState,
        vcp: VcpState,
        structure: StructureSignal,
        pivot: PivotConfirmation,
        context: ContextState | None,
        earnings: EarningsState | None,
        stop_distance_quality: str,
    ) -> dict[str, Any]:
        blockers: list[str] = []
        watch_reasons: list[str] = []
        warnings: list[str] = []
        confirmations: list[str] = []

        if structure.direction not in ("LONG", "SHORT"):
            blockers.append("no_trade_direction")
        elif structure.type == "NONE" or structure.quality_score < 35:
            blockers.append("weak_structure")
        else:
            confirmations.append(f"{structure.type}_{structure.direction}")

        if structure.direction == "LONG":
            if not stage.long_permission:
                blockers.append("stage_blocks_long")
            else:
                confirmations.append("stage_long_permission")
        elif structure.direction == "SHORT":
            if not stage.short_permission:
                blockers.append("stage_blocks_short")
            else:
                confirmations.append("stage_short_permission")

        base_confirmed = bool(base.metadata.get("confirmed")) if base.metadata else False
        constructive_vcp = self._constructive_vcp(vcp, structure.direction, stop_distance_quality)
        base_mode = str(base.metadata.get("confirmation_mode", "none")) if base.metadata else "none"
        high_confidence_base = base_confirmed and (base_mode != "close_compression" or constructive_vcp)
        constructive_base_or_vcp = high_confidence_base or vcp.is_tight or constructive_vcp
        if constructive_base_or_vcp:
            confirmations.append("constructive_base_or_vcp")
        else:
            watch_reasons.extend(
                self._base_vcp_watch_reasons(base, vcp, structure.direction, stop_distance_quality, base_mode)
            )

        if pivot.confirmed:
            confirmations.append("pivot_confirmed")
        else:
            pivot_state = str((pivot.metadata or {}).get("state") or "")
            if pivot_state == "awaiting_reclaim":
                watch_reasons.append("pivot_awaiting_reclaim")
            elif pivot_state == "awaiting_loss":
                watch_reasons.append("pivot_awaiting_loss")
            elif pivot_state == "awaiting_retest":
                watch_reasons.append("pivot_not_retested")
            elif pivot_state == "retest_failed":
                watch_reasons.append("pivot_retest_failed")
            elif pivot_state == "awaiting_shift_away" or pivot.retest_hold:
                watch_reasons.append("pivot_waiting_for_shift_away")
            elif not pivot.reclaimed_or_lost:
                watch_reasons.append("pivot_not_reclaimed_or_lost")
            elif not pivot.retested:
                watch_reasons.append("pivot_not_retested")
            else:
                watch_reasons.append("pivot_retest_failed")

        if stop_distance_quality == "WIDE":
            blockers.append("wide_stop_distance")
        elif stop_distance_quality in ("GOOD", "ACCEPTABLE"):
            confirmations.append(f"stop_distance_{stop_distance_quality.lower()}")

        reference = ((context.metadata or {}).get("reference_confluence", {}) if context else {})
        favorable_count = int(reference.get("favorable_count") or 0)
        obstacle_count = int(reference.get("obstacle_count") or 0)
        at_level_count = int(reference.get("at_level_count") or 0)
        reference_flags = list(reference.get("flags") or [])
        if obstacle_count >= 2 and obstacle_count >= favorable_count + 2:
            blockers.append("against_reference_confluence")
        elif obstacle_count >= 2 and obstacle_count > favorable_count:
            watch_reasons.append("mixed_reference_confluence")
        elif favorable_count > 0 or "at_reference_level" in reference_flags:
            confirmations.append("reference_confluence")
        elif obstacle_count and at_level_count:
            watch_reasons.append("reference_level_overhead")
        else:
            warnings.append("no_nearby_reference_support")

        if context:
            if context.quality_score < 30:
                warnings.append("weak_context")
            elif context.quality_score >= 55:
                confirmations.append("context_supportive")
        else:
            warnings.append("missing_context")

        volume_confirmed = bool(vcp.volume_dry or vcp.metadata.get("breakout_volume"))
        if volume_confirmed:
            confirmations.append("volume_quality")
        else:
            warnings.append("missing_volume_quality")

        if earnings and earnings.blocked_for_earnings:
            blockers.append("earnings_block")

        status = "ALLOW"
        if blockers:
            status = "BLOCK"
        elif watch_reasons:
            status = "WATCH"

        return {
            "status": status,
            "blockers": blockers,
            "watch_reasons": watch_reasons,
            "warnings": warnings,
            "confirmations": confirmations,
            "confirmed_count": len(confirmations),
            "required": [
                "directional_structure",
                "stage_permission",
                "constructive_base_or_vcp",
                "pivot_confirmation",
                "valid_stop_distance",
            ],
        }
