from __future__ import annotations

from shadow_v8.models import (
    AssetConfig,
    BaseState,
    ContextState,
    EarningsState,
    NestedStructureState,
    PivotConfirmation,
    Stage,
    StageState,
    StructureSignal,
    VcpState,
)
from shadow_v8.strategy.entry_policy import EntryPolicy
from shadow_v8.strategy.risk_manager import RiskManager
from shadow_v8.strategy.scorer import Scorer


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def asset() -> AssetConfig:
    return AssetConfig(symbol="GATE", asset_class="crypto", broker="paper", allow_long=True, allow_short=True)


def stage() -> StageState:
    return StageState(
        weekly_stage=Stage.STAGE_2,
        daily_stage=Stage.STAGE_2,
        long_permission=True,
        short_permission=False,
        risk_bias="RISK_ON",
    )


def base() -> BaseState:
    return BaseState(
        found=True,
        pivot=100.0,
        quality_score=80.0,
        metadata={"confirmed": True, "near_pivot": True, "stop_distance_quality": "GOOD", "stop_distance_pct": 3.0},
    )


def vcp() -> VcpState:
    return VcpState(
        is_tight=True,
        tightness_score=82.0,
        contraction_count=3,
        volume_dry=True,
        higher_lows=True,
        stop_distance_quality="GOOD",
        metadata={"near_pivot": True, "breakout_volume": True, "atr_compressing": True},
    )


def structure() -> StructureSignal:
    return StructureSignal(type="W", direction="LONG", quality_score=82.0, neckline=100.0)


def nested() -> NestedStructureState:
    return NestedStructureState(pattern="W_WITHIN_W", confirmed=True, quality_score=70.0)


def pivot() -> PivotConfirmation:
    return PivotConfirmation(
        pivot=100.0,
        reclaimed_or_lost=True,
        retested=True,
        retest_hold=True,
        shift_away=True,
        shift_strength=1.8,
        confirmed=True,
    )


def context() -> ContextState:
    return ContextState(
        quality_score=68.0,
        nearest_zones=[{"name": "Daily Open"}],
        zone_count=8,
        regime="trend_norm",
        metadata={
            "reference_confluence": {
                "favorable_count": 2,
                "obstacle_count": 0,
                "flags": ["at_reference_level", "stacked_directional_support"],
            }
        },
    )


def mixed_reference_context() -> ContextState:
    return ContextState(
        quality_score=58.0,
        nearest_zones=[{"name": "ADR Low"}],
        zone_count=10,
        regime="range_norm",
        metadata={
            "reference_confluence": {
                "favorable_count": 2,
                "obstacle_count": 3,
                "at_level_count": 5,
                "flags": ["at_reference_level", "stacked_directional_support", "nearby_directional_resistance"],
            }
        },
    )


def stacked_obstacle_context() -> ContextState:
    return ContextState(
        quality_score=45.0,
        nearest_zones=[{"name": "Session High"}],
        zone_count=10,
        regime="range_norm",
        metadata={
            "reference_confluence": {
                "favorable_count": 0,
                "obstacle_count": 3,
                "at_level_count": 3,
                "flags": ["at_reference_level", "nearby_directional_resistance"],
            }
        },
    )


def check_approved_gate() -> None:
    setup = Scorer().score(
        "GATE",
        stage(),
        base(),
        vcp(),
        structure(),
        nested(),
        pivot(),
        context=context(),
        earnings=EarningsState(),
    )
    gate = setup.metadata["trade_gate"]
    risk = RiskManager().evaluate(asset(), setup)
    entry = EntryPolicy().decide(asset(), setup, risk)
    assert_true(gate["status"] == "ALLOW", "High-quality setup should pass gate")
    assert_true("pivot_confirmed" in gate["confirmations"], "Gate should confirm pivot")
    assert_true(entry.action == "ENTER", "A+ quality gated setup should enter")


def check_blocked_gate() -> None:
    weak_structure = StructureSignal(type="NONE", direction="FLAT", quality_score=0.0)
    weak_pivot = PivotConfirmation(pivot=100.0, retested=True, retest_hold=True, confirmed=False)
    setup = Scorer().score(
        "BLOCK",
        stage(),
        base(),
        vcp(),
        weak_structure,
        NestedStructureState(),
        weak_pivot,
        context=context(),
    )
    gate = setup.metadata["trade_gate"]
    risk = RiskManager().evaluate(asset(), setup)
    entry = EntryPolicy().decide(asset(), setup, risk)
    assert_true(gate["status"] == "BLOCK", "Weak setup should be gate blocked")
    assert_true("no_trade_direction" in gate["blockers"], "Gate should block missing direction")
    assert_true(entry.action == "SKIP", "Blocked gate should skip entry")
    assert_true("Gate blocked" in entry.reason, "Skip reason should explain gate blockers")


