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


if __name__ == "__main__":
    main()
