from __future__ import annotations

from datetime import datetime

from shadow_v8.models import AssetConfig, Candle, EntryDecision, SetupDecision
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


def asset(symbol: str = "EXITUNIT") -> AssetConfig:
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
        reason="Exit lifecycle smoke entry",
        entry=entry,
        stop=stop,
        setup=SetupDecision(symbol=symbol, direction=direction, setup_class="UNIT", grade="A", final_score=80.0),
    )


def check_hard_stop_exit() -> dict:
    simulator = Simulator()
    simulator.open_position(
        asset("STOPUNIT"),
        entry_decision("STOPUNIT", "LONG", entry=100.0, stop=95.0),
        candle("2026-04-01T00:00:00", 100.0, 101.0, 99.0, 100.0),
    )
    trade = simulator.on_bar(candle("2026-04-02T00:00:00", 100.0, 101.0, 94.0, 94.5))
    assert_true(trade is not None, "Hard stop bar should close the position")
    assert_true(trade["exit_type"] == "hard_stop", "Hard stop should classify as hard_stop")
    assert_true(trade["exit_diagnostics"]["hit_hard_stop"] is True, "Hard stop diagnostics should flag hard stop")
    assert_true(trade["exit_diagnostics"]["closed_at_end"] is False, "Hard stop should not be end-of-replay")
    return trade


def check_end_of_replay_exit() -> dict:
    simulator = Simulator()
    simulator.open_position(
        asset("ENDUNIT"),
        entry_decision("ENDUNIT", "LONG", entry=100.0, stop=95.0),
        candle("2026-05-01T00:00:00", 100.0, 101.0, 99.0, 100.0),
    )
    trade = simulator.close_open_at_end(candle("2026-05-02T00:00:00", 100.0, 106.0, 99.0, 104.0))
    assert_true(trade is not None, "End-of-replay should close the position")
    assert_true(trade["exit_type"] == "end_of_replay", "End close should classify as end_of_replay")
    assert_true(trade["exit_diagnostics"]["closed_at_end"] is True, "End close diagnostics should flag closed at end")
    assert_true(trade["exit_diagnostics"]["partial_candidate"] is True, "End close should detect partial candidate")
    assert_true(trade["exit_diagnostics"]["break_even_candidate"] is True, "End close should detect break-even candidate")
    return trade


def check_trail_candidate_exit() -> dict:
    simulator = Simulator()
    simulator.open_position(
        asset("TRAILUNIT"),
        entry_decision("TRAILUNIT", "SHORT", entry=100.0, stop=105.0),
        candle("2026-06-01T00:00:00", 100.0, 101.0, 99.0, 100.0),
    )
    simulator.on_bar(candle("2026-06-02T00:00:00", 100.0, 101.0, 84.0, 86.0))
    trade = simulator.close_position(candle("2026-06-03T00:00:00", 86.0, 89.0, 85.0, 88.0), "Unit close")
    assert_true(trade["exit_diagnostics"]["trail_candidate"] is True, "Large favorable move should flag trail candidate")
    assert_true(trade["exit_diagnostics"]["max_r"] >= 3.0, "Trail candidate should have at least 3R max excursion")
    return trade


def main() -> None:
    hard_stop = check_hard_stop_exit()
    end_close = check_end_of_replay_exit()
    trail = check_trail_candidate_exit()

    print("Exit lifecycle smoke complete")
    print("ok=True")
    print(f"hard_stop_type={hard_stop['exit_type']}")
    print(f"end_close_type={end_close['exit_type']}")
    print(f"trail_candidate={trail['exit_diagnostics']['trail_candidate']}")
    print(f"trail_max_r={trail['exit_diagnostics']['max_r']}")


if __name__ == "__main__":
    main()
