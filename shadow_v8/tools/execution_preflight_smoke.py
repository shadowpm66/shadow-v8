from __future__ import annotations

from collections import Counter

from shadow_v8.execution.execution_router import ExecutionRouter
from shadow_v8.models import AssetConfig, BrokerConfig


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


def main() -> None:
    router = ExecutionRouter(
        {"paper": object(), "bybit": object()},
        mode="live_guarded",
        broker_configs={
            "bybit": BrokerConfig(name="bybit", enabled=True, paper=False),
            "ibkr": BrokerConfig(name="ibkr", enabled=False, paper=True),
        },
        live_trading_enabled={"crypto": False, "stock": False},
    )
    checks = [
        router.preflight(asset("ETHUSDT", "bybit"), direction="LONG"),
        router.preflight(asset("AAPL", "ibkr", "stock"), direction="LONG"),
        router.preflight(asset("PAPER", "paper"), direction="LONG"),
        router.preflight(asset("NOSHORT", "bybit", allow_short=False), direction="SHORT"),
        router.preflight(asset("UNKNOWN", "missing"), direction="LONG"),
    ]

    assert_true(all(check["safety_block"] for check in checks), "Default live preflight should block unsafe routes")
    reasons = Counter(check["reason"] for check in checks)
    assert_true(reasons["Live trading disabled for crypto"] == 1, "Crypto live flag should be reported")
    assert_true(reasons["Broker ibkr disabled"] == 1, "Disabled broker should be reported")
    assert_true(reasons["Live guarded mode does not route paper broker orders"] == 1, "Paper live route should block")
    assert_true(reasons["Short entries disabled for asset"] == 1, "Short permission should be reported")
    assert_true(reasons["No broker config for missing"] == 1, "Missing broker config should be reported")

    pass_router = ExecutionRouter(
        {"bybit": object()},
        mode="live_guarded",
        broker_configs={"bybit": BrokerConfig(name="bybit", enabled=True, paper=False)},
        live_trading_enabled={"crypto": True},
    )
    passed = pass_router.preflight(asset("LIVEOK", "bybit"), direction="LONG")
    assert_true(passed["ok"] is True, "Preflight should pass when every live guard passes")
    assert_true(passed["executor_present"] is True, "Passing preflight should report executor presence")

    print("Execution preflight smoke complete")
    print("ok=True")
    print(f"blocked_count={sum(1 for check in checks if check['safety_block'])}")
    print(f"passed_reason={passed['reason']}")
    print(f"top_block_reasons={dict(reasons)}")


if __name__ == "__main__":
    main()