def check_watch_gate() -> None:
    developing_pivot = PivotConfirmation(pivot=100.0, retested=True, retest_hold=True, confirmed=False)
    developing_vcp = VcpState(
        is_tight=False,
        tightness_score=58.0,
        contraction_count=1,
        volume_dry=False,
        higher_lows=True,
        stop_distance_quality="ACCEPTABLE",
        metadata={"near_pivot": True},
    )
    setup = Scorer().score(
        "WATCH",
        stage(),
        BaseState(found=False),
        developing_vcp,
        structure(),
        NestedStructureState(),
        developing_pivot,
        context=context(),
    )
    gate = setup.metadata["trade_gate"]
    risk = RiskManager().evaluate(asset(), setup)
    entry = EntryPolicy().decide(asset(), setup, risk)
    assert_true(gate["status"] == "WATCH", "Developing setup should reach watch state")
    assert_true("pivot_waiting_for_shift_away" in gate["watch_reasons"], "Gate should explain watch reason")
    assert_true(entry.action == "MONITOR", "Watch gate should monitor instead of skip")
    assert_true("Gate watching" in entry.reason, "Monitor reason should explain watch reasons")


def check_pivot_watch_reason_details() -> None:
    scenarios = [
        (
            "not_reclaimed",
            PivotConfirmation(
                pivot=100.0,
                reclaimed_or_lost=False,
                retested=False,
                retest_hold=False,
                confirmed=False,
                metadata={"state": "awaiting_reclaim"},
            ),
            "pivot_awaiting_reclaim",
        ),
        (
            "not_retested",
            PivotConfirmation(pivot=100.0, reclaimed_or_lost=True, retested=False, retest_hold=False, confirmed=False),
            "pivot_not_retested",
        ),
        (
            "retest_failed",
            PivotConfirmation(pivot=100.0, reclaimed_or_lost=True, retested=True, retest_hold=False, confirmed=False),
            "pivot_retest_failed",
        ),
    ]
    for label, pivot_state, expected_reason in scenarios:
        setup = Scorer().score(
            f"PIVOT_{label}",
            stage(),
            base(),
            vcp(),
            structure(),
            nested(),
            pivot_state,
            context=context(),
        )
        gate = setup.metadata["trade_gate"]
        assert_true(gate["status"] == "WATCH", f"{label} pivot setup should be watched")
        assert_true(expected_reason in gate["watch_reasons"], f"{label} should report {expected_reason}")


def check_base_vcp_watch_reason_details() -> None:
    weak_base = BaseState(
        found=True,
        pivot=100.0,
        quality_score=48.0,
        metadata={"confirmed": False, "near_pivot": False, "stop_distance_quality": "WIDE", "stop_distance_pct": 9.0},
    )
    weak_vcp = VcpState(
        is_tight=False,
        tightness_score=28.0,
        contraction_count=0,
        volume_dry=False,
        higher_lows=False,
        stop_distance_quality="WIDE",
        metadata={"near_pivot": False},
    )
    setup = Scorer().score(
        "BASEVCP",
        stage(),
        weak_base,
        weak_vcp,
        structure(),
        nested(),
        pivot(),
        context=context(),
    )
    gate = setup.metadata["trade_gate"]
    assert_true(gate["status"] == "BLOCK", "Wide stop base/VCP setup should be blocked")
    assert_true("base_not_confirmed" in gate["watch_reasons"], "Gate should report unconfirmed base")
    assert_true("vcp_not_tight" in gate["watch_reasons"], "Gate should report loose VCP")
    assert_true("vcp_no_contraction" in gate["watch_reasons"], "Gate should report missing contractions")
    assert_true("vcp_direction_not_constructive" in gate["watch_reasons"], "Gate should report direction mismatch")
    assert_true("vcp_not_near_pivot" in gate["watch_reasons"], "Gate should report pivot distance")
    assert_true("stop_distance_not_valid" in gate["watch_reasons"], "Gate should report invalid stop distance")


