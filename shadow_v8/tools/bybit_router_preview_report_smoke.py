from __future__ import annotations

from shadow_v8.tools.bybit_order_intent_smoke import sample_instrument
from shadow_v8.tools.bybit_router_preview_report import build_bybit_router_preview_report, compact_lines


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    fake_env = {"BYBIT_API_KEY": "fake-key-value", "BYBIT_API_SECRET": "fake-secret-value"}
    report = build_bybit_router_preview_report(
        symbol="ETHUSDT",
        direction="LONG",
        entry=2000.123,
        stop=1960.0,
        risk_pct=0.01,
        account_balance=10_000.0,
        instrument_payload=sample_instrument(),
        env=fake_env,
    )
    lines = compact_lines(report)
    text = str(report)
    compact = "\n".join(lines)

    assert_true(report["ok"] is False, "Router preview report must stay validate-only blocked")
    assert_true(report["router_preflight"]["ok"] is True, "Live-guard preflight should pass before adapter validation")
    assert_true(report["payload_ok"] is True, "Valid sample should be payload-ready")
    assert_true(report["safety_block"] is True, "Bybit preview must remain safety blocked")
    assert_true(report["live_orders_enabled"] is False, "Bybit preview must not enable live orders")
    assert_true(report["payload"]["qty"] == "2.49", "Router preview should surface rounded payload qty")
    assert_true("live_orders_disabled_validate_only" in report["blockers"], "Validate-only blocker should remain")
    assert_true("Payload ready: True" in compact, "Compact report should include payload readiness")
    assert_true("fake-key-value" not in text, "Router preview must not echo API key")
    assert_true("fake-secret-value" not in text, "Router preview must not echo API secret")

    missing = build_bybit_router_preview_report(
        symbol="ETHUSDT",
        direction="LONG",
        entry=2000.0,
        stop=1960.0,
        risk_pct=0.01,
        env=fake_env,
    )
    assert_true(missing["payload_ok"] is False, "Missing instrument payload should not be payload-ready")
    assert_true("instrument_payload_missing" in missing["blockers"], "Missing instrument payload should be surfaced")
    assert_true(missing["safety_block"] is True, "Missing payload path should remain safety blocked")

    print("Bybit router preview report smoke complete")
    print("ok=True")
    print(f"payload={report['payload']}")
    print(f"blockers={report['blockers']}")


if __name__ == "__main__":
    main()
