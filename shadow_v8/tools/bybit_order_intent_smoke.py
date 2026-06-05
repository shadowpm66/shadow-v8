from __future__ import annotations

from shadow_v8.execution.bybit_order_manager import BybitOrderManager
from shadow_v8.models import AssetConfig, EntryDecision


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def crypto_asset() -> AssetConfig:
    return AssetConfig(symbol="ETHUSDT", asset_class="crypto", broker="bybit", allow_long=True, allow_short=True)


def sample_instrument(
    *,
    qty_step: str = "0.01",
    min_order_qty: str = "0.01",
    min_notional: str = "5",
    tick_size: str = "0.01",
) -> dict:
    return {
        "symbol": "ETHUSDT",
        "status": "Trading",
        "baseCoin": "ETH",
        "quoteCoin": "USDT",
        "priceFilter": {"tickSize": tick_size},
        "lotSizeFilter": {
            "minOrderQty": min_order_qty,
            "maxOrderQty": "100",
            "qtyStep": qty_step,
            "minNotionalValue": min_notional,
        },
        "leverageFilter": {"maxLeverage": "50"},
    }


def main() -> None:
    manager = BybitOrderManager(env={"BYBIT_API_KEY": "fake-key-value", "BYBIT_API_SECRET": "fake-secret-value"})
    long_decision = EntryDecision(
        action="ENTER",
        symbol="ETHUSDT",
        direction="LONG",
        reason="smoke",
        entry=2000.123,
        stop=1960.0,
        metadata={"risk_pct": 0.01},
    )
    long_intent = manager.build_entry_intent_preview(
        crypto_asset(),
        long_decision,
        sample_instrument(),
        account_balance=10_000.0,
    )
    assert_true(long_intent["ok"] is True, "Valid long intent should pass preview validation")
    assert_true(long_intent["side"] == "Buy", "Long intent should map to Bybit Buy")
    assert_true(long_intent["qty"] == 2.49, "Qty should be rounded down to qty step")
    assert_true(long_intent["entry"] == 2000.12, "Entry should be rounded down to tick size")
    assert_true(long_intent["live_orders_enabled"] is False, "Intent preview must not enable live orders")
    assert_true("fake-key-value" not in str(long_intent), "Intent preview must not echo API key")

    short_decision = EntryDecision(
        action="ENTER",
        symbol="ETHUSDT",
        direction="SHORT",
        reason="smoke",
        entry=2000.0,
        stop=2030.0,
        metadata={"qty": 0.034},
    )
    short_intent = manager.build_entry_intent_preview(crypto_asset(), short_decision, sample_instrument())
    assert_true(short_intent["ok"] is True, "Valid short intent should pass preview validation")
    assert_true(short_intent["side"] == "Sell", "Short intent should map to Bybit Sell")
    assert_true(short_intent["qty"] == 0.03, "Provided qty should be rounded down to qty step")
    assert_true(short_intent["sizing_model"] == "provided_qty", "Provided qty sizing model should be reported")

    invalid_stop = manager.build_entry_intent_preview(
        crypto_asset(),
        EntryDecision(action="ENTER", symbol="ETHUSDT", direction="LONG", reason="smoke", entry=2000.0, stop=2010.0),
        sample_instrument(),
    )
    assert_true(invalid_stop["ok"] is False, "Invalid long stop side should block intent")
    assert_true("invalid_long_stop_side" in invalid_stop["blockers"], "Invalid long stop blocker should be reported")

    tiny_order = manager.build_entry_intent_preview(
        crypto_asset(),
        EntryDecision(
            action="ENTER",
            symbol="ETHUSDT",
            direction="LONG",
            reason="smoke",
            entry=2000.0,
            stop=1999.0,
            metadata={"qty": 0.001},
        ),
        sample_instrument(min_order_qty="0.01", min_notional="50"),
    )
    assert_true(tiny_order["ok"] is False, "Tiny rounded order should be blocked")
    assert_true("qty_zero_after_rounding" in tiny_order["blockers"], "Zero-after-rounding blocker should be reported")
    assert_true("qty_below_min_order_qty" in tiny_order["blockers"], "Min qty blocker should be reported")
    assert_true("notional_below_min" in tiny_order["blockers"], "Min notional blocker should be reported")

    print("Bybit order intent smoke complete")
    print("ok=True")
    print(f"long_intent={long_intent}")
    print(f"tiny_blockers={tiny_order['blockers']}")


if __name__ == "__main__":
    main()