def check_close_compression_base_needs_vcp_confirmation() -> None:
    close_compression_base = BaseState(
        found=True,
        pivot=100.0,
        quality_score=82.0,
        metadata={
            "confirmed": True,
            "near_pivot": True,
            "stop_distance_quality": "GOOD",
            "stop_distance_pct": 1.5,
            "confirmation_mode": "close_compression",
        },
    )
    weak_vcp = VcpState(
        is_tight=False,
        tightness_score=42.0,
        contraction_count=1,
        volume_dry=False,
        higher_lows=False,
        stop_distance_quality="GOOD",
        metadata={"near_pivot": True},
    )
    setup = Scorer().score(
        "CLOSEBASE",
        stage(),
        close_compression_base,
        weak_vcp,
        structure(),
        nested(),
        pivot(),
        context=context(),
    )
    gate = setup.metadata["trade_gate"]
    risk = RiskManager().evaluate(asset(), setup)
    entry = EntryPolicy().decide(asset(), setup, risk)
    assert_true(gate["status"] == "WATCH", "Close compression base should need VCP confirmation")
    assert_true(
        "close_compression_needs_vcp_confirmation" in gate["watch_reasons"],
        "Gate should report close compression needs VCP confirmation",
    )
    assert_true(entry.action == "MONITOR", "Close compression without VCP confirmation should monitor")


def check_developing_directional_vcp_watch() -> None:
    developing_vcp = VcpState(
        is_tight=False,
        tightness_score=58.0,
        contraction_count=2,
        volume_dry=False,
        higher_lows=False,
        stop_distance_quality="GOOD",
        metadata={
            "near_pivot": True,
            "is_near_tight": True,
            "directional_close_shift": True,
            "directional_evidence": "close_shift",
            "breakout_volume": True,
        },
    )
    developing_pivot = PivotConfirmation(
        pivot=100.0,
        reclaimed_or_lost=True,
        retested=True,
        retest_hold=True,
        confirmed=False,
        metadata={"state": "awaiting_shift_away"},
    )
    setup = Scorer().score(
        "DEVVCP",
        stage(),
        BaseState(found=False),
        developing_vcp,
        structure(),
        nested(),
        developing_pivot,
        context=context(),
    )
    gate = setup.metadata["trade_gate"]
    risk = RiskManager().evaluate(asset(), setup)
    entry = EntryPolicy().decide(asset(), setup, risk)
    vcp_confirmation = setup.metadata["vcp_confirmation"]
    assert_true(gate["status"] == "WATCH", "Developing directional VCP should stay in watch state")
    assert_true(
        "developing_directional_vcp" in gate["confirmations"],
        "Gate should mark developing directional VCP as a confirmation",
    )
    assert_true(
        "developing_directional_vcp" in gate["watch_reasons"],
        "Gate should explain developing directional VCP watch",
    )
    assert_true(
        vcp_confirmation["developing_directional"] is True,
        "VCP confirmation should expose developing directional flag",
    )
    assert_true(entry.action == "MONITOR", "Developing directional VCP should monitor, not enter")


def check_short_pivot_awaiting_loss_reason() -> None:
    short_stage = StageState(
        weekly_stage=Stage.STAGE_4,
        daily_stage=Stage.STAGE_4,
        long_permission=False,
        short_permission=True,
        risk_bias="RISK_ON",
    )
    short_structure = StructureSignal(type="M", direction="SHORT", quality_score=82.0, neckline=100.0)
    short_vcp = VcpState(
        is_tight=True,
        tightness_score=82.0,
        contraction_count=3,
        volume_dry=True,
        lower_highs=True,
        stop_distance_quality="GOOD",
        metadata={"near_pivot": True, "breakout_volume": True, "atr_compressing": True},
    )
    short_pivot = PivotConfirmation(
        pivot=100.0,
        reclaimed_or_lost=False,
        retested=False,
        retest_hold=False,
        confirmed=False,
        metadata={"state": "awaiting_loss"},
    )
    setup = Scorer().score(
        "PIVOT_SHORT",
        short_stage,
        base(),
        short_vcp,
        short_structure,
        NestedStructureState(pattern="M_WITHIN_M", confirmed=True, quality_score=70.0),
        short_pivot,
        context=context(),
    )
    gate = setup.metadata["trade_gate"]
    assert_true(gate["status"] == "WATCH", "Short pivot awaiting loss should be watched")
    assert_true("pivot_awaiting_loss" in gate["watch_reasons"], "Short pivot should report awaiting loss")


def check_pivot_state_precedes_retest_hold() -> None:
    pivot_state = PivotConfirmation(
        pivot=100.0,
        reclaimed_or_lost=False,
        retested=True,
        retest_hold=True,
        shift_away=True,
        confirmed=False,
        metadata={"state": "awaiting_reclaim"},
    )
    setup = Scorer().score(
        "PIVOT_ORDER",
        stage(),
        base(),
        vcp(),
        structure(),
        nested(),
        pivot_state,
        context=context(),
    )
    gate = setup.metadata["trade_gate"]
    assert_true("pivot_awaiting_reclaim" in gate["watch_reasons"], "Pivot state should explain missing reclaim")
    assert_true("pivot_waiting_for_shift_away" not in gate["watch_reasons"], "Retest hold should not hide missing reclaim")


