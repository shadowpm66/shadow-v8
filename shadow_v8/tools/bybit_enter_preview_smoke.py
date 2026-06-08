from __future__ import annotations

from shadow_v8.execution.bybit_order_manager import BybitOrderManager
from shadow_v8.execution.execution_router import ExecutionRouter
from shadow_v8.models import AssetConfig, BrokerConfig, EntryDecision
from shadow_v8.tools.bybit_order_intent_smoke import sample_instrument


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def crypto_asset(symbol: str = "ETHUSDT") -> AssetConfig:
    return AssetConfig(symbol=symbol, asset_class="crypto", broker="bybit", allow_long=True, allow_short=True)


def entry_with_rules() -> EntryDecision:
    return EntryDecision(
        action="ENTER",
        symbol="ETHUSDT",
        direction="LONG",
        reason="smoke",
        entry=2000.123,
        stop=1960.0,
        metadata={
            "risk_pct": 0.01,
            "account_balance": 10_000.0,
            "instrument_payload": sample_instrument(),
        },
    )


def main() -> None:
    manager = BybitOrderManager(env={"BYBIT_API_KEY": "fake-key-value", "BYBIT_API_SECRET": "fake-secret-value"})

    missing_rules = manager.enter(
        crypto_asset(),
        EntryDecision(action="ENTER", symbol="ETHUSDT", direction="LONG", reason="missing rules", entry=2000, stop=1960),
    )
    assert_true(missing_rules["ok"] is False, "Bybit enter must stay blocked without instrument payload")
    assert_true(missing_rules["safety_block"] is True, "Bybit enter should report safety block")
    assert_true("instrument_payload_missing" in missing_rules["blockers"], "Missing instrument payload should be reported")
    assert_true(missing_rules["live_orders_enabled"] is False, "Bybit enter must not enable live orders")

    preview = manager.enter(crypto_asset(), entry_with_rules())
    assert_true(preview["ok"] is False, "Bybit enter preview must remain validate-only blocked")
    assert_true(preview["payload_ok"] is True, "Bybit enter should surface payload readiness")
    assert_true(preview["safety_block"] is True, "Bybit enter preview should report safety block")
    assert_true(preview["payload"]["qty"] == "2.49", "Bybit enter should include rounded payload qty")
    assert_true(preview["payload"]["side"] == "Buy", "Bybit enter should map long to Buy")
    assert_true("live_orders_disabled_validate_only" in preview["blockers"], "Validate-only blocker should remain")
    assert_true("fake-key-value" not in str(preview), "Bybit enter preview must not echo API key")
    assert_true("fake-secret-value" not in str(preview), "Bybit enter preview must not echo API secret")

    router = ExecutionRouter(
        {"bybit": manager},
        mode="live_guarded",
        broker_configs={"bybit": BrokerConfig(name="bybit", enabled=True, paper=False, base_url="https://api.bybit.com")},
        live_trading_enabled={"crypto": True},
        live_order_unlocked={"bybit": True},
    )
    routed = router.enter(crypto_asset(), entry_with_rules())
    assert_true(routed["ok"] is False, "Router should surface validate-only Bybit enter block")
    assert_true(routed["payload_ok"] is True, "Router should keep Bybit payload preview")
    assert_true(routed["safety_block"] is True, "Routered Bybit preview should remain safety-blocked")

    print("Bybit enter preview smoke complete")
    print("ok=True")
    print(f"payload={preview['payload']}")
    print(f"blockers={preview['blockers']}")


if __name__ == "__main__":
    main()
