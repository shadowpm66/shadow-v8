from __future__ import annotations

from shadow_v8.models import EarningsState, FundamentalState, SetupDecision, Stage, StageState


class StockFilter:
    def approve(
        self,
        fundamentals: FundamentalState,
        earnings: EarningsState,
        stage: StageState | None = None,
        setup: SetupDecision | None = None,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if earnings.blocked_for_earnings:
            return False, ["Upcoming earnings block"]
        if stage and stage.weekly_stage not in (Stage.STAGE_2, Stage.STAGE_1):
            return False, [f"Weekly stage {stage.weekly_stage.value} not eligible for long stock setup"]
        if setup and setup.direction == "SHORT":
            return False, ["Stock shorts disabled by default"]
        if fundamentals.fundamental_grade not in ("S", "A", "B"):
            return False, [f"Fundamental grade {fundamentals.fundamental_grade} not strong enough"]
        if not fundamentals.revenue_accelerating and not fundamentals.eps_accelerating:
            return False, ["No sales or EPS acceleration"]
        reasons.append(f"Fundamental grade {fundamentals.fundamental_grade}")
        if fundamentals.revenue_accelerating:
            reasons.append("Revenue acceleration approved")
        if fundamentals.eps_accelerating:
            reasons.append("EPS acceleration approved")
        if earnings.post_earnings_setup:
            reasons.append("Positive post-earnings setup allowed")
        return True, reasons
