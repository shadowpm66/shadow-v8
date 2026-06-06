from __future__ import annotations

from shadow_v8.tools import bybit_end_to_end_dry_run as dry_run_module
from shadow_v8.tools.bybit_end_to_end_dry_run import build_bybit_end_to_end_dry_run, compact_lines
from shadow_v8.tools.bybit_order_intent_smoke import sample_instrument


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
    assert_true(report["instrument_source"] == "sample", "Default dry run should use offline sample instrument")
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

    original_market_data = dry_run_module.BybitMarketData

    class PublicInstrumentProvider:
        def __init__(self, base_url: str | None = None) -> None:
            self.base_url = base_url

        def get_linear_instrument(self, symbol: str) -> dict:
            instrument = sample_instrument()
            instrument["symbol"] = symbol
            return instrument

    try:
        dry_run_module.BybitMarketData = PublicInstrumentProvider
        public_report = build_bybit_end_to_end_dry_run(
            symbol="BTCUSDT",
            entry=65000.0,
            stop=63700.0,
            fetch_public_instrument=True,
            env=fake_env,
        )
        public_compact = "\n".join(compact_lines(public_report))
        assert_true(public_report["instrument_source"] == "public", "Public probe should mark public instrument source")
        assert_true(public_report["public_fetch_error"] is None, "Public probe should not report fetch error on success")
        assert_true(public_report["router_preview"]["payload_ok"] is True, "Public probe should build payload preview")
        assert_true("Instrument source: public" in public_compact, "Compact report should show public instrument source")
    finally:
        dry_run_module.BybitMarketData = original_market_data

    class FailingInstrumentProvider:
        def __init__(self, base_url: str | None = None) -> None:
            self.base_url = base_url

        def get_linear_instrument(self, symbol: str) -> dict:
            raise RuntimeError("network disabled in smoke")

    try:
        dry_run_module.BybitMarketData = FailingInstrumentProvider
        failed_public_report = build_bybit_end_to_end_dry_run(
            symbol="BTCUSDT",
            entry=65000.0,
            stop=63700.0,
            fetch_public_instrument=True,
            env=fake_env,
        )
        failed_compact = "\n".join(compact_lines(failed_public_report))
        assert_true(
            "public_instrument_fetch_failed" in failed_public_report["blockers"],
            "Public fetch failure should be explicit",
        )
        assert_true("network disabled in smoke" in failed_public_report["public_fetch_error"], "Fetch error should be surfaced")
        assert_true("Public fetch error: RuntimeError" in failed_compact, "Compact report should summarize fetch error")
    finally:
        dry_run_module.BybitMarketData = original_market_data

    print("Bybit end-to-end dry run smoke complete")
    print("ok=True")
    print(f"readiness={report['execution_readiness']}")
    print(f"payload={report['router_preview']['payload']}")
    print(f"blockers={report['blockers']}")


if __name__ == "__main__":
    main()
