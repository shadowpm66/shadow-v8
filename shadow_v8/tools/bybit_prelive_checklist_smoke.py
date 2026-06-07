from __future__ import annotations

import json

from shadow_v8.tools import bybit_prelive_checklist as checklist
from shadow_v8.tools.bybit_public_dry_run_batch import offline_sample_instrument


FAKE_ENV = {
    "BYBIT_API_KEY": "fake-key-value",
    "BYBIT_API_SECRET": "fake-secret-value",
}


class FakeMarketData:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url

    def get_linear_instrument(self, symbol: str) -> dict:
        return offline_sample_instrument(symbol)


class FailingMarketData:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url

    def get_linear_instrument(self, symbol: str) -> dict:
        raise RuntimeError(f"public fetch unavailable for {symbol}")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    original_market_data = checklist.BybitMarketData
    try:
        checklist.BybitMarketData = FakeMarketData  # type: ignore[assignment]
        ready = checklist.build_bybit_prelive_checklist(
            symbols="ETHUSDT,BTCUSDT",
            direction="LONG",
            fetch_public_instrument=False,
            env=FAKE_ENV,
        )
        ready_text = json.dumps(ready, sort_keys=True)
        assert_true(ready["status"] == "VALIDATE_ONLY_READY", "Fake credential path should be validate-only ready")
        assert_true(ready["payload_validate_ready"] is True, "Payload validation should be ready")
        assert_true(ready["credential_ready"] is True, "Signed preview should be credential-ready with fake env")
        assert_true(ready["live_orders_enabled"] is False, "Checklist must not enable live orders")
        assert_true("live_orders_disabled_validate_only" in ready["blocker_counts"], "Validate-only safety blocker should remain")
        assert_true("adapter_validate_only" in ready["blocker_counts"], "Adapter validate-only blocker should remain")
        assert_true("fake-key-value" not in ready_text, "Checklist must not echo raw API keys")
        assert_true("fake-secret-value" not in ready_text, "Checklist must not echo raw API secrets")

        compact = "\n".join(checklist.compact_lines(ready))
        assert_true("Shadow v8 Bybit pre-live checklist" in compact, "Compact report should include title")
        assert_true("Status: VALIDATE_ONLY_READY" in compact, "Compact report should show status")
        assert_true("Live orders enabled: False" in compact, "Compact report should show live-order safety")

        missing_credentials = checklist.build_bybit_prelive_checklist(
            symbols="ETHUSDT,BTCUSDT",
            direction="LONG",
            fetch_public_instrument=False,
            env={},
        )
        assert_true(
            missing_credentials["status"] == "CREDENTIALS_PENDING",
            "Missing credentials should be reported separately from payload blockers",
        )
        assert_true("credentials_missing" in missing_credentials["blocker_counts"], "Credential blocker should be counted")
        assert_true(
            "signed:credentials_missing" in missing_credentials["blocker_counts"],
            "Signed preview credential blocker should be counted",
        )

        checklist.BybitMarketData = FailingMarketData  # type: ignore[assignment]
        public_failure = checklist.build_bybit_prelive_checklist(
            symbols="ETHUSDT,BTCUSDT",
            direction="LONG",
            env=FAKE_ENV,
        )
        assert_true(public_failure["status"] == "BLOCKED", "Public fetch failures should block the checklist")
        assert_true(
            any(str(item).startswith("public_instrument_fetch_failed") for item in public_failure["public_blockers"]),
            "Public fetch blocker should be surfaced",
        )
    finally:
        checklist.BybitMarketData = original_market_data  # type: ignore[assignment]

    print("Bybit pre-live checklist smoke complete")
    print("ok=True")
    print(f"status={ready['status']}")
    print(f"blockers={ready['blocker_counts']}")


if __name__ == "__main__":
    main()
