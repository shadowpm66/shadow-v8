from __future__ import annotations

from shadow_v8.execution.execution_router import ExecutionRouter
from shadow_v8.models import AssetConfig, BrokerConfig, EntryDecision, ExitDecision, SetupDecision


class RecordingExecutor:
    def __init__(self) -> None:
        self.entries: list[str] = []
        self.exits: list[str] = []

    def enter(self, asset: AssetConfig, decision: EntryDecision) -> dict:
        self.entries.append(asset.symbol)
        return {"ok": True, "reason": "recorded entry", "symbol": asset.symbol}

    def apply_exit(self, asset: AssetConfig, decision: ExitDecision) -> dict:
        self.exits.append(asset.symbol)
        return {"ok": True, "reason": "recorded exit", "symbol": asset.symbol}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def asset(symbol: str, broker: str, asset_class: str = "crypto", allow_short: bool = True) -> AssetConfig:
    return AssetConfig(
        symbol=symbol,
        asset_class=asset_class,
        broker=broker,
        allow_long=True,
        allow_short=allow_short,
    )


def entry(symbol: str, direction: str = "LONG") -> EntryDecision:
    return EntryDecision(
        action="ENTER",
        symbol=symbol,
        direction=direction,
        reason="Execution router safety smoke",
        entry=100.0,
        stop=90.0,
        setup=SetupDecision(symbol=symbol, direction=direction, setup_class="ROUTER_SMOKE", grade="A"),
    )


def exit_decision(symbol: str) -> ExitDecision:
    return ExitDecision(action="CLOSE", symbol=symbol, reason="Execution router safety smoke exit")


def main() -> None:
    paper_executor = RecordingExecutor()
    live_executor = RecordingExecutor()

    scan_router = ExecutionRouter({"paper": paper_executor}, mode="scan_only")
    scan_result = scan_router.enter(asset("SCAN", "paper"), entry("SCAN"))
    assert_true(scan_result["safety_block"] is True, "scan_only should block entries")
    assert_true(not paper_executor.entries, "scan_only should not call executor")

    paper_router = ExecutionRouter({"paper": paper_executor, "bybit": live_executor}, mode="paper")
    paper_result = paper_router.enter(asset("PAPER", "paper"), entry("PAPER"))
    assert_true(paper_result["ok"] is True, "paper mode should route paper broker")
    live_in_paper = paper_router.enter(asset("LIVEINPAPER", "bybit"), entry("LIVEINPAPER"))
    assert_true(live_in_paper["safety_block"] is True, "paper mode should block live broker")

    no_live_flag_router = ExecutionRouter(
        {"bybit": live_executor},
        mode="live_guarded",
        broker_configs={"bybit": BrokerConfig(name="bybit", enabled=True, paper=False)},
        live_trading_enabled={"crypto": False},
    )
    no_live_flag = no_live_flag_router.enter(asset("NOLIVE", "bybit"), entry("NOLIVE"))
    assert_true(no_live_flag["safety_block"] is True, "live flag off should block live route")

    live_router = ExecutionRouter(
        {"bybit": live_executor},
        mode="live_guarded",
        broker_configs={"bybit": BrokerConfig(name="bybit", enabled=True, paper=False)},
        live_trading_enabled={"crypto": True},
    )
    live_result = live_router.enter(asset("LIVE", "bybit"), entry("LIVE"))
    assert_true(live_result["ok"] is True, "live guarded should route when every guard passes")
    short_block = live_router.enter(asset("NOSHORT", "bybit", allow_short=False), entry("NOSHORT", "SHORT"))
    assert_true(short_block["safety_block"] is True, "asset short permission should block shorts")
    exit_result = live_router.apply_exit(asset("LIVE", "bybit"), exit_decision("LIVE"))
    assert_true(exit_result["ok"] is True, "live guarded should route exits when every guard passes")

    print("Execution router safety smoke complete")
    print("ok=True")
    print(f"scan_only_blocked={scan_result['safety_block']}")
    print(f"paper_entries={paper_executor.entries}")
    print(f"live_entries={live_executor.entries}")
    print(f"short_block_reason={short_block['reason']}")


if __name__ == "__main__":
    main()
