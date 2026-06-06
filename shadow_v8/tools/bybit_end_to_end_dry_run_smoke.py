from __future__ import annotations

from shadow_v8.tools.bybit_end_to_end_dry_run import build_bybit_end_to_end_dry_run, compact_lines


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    fake_env = {"BYBIT_API_KEY": "fake-key-value", "BYBIT_API_SECRET": "fake-secret-value"}
    report = build_bybit_end_to_end_dry_run(env=fake_env)
    compact = "\n".join(compact_lines(report))
    text = str(report)

    assert_true(report["ok"] is False, "Dry run must never claim live-order success")
    assert_true(report["mode"] == "dry_run_validate_only", "Dry run should use validate-only mode")
    assert_true(report["strategy_gate"]["status"] == "ALLOW", "Dry run should include a strategy-approved sample")
    assert_true(report["strategy_entry"]["action"] == "ENTER", "Dry run should carry an entry decision")
    assert_true(
        report["execution_readiness"] == "PAYLOAD_READY_VALIDATE_ONLY_BLOCKED",
        "Dry run should distinguish ready payload from live safety block",
    )
    assert_true(report["router_preview"]["router_preflight"]["ok"] is True, "Router preflight should pass live guard")
    assert_true(report["router_preview"]["payload_ok"] is True, "Router should build a valid payload preview")
    assert_true(report["router_preview"]["payload"]["side"] == "Buy", "Default long dry run should preview Buy side")
    assert_true(report["dashboard_execution_preview"]["payload_ok"] is True, "Dashboard preview should show payload ready")
    assert_true(
        report["dashboard_execution_preview"]["payload"]["qty"] == report["router_preview"]["payload"]["qty"],
        "Dashboard preview should mirror router payload quantity",
    )
    assert_true(report["live_orders_enabled"] is False, "Live orders must remain disabled")
    assert_true(report["safety_block"] is True, "Dry run should remain safety-blocked")
    assert_true("live_orders_disabled_validate_only" in report["blockers"], "Validate-only blocker should remain")
    assert_true("Shadow v8 Bybit end-to-end dry run" in compact, "Compact report should include title")
    assert_true("Execution readiness: PAYLOAD_READY_VALIDATE_ONLY_BLOCKED" in compact, "Compact report should show readiness")
    assert_true("fake-key-value" not in text, "Dry run must not echo API key")
    assert_true("fake-secret-value" not in text, "Dry run must not echo API secret")

    short_report = build_bybit_end_to_end_dry_run(
        symbol="ETHUSDT",
        direction="SHORT",
        entry=2000.0,
        stop=2040.0,
        risk_pct=0.01,
        env=fake_env,
    )
    assert_true(short_report["router_preview"]["payload"]["side"] == "Sell", "Short dry run should preview Sell side")
    assert_true(short_report["strategy_gate"]["status"] == "ALLOW", "Short dry run should include approved sample gate")

    print("Bybit end-to-end dry run smoke complete")
    print("ok=True")
    print(f"readiness={report['execution_readiness']}")
    print(f"payload={report['router_preview']['payload']}")
    print(f"blockers={report['blockers']}")


if __name__ == "__main__":
    main()
