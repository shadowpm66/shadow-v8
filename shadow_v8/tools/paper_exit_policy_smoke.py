from __future__ import annotations

import shutil
from pathlib import Path

from shadow_v8.execution.paper_order_manager import PaperOrderManager
from shadow_v8.models import AssetConfig, EntryDecision, SetupDecision
from shadow_v8.state_store import ClosedTradeStore, PositionStore


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def asset(symbol: str) -> AssetConfig:
    return AssetConfig(
        symbol=symbol,
        asset_class="crypto",
        broker="paper",
        allow_long=True,
        allow_short=True,
        max_risk_pct=0.01,
    )


def entry_decision(symbol: str, direction: str = "LONG") -> EntryDecision:
    return EntryDecision(
        action="ENTER",
        symbol=symbol,
        direction=direction,
        reason="Paper exit policy smoke entry",
        entry=100.0,
        stop=90.0 if direction == "LONG" else 110.0,
        target=None,
        setup=SetupDecision(symbol=symbol, direction=direction, setup_class="PAPER_SMOKE", grade="A", final_score=80.0),
        metadata={"risk_pct": 0.01, "risk_state": "FULL", "risk_reason": "Smoke test"},
    )


def manager(name: str) -> PaperOrderManager:
    root = Path("runtime") / "smoke" / "paper_exit_policy" / name
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return PaperOrderManager(
        account_balance=10_000.0,
        store=PositionStore(root / "positions.json"),
        closed_store=ClosedTradeStore(root / "closed.json"),
    )


def check_break_even_stop() -> dict:
    paper = manager("break_even")
    symbol = "PAPERBE"
    entered = paper.enter(asset(symbol), entry_decision(symbol))
    assert_true(entered["ok"] is True, "Paper break-even smoke should open")
    events = paper.manage_positions({symbol: {"high": 112.5, "low": 99.0, "last": 112.5}})
    assert_true(any(event["reason"] == "Paper partial take profit" for event in events), "Partial should trigger")
    assert_true(any(event["reason"] == "Paper stop to break-even" for event in events), "Break-even should trigger")
    events = paper.manage_positions({symbol: {"high": 101.0, "low": 100.0, "last": 100.0}})
    exit_event = next(event for event in events if event["type"] == "EXIT")
    trade = exit_event["trade"]
    assert_true(trade["exit_type"] == "break_even_stop", "Closed trade should classify break-even stop")
    assert_true(trade["exit_diagnostics"]["break_even_stop"] is True, "Diagnostics should flag break-even stop")
    assert_true(trade["partial_taken"] is True, "Trade should preserve partial state")
    assert_true(len(trade["lifecycle_events"]) >= 3, "Trade should preserve lifecycle events")
    return trade


def check_trailing_stop() -> dict:
    paper = manager("trailing")
    symbol = "PAPERTRAIL"
    entered = paper.enter(asset(symbol), entry_decision(symbol))
    assert_true(entered["ok"] is True, "Paper trailing smoke should open")
    paper.manage_positions({symbol: {"high": 132.0, "low": 99.0, "last": 132.0}})
    events = paper.manage_positions({symbol: {"high": 124.0, "low": 121.0, "last": 121.0}})
    exit_event = next(event for event in events if event["type"] == "EXIT")
    trade = exit_event["trade"]
    assert_true(trade["exit_type"] == "trailing_stop", "Closed trade should classify trailing stop")
    assert_true(trade["exit_diagnostics"]["trailing_stop"] is True, "Diagnostics should flag trailing stop")
    assert_true(trade["break_even_moved"] is True, "Trade should preserve break-even state")
    return trade


def main() -> None:
    break_even_trade = check_break_even_stop()
    trailing_trade = check_trailing_stop()
    print("Paper exit policy smoke complete")
    print("ok=True")
    print(f"break_even_exit_type={break_even_trade['exit_type']}")
    print(f"break_even_r={break_even_trade['r_multiple']}")
    print(f"trailing_exit_type={trailing_trade['exit_type']}")
    print(f"trailing_r={trailing_trade['r_multiple']}")


if __name__ == "__main__":
    main()
