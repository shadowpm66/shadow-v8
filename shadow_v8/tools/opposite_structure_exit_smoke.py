from __future__ import annotations

from datetime import datetime

from shadow_v8.models import AssetConfig, Candle, EntryDecision, SetupDecision, StructureSignal
from shadow_v8.research.replay import Replay
from shadow_v8.research.simulator import Simulator


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def candle(timestamp: str, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp=datetime.fromisoformat(timestamp),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100_000,
    )


def asset(symbol: str = "OPPUSDT") -> AssetConfig:
    return AssetConfig(
        symbol=symbol,
        asset_class="crypto",
        broker="paper",
        allow_long=True,
        allow_short=True,
        max_risk_pct=0.01,
    )


def entry_decision(symbol: str, direction: str, entry: float, stop: float) -> EntryDecision:
    return EntryDecision(
        action="ENTER",
        symbol=symbol,
        direction=direction,
        reason="Opposite structure smoke entry",
        entry=entry,
        stop=stop,
        setup=SetupDecision(symbol=symbol, direction=direction, setup_class="UNIT", grade="A", final_score=80.0),
    )


def check_long_exits_on_bearish_m() -> dict:
    simulator = Simulator()
    opened = candle("2026-04-01T00:00:00", 100.0, 101.0, 99.0, 100.0)
    simulator.open_position(asset("LONGOPP"), entry_decision("LONGOPP", "LONG", entry=100.0, stop=95.0), opened)
    trade = simulator.apply_structure_exit(
        candle("2026-04-02T00:00:00", 100.0, 101.0, 96.0, 98.0),
        StructureSignal(
            type="M",
            direction="SHORT",
            entry=98.0,
            neckline=99.0,
            quality_score=72.0,
            reasons=["Synthetic bearish M invalidated long"],
            metadata={"neckline_ok": True},
        ),
    )
    assert_true(trade is not None, "LONG trade should close on bearish M")
    assert_true(trade["exit_type"] == "opposite_structure", "Trade should use opposite structure exit type")
    assert_true(
        trade["exit_diagnostics"]["opposite_structure_exit"] is True,
        "Exit diagnostics should flag opposite structure exit",
    )
    assert_true(
        any(event["type"] == "EXIT_SIGNAL" for event in trade["lifecycle_events"]),
        "Lifecycle events should include structure exit signal",
    )
    return trade


def check_short_exits_on_bullish_w() -> dict:
    simulator = Simulator()
    opened = candle("2026-05-01T00:00:00", 100.0, 101.0, 99.0, 100.0)
    simulator.open_position(asset("SHORTOPP"), entry_decision("SHORTOPP", "SHORT", entry=100.0, stop=105.0), opened)
    trade = simulator.apply_structure_exit(
        candle("2026-05-02T00:00:00", 100.0, 104.0, 99.0, 102.0),
        StructureSignal(
            type="W",
            direction="LONG",
            entry=102.0,
            neckline=101.0,
            quality_score=72.0,
            reasons=["Synthetic bullish W invalidated short"],
            metadata={"neckline_ok": True},
        ),
    )
    assert_true(trade is not None, "SHORT trade should close on bullish W")
    assert_true(trade["exit_type"] == "opposite_structure", "Trade should use opposite structure exit type")
    assert_true(
        trade["exit_diagnostics"]["opposite_structure_exit"] is True,
        "Exit diagnostics should flag opposite structure exit",
    )
    return trade


def check_exit_analytics(long_trade: dict, short_trade: dict) -> dict:
    analytics = Replay(asset=asset("ANALYTICS"), candles=[])._build_exit_analytics([long_trade, short_trade])
    assert_true(analytics["opposite_structure_exit_count"] == 2, "Exit analytics should count opposite exits")
    assert_true(analytics["opposite_structure_exit_rate"] == 1.0, "Exit analytics should calculate opposite exit rate")
    assert_true(
        analytics["opposite_structure_by_direction"] == {"LONG": 1, "SHORT": 1},
        "Exit analytics should count directions",
    )
    assert_true(
        analytics["opposite_structure_by_signal_type"] == {"M": 1, "W": 1},
        "Exit analytics should count opposite signal types",
    )
    assert_true(len(analytics["opposite_structure_samples"]) == 2, "Exit analytics should include samples")
    return analytics


def main() -> None:
    long_trade = check_long_exits_on_bearish_m()
    short_trade = check_short_exits_on_bullish_w()
    analytics = check_exit_analytics(long_trade, short_trade)
    print("Opposite structure exit smoke complete")
    print("ok=True")
    print(f"long_exit_type={long_trade['exit_type']}")
    print(f"long_exit_reason={long_trade['exit_reason']}")
    print(f"short_exit_type={short_trade['exit_type']}")
    print(f"short_exit_reason={short_trade['exit_reason']}")
    print(f"opposite_structure_exit_count={analytics['opposite_structure_exit_count']}")
    print(f"opposite_structure_by_signal_type={analytics['opposite_structure_by_signal_type']}")


if __name__ == "__main__":
    main()
