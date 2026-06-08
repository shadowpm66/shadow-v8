from __future__ import annotations

from shadow_v8.execution.execution_router import ExecutionRouter
from shadow_v8.execution.readiness import execution_readiness_report
from shadow_v8.models import AssetConfig, BrokerConfig, EntryDecision, SetupDecision


class RecordingExecutor:
    def __init__(self) -> None:
        self.entries: list[str] = []

    def enter(self, asset: AssetConfig, decision: EntryDecision) -> dict:
        self.entries.append(asset.symbol)
        return {"ok": True, "reason": "recorded live entry", "symbol": asset.symbol}

    def apply_exit(self, asset: AssetConfig, decision: object) -> dict:
        return {"ok": True, "reason": "recorded live exit", "symbol": asset.symbol}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def crypto_asset(symbol: str = "ETHUSDT") -> AssetConfig:
    return AssetConfig(symbol=symbol, asset_class="crypto", broker="bybit", allow_long=True, allow_short=True)


def paper_asset(symbol: str = "PAPER") -> AssetConfig:
    return AssetConfig(symbol=symbol, asset_class="crypto", broker="paper", allow_long=True, allow_short=True)


def entry(symbol: str = "ETHUSDT") -> EntryDecision:
    return EntryDecision(
        action="ENTER",
        symbol=symbol,
        direction="LONG",
        reason="live unlock guard smoke",
        entry=100.0,
        stop=95.0,
        setup=SetupDecision(symbol=symbol, direction="LONG", setup_class="UNLOCK_SMOKE", grade="A"),
    )


def main() -> None:
    broker = BrokerConfig(name="bybit", enabled=True, paper=False)
    executor = RecordingExecutor()

    locked_router = ExecutionRouter(
        {"bybit": executor},
        mode="live_guarded",
        broker_configs={"bybit": broker},
        live_trading_enabled={"crypto": True},
    )
    locked = locked_router.enter(crypto_asset(), entry())
    assert_true(locked["safety_block"] is True, "Live route should block without broker unlock")
    assert_true("Live unlock guard not passed" in locked["reason"], "Live unlock blocker should be explicit")
    assert_true(not executor.entries, "Locked route must not call executor")

    locked_preflight = locked_router.preflight(crypto_asset(), direction="LONG")
    assert_true(locked_preflight["executor_present"] is True, "Locked preflight should still report executor presence")
    assert_true(locked_preflight["safety_block"] is True, "Locked preflight should block")

    unlocked_router = ExecutionRouter(
        {"bybit": executor},
        mode="live_guarded",
        broker_configs={"bybit": broker},
        live_trading_enabled={"crypto": True},
        live_order_unlocked={"bybit": True},
    )
    unlocked = unlocked_router.enter(crypto_asset("BTCUSDT"), entry("BTCUSDT"))
    assert_true(unlocked["ok"] is True, "Unlocked live route should reach executor in controlled smoke")
    assert_true(executor.entries == ["BTCUSDT"], "Only unlocked route should call executor")

    readiness = execution_readiness_report(
        assets=[crypto_asset()],
        broker_configs={"bybit": broker},
        mode="live_guarded",
        live_trading_enabled={"crypto": True},
        live_order_unlocked={},
        executors={"bybit": object()},
        env={"BYBIT_API_KEY": "fake-key", "BYBIT_API_SECRET": "fake-secret"},
    )
    top_blockers = {item["reason"] for item in readiness["top_blockers"]}
    assert_true("live_unlock_missing" in top_blockers, "Readiness should surface missing live unlock")
    assert_true(readiness["broker_reports"][0]["live_unlock_passed"] is False, "Broker report should show unlock false")

    paper_router = ExecutionRouter({"paper": executor}, mode="paper")
    paper = paper_router.preflight(paper_asset(), direction="LONG")
    assert_true(paper["ok"] is True, "Paper mode should not require live unlock")

    print("Live unlock guard smoke complete")
    print("ok=True")
    print(f"locked_reason={locked['reason']}")
    print(f"top_blockers={readiness['top_blockers']}")


if __name__ == "__main__":
    main()
