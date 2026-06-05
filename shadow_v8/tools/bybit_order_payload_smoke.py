from __future__ import annotations

import json

from shadow_v8.execution.bybit_order_manager import BybitOrderManager
from shadow_v8.models import AssetConfig, EntryDecision
from shadow_v8.tools.bybit_order_payload_preview import build_bybit_order_payload_preview, compact_lines
from shadow_v8.tools.bybit_order_intent_smoke import sample_instrument


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def crypto_asset() -> AssetConfig:
    return AssetConfig(symbol="ETHUSDT", asset_class="crypto", broker="bybit", allow_long=True, allow_short=True)


def main() -> None:
    manager = BybitOrderManager(env={"BYBIT_API_KEY": "fake-key-value", "BYBIT_API_SECRET": "fake-secret-value"})
    decision = EntryDecision(
        action="ENTER",
        symbol="ETHUSDT",
        direction="LONG",
        reason="smoke",
        entry=2000.123,
        stop=1960.0,
        metadata={"risk_pct": 0.01},
    )
    preview = manager.build_entry_order_payload_preview(
        crypto_asset(),
        decision,
        sample_instrument(),
        account_balance=10_000.0,
    )
    payload = preview["payload"]
    body = json.loads(preview["body"])
    signed = preview["signed_preview"]

    assert_true(preview["ok"] is False, "Order payload preview must remain validate-only blocked")
    assert_true(preview["payload_ok"] is True, "Valid intent should produce a payload-ready preview")
    assert_true(preview["live_orders_enabled"] is False, "Payload preview must not enable live orders")
    assert_true("live_orders_disabled_validate_only" in preview["blockers"], "Validate-only blocker should remain")
    assert_true(payload["category"] == "linear", "Bybit linear category should be set")
    assert_true(payload["symbol"] == "ETHUSDT", "Payload symbol should be upper-case")
    assert_true(payload["side"] == "Buy", "Long entries should map to Buy")
    assert_true(payload["orderType"] == "Market", "Entry preview should build a market payload")
    assert_true(payload["qty"] == "2.49", "Rounded qty should be serialized as Bybit string")
    assert_true(payload["stopLoss"] == "1960", "Stop loss should be serialized as Bybit string")
    assert_true(body == payload, "Serialized body should match payload")
    assert_true(signed["ok"] is True, "Signed POST preview should pass shape validation")
    assert_true(signed["method"] == "POST", "Signed preview should use POST")
    assert_true(signed["path"] == "/v5/order/create", "Signed preview should target create-order path")
    assert_true(signed["signature_length"] == 64, "Signed preview should produce HMAC length")
    assert_true("fake-key-value" not in str(preview), "Payload preview must not echo API key")
    assert_true("fake-secret-value" not in str(preview), "Payload preview must not echo API secret")

    invalid = manager.build_entry_order_payload_preview(
        crypto_asset(),
        EntryDecision(action="ENTER", symbol="ETHUSDT", direction="LONG", reason="smoke", entry=2000.0, stop=2010.0),
        sample_instrument(),
    )
    assert_true(invalid["payload_ok"] is False, "Invalid intent should not be payload-ready")
    assert_true("intent:intent_not_ready" not in invalid["blockers"], "Blockers should not be double-prefixed")
    assert_true("intent:invalid_long_stop_side" in invalid["blockers"], "Intent blockers should be surfaced")
    assert_true("intent_not_ready" in invalid["blockers"], "Payload preview should report intent not ready")

    report = build_bybit_order_payload_preview(
        symbol="ETHUSDT",
        direction="LONG",
        entry=2000.123,
        stop=1960.0,
        risk_pct=0.01,
        instrument_payload=sample_instrument(),
    )
    lines = compact_lines(report)
    assert_true(report["payload"]["qty"] == "2.49", "Report tool should build the same rounded payload")
    assert_true(any("Payload ready: True" in line for line in lines), "Compact report should show payload readiness")
    assert_true("fake-key-value" not in str(report), "Report tool must not echo API key")

    print("Bybit order payload smoke complete")
    print("ok=True")
    print(f"payload={payload}")
    print(f"blockers={preview['blockers']}")


if __name__ == "__main__":
    main()
