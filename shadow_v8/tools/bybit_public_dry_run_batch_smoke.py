from __future__ import annotations

from shadow_v8.tools import bybit_end_to_end_dry_run as dry_run_module
from shadow_v8.tools.bybit_order_intent_smoke import sample_instrument
from shadow_v8.tools.bybit_public_dry_run_batch import build_bybit_public_dry_run_batch, compact_lines


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class PublicInstrumentProvider:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url

    def get_linear_instrument(self, symbol: str) -> dict:
        instrument = sample_instrument()
        instrument["symbol"] = symbol
        return instrument


class MissingSolInstrumentProvider:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url

    def get_linear_instrument(self, symbol: str) -> dict | None:
        if symbol == "SOLUSDT":
            return None
        instrument = sample_instrument()
        instrument["symbol"] = symbol
        return instrument


def main() -> None:
    fake_env = {"BYBIT_API_KEY": "fake-key-value", "BYBIT_API_SECRET": "fake-secret-value"}
    original_market_data = dry_run_module.BybitMarketData
    try:
        dry_run_module.BybitMarketData = PublicInstrumentProvider
        report = build_bybit_public_dry_run_batch(symbols="ETHUSDT,BTCUSDT,SOLUSDT", env=fake_env)
        compact = "\n".join(compact_lines(report))
        text = str(report)

        assert_true(report["ok"] is True, "Batch should be validate-only ready when all public probes pass")
        assert_true(report["ready_for_validate_only"] is True, "Batch should mark validate-only readiness")
        assert_true(report["live_orders_enabled"] is False, "Batch must never enable live orders")
        assert_true(report["summary"]["payload_ready_count"] == 3, "All three symbols should be payload-ready")
        assert_true(report["summary"]["public_fetch_failed_symbols"] == [], "Public fetch should not fail in success path")
        assert_true(
            report["summary"]["blocker_counts"].get("live_orders_disabled_validate_only") == 3,
            "Every symbol should keep validate-only safety blocker",
        )
        assert_true("Ready for validate-only: True" in compact, "Compact output should show readiness")
        assert_true("Payload ready: 3/3" in compact, "Compact output should summarize payload readiness")
        assert_true("fake-key-value" not in text, "Batch report must not echo API key")
        assert_true("fake-secret-value" not in text, "Batch report must not echo API secret")
    finally:
        dry_run_module.BybitMarketData = original_market_data

    offline_report = build_bybit_public_dry_run_batch(
        symbols=["ETHUSDT", "BTCUSDT"],
        fetch_public_instrument=False,
        env=fake_env,
    )
    assert_true(offline_report["ok"] is True, "Offline sample batch should remain validate-only ready")
    assert_true(offline_report["fetch_public_instrument"] is False, "Offline sample batch should disclose sample mode")
    assert_true(offline_report["summary"]["payload_ready_count"] == 2, "Offline batch should build two payload previews")

    try:
        dry_run_module.BybitMarketData = MissingSolInstrumentProvider
        missing_report = build_bybit_public_dry_run_batch(symbols="ETHUSDT,SOLUSDT", env=fake_env)
        missing_compact = "\n".join(compact_lines(missing_report))
        assert_true(missing_report["ok"] is False, "Missing public instrument should block validate-only readiness")
        assert_true(["SOLUSDT"] == missing_report["summary"]["public_fetch_failed_symbols"], "SOL missing should be surfaced")
        assert_true(
            missing_report["summary"]["blocker_counts"].get("public_instrument_missing") == 1,
            "Missing public instrument blocker should be counted",
        )
        assert_true("Public fetch failures: SOLUSDT" in missing_compact, "Compact output should show failed symbol")
    finally:
        dry_run_module.BybitMarketData = original_market_data

    print("Bybit public dry-run batch smoke complete")
    print("ok=True")
    print(f"payload_ready={report['summary']['payload_ready_count']}/{report['summary']['symbols_checked']}")
    print(f"blockers={report['summary']['blocker_counts']}")


if __name__ == "__main__":
    main()
