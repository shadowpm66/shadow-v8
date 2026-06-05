from __future__ import annotations

from shadow_v8.execution.bybit_order_manager import BybitOrderManager
from shadow_v8.execution.readiness import execution_readiness_report
from shadow_v8.models import AssetConfig, BrokerConfig, EntryDecision, ExitDecision


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def crypto_asset() -> AssetConfig:
    return AssetConfig(symbol="ETHUSDT", asset_class="crypto", broker="bybit", allow_long=True, allow_short=True)


def sample_instrument(symbol: str = "ETHUSDT", status: str = "Trading", quote: str = "USDT") -> dict:
    return {
        "symbol": symbol,
        "status": status,
        "baseCoin": "ETH",
        "quoteCoin": quote,
        "priceFilter": {"tickSize": "0.01"},
        "lotSizeFilter": {
            "minOrderQty": "0.01",
            "maxOrderQty": "100",
            "qtyStep": "0.01",
            "minNotionalValue": "5",
        },
        "leverageFilter": {"maxLeverage": "50"},
    }


def blocker_names(report: dict) -> set[str]:
    return {item["reason"] for item in report.get("top_blockers", [])}


def main() -> None:
    env_without_creds = {"BYBIT_API_KEY": "", "BYBIT_API_SECRET": ""}
    env_with_creds = {"BYBIT_API_KEY": "fake-key-value", "BYBIT_API_SECRET": "fake-secret-value"}
    manager = BybitOrderManager(env=env_without_creds)

    config_check = manager.validate_config()
    assert_true(config_check["ok"] is False, "Bybit validate-only config should not enable live orders")
    assert_true("credentials_missing" in config_check["blockers"], "Missing credentials should be reported")
    assert_true("live_orders_disabled_validate_only" in config_check["blockers"], "Validate-only blocker should remain")

    instrument_check = manager.validate_instrument(crypto_asset(), sample_instrument())
    assert_true(instrument_check["ok"] is True, "Valid fake ETHUSDT instrument should pass validation")
    assert_true(instrument_check["rules"]["tick_size"] == 0.01, "Tick size should be parsed")
    assert_true(instrument_check["rules"]["qty_step"] == 0.01, "Qty step should be parsed")
    assert_true(instrument_check["rules"]["min_notional_value"] == 5.0, "Min notional should be parsed")

    blocked_instrument = manager.validate_instrument(crypto_asset(), sample_instrument(status="PreLaunch", quote="USDC"))
    assert_true(blocked_instrument["ok"] is False, "Non-trading wrong-quote instrument should be blocked")
    assert_true("instrument_not_trading" in blocked_instrument["blockers"], "Trading status blocker should be reported")
    assert_true("quote_not_usdt" in blocked_instrument["blockers"], "Quote blocker should be reported")

    entry_result = manager.enter(
        crypto_asset(),
        EntryDecision(action="ENTER", symbol="ETHUSDT", direction="LONG", reason="smoke"),
    )
    exit_result = manager.apply_exit(
        crypto_asset(),
        ExitDecision(action="EXIT", symbol="ETHUSDT", reason="smoke"),
    )
    assert_true(entry_result["ok"] is False, "Validate-only adapter must block entries")
    assert_true(exit_result["ok"] is False, "Validate-only adapter must block exits")
    assert_true("validate-only" in entry_result["reason"], "Entry block should explain validate-only mode")

    readiness = execution_readiness_report(
        assets=[crypto_asset()],
        broker_configs={
            "bybit": BrokerConfig(name="bybit", enabled=True, paper=False, base_url="https://api.bybit.com"),
            "paper": BrokerConfig(name="paper", enabled=True, paper=True),
        },
        mode="live_guarded",
        live_trading_enabled={"crypto": True},
        executors={"bybit": manager},
        env=env_with_creds,
    )
    readiness_text = str(readiness)
    assert_true(readiness["ready"] is False, "Live readiness must stay blocked while Bybit is validate-only")
    assert_true("adapter_validate_only" in blocker_names(readiness), "Validate-only readiness blocker should be reported")
    assert_true("fake-key-value" not in readiness_text, "Readiness must not echo fake API key")
    assert_true("fake-secret-value" not in readiness_text, "Readiness must not echo fake API secret")

    print("Bybit validate-only smoke complete")
    print("ok=True")
    print(f"instrument_rules={instrument_check['rules']}")
    print(f"readiness_blockers={readiness['top_blockers']}")


if __name__ == "__main__":
    main()