def check_pivot_shift_progress_reasons() -> None:
    insufficient_pivot = PivotConfirmation(
        pivot=100.0,
        reclaimed_or_lost=True,
        retested=True,
        retest_hold=True,
        shift_away=False,
        confirmed=False,
        metadata={"state": "awaiting_shift_away", "shift_progress_state": "insufficient"},
    )
    adverse_pivot = PivotConfirmation(
        pivot=100.0,
        reclaimed_or_lost=True,
        retested=True,
        retest_hold=True,
        shift_away=False,
        confirmed=False,
        metadata={"state": "awaiting_shift_away", "shift_progress_state": "adverse"},
    )
    insufficient_setup = Scorer().score(
        "PIVOT_INSUFFICIENT",
        stage(),
        base(),
        vcp(),
        structure(),
        nested(),
        insufficient_pivot,
        context=context(),
    )
    adverse_setup = Scorer().score(
        "PIVOT_ADVERSE",
        stage(),
        base(),
        vcp(),
        structure(),
        nested(),
        adverse_pivot,
        context=context(),
    )
    insufficient_gate = insufficient_setup.metadata["trade_gate"]
    adverse_gate = adverse_setup.metadata["trade_gate"]
    adverse_risk = RiskManager().evaluate(asset(), adverse_setup)
    adverse_entry = EntryPolicy().decide(asset(), adverse_setup, adverse_risk)
    assert_true(insufficient_gate["status"] == "WATCH", "Insufficient pivot shift should remain watch")
    assert_true(
        "pivot_shift_insufficient" in insufficient_gate["watch_reasons"],
        "Insufficient pivot shift should be reported",
    )
    assert_true(adverse_gate["status"] == "BLOCK", "Adverse pivot shift should block")
    assert_true("adverse_pivot_shift" in adverse_gate["blockers"], "Adverse pivot shift should be a blocker")
    assert_true("pivot_shift_adverse" in adverse_gate["watch_reasons"], "Adverse pivot shift should be reported")
    assert_true(adverse_entry.action == "SKIP", "Adverse pivot shift should skip entry")


def check_mixed_reference_watch_gate() -> None:
    setup = Scorer().score(
        "MIXEDREF",
        stage(),
        base(),
        vcp(),
        structure(),
        nested(),
        pivot(),
        context=mixed_reference_context(),
    )
    gate = setup.metadata["trade_gate"]
    risk = RiskManager().evaluate(asset(), setup)
    entry = EntryPolicy().decide(asset(), setup, risk)
    assert_true(gate["status"] == "WATCH", "Mixed reference confluence should be watched, not blocked")
    assert_true("mixed_reference_confluence" in gate["watch_reasons"], "Gate should explain mixed reference watch")
    assert_true("against_reference_confluence" not in gate["blockers"], "Mixed reference should not hard block")
    assert_true(entry.action == "MONITOR", "Mixed reference watch should monitor")


def check_stacked_obstacle_reference_block() -> None:
    setup = Scorer().score(
        "STACKEDREF",
        stage(),
        base(),
        vcp(),
        structure(),
        nested(),
        pivot(),
        context=stacked_obstacle_context(),
    )
    gate = setup.metadata["trade_gate"]
    risk = RiskManager().evaluate(asset(), setup)
    entry = EntryPolicy().decide(asset(), setup, risk)
    assert_true(gate["status"] == "BLOCK", "Stacked opposing references should remain blocked")
    assert_true("against_reference_confluence" in gate["blockers"], "Gate should block stacked opposing references")
    assert_true(entry.action == "SKIP", "Stacked opposing reference should skip")


def main() -> None:
    check_approved_gate()
    check_watch_gate()
    check_pivot_watch_reason_details()
    check_base_vcp_watch_reason_details()
    check_close_compression_base_needs_vcp_confirmation()
    check_developing_directional_vcp_watch()
    check_short_pivot_awaiting_loss_reason()
    check_pivot_state_precedes_retest_hold()
    check_pivot_shift_progress_reasons()
    check_blocked_gate()
    check_mixed_reference_watch_gate()
    check_stacked_obstacle_reference_block()
    print("Strategy gate smoke complete")
    print("ok=True")
    print("approved_gate=ALLOW")
    print("watch_gate=MONITOR")
    print("blocked_gate=SKIP")
    print("mixed_reference_gate=MONITOR")
    print("stacked_reference_gate=SKIP")
    print("pivot_watch_reasons=granular")
    print("base_vcp_watch_reasons=granular")
    print("close_compression_gate=guarded")
    print("directional_pivot_states=enabled")
    print("developing_directional_vcp=MONITOR")
    print("pivot_shift_progress=granular")


if __name__ == "__main__":
    main()
