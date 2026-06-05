from __future__ import annotations

from shadow_v8.execution.readiness import execution_readiness_report
from shadow_v8.models import AssetConfig, BrokerConfig


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def crypto_asset() -> AssetConfig:
    return AssetConfig(symbol="ETHUSDT", asset_class="crypto", broker="bybit", allow_long=True, allow_short=True)


def blocker_names(report: dict) -> set[str]:
    return {item["reason"] for item in report.get("top_blockers", [])}


def main() -> None:
    brokers = {
        "bybit": BrokerConfig(name="bybit", enabled=True, paper=False, base_url="https://api.bybit.com"),
        "paper": BrokerConfig(name="paper", enabled=True, paper=True),
    }
    env_with_creds = {"BYBIT_API_KEY": "fake-key-value", "BYBIT_API_SECRET": "fake-secret-value"}
    env_without_creds = {"BYBIT_API_KEY": "", "BYBIT_API_SECRET": ""}

    scan_report = execution_readiness_report(
        assets=[crypto_asset()],
        broker_configs=brokers,
        mode="scan_only",
        live_trading_enabled={"crypto": False},
        executors={},
        env=env_without_creds,
    )
    assert_true(scan_report["ready"] is False, "Scan-only should not be execution ready")
    assert_true("execution_mode_scan_only" in blocker_names(scan_report), "Scan-only blocker should be reported")

    paper_report = execution_readiness_report(
        assets=[AssetConfig(symbol="PAPERUSDT", asset_class="crypto", broker="paper")],
        broker_configs=brokers,
        mode="paper",
        live_trading_enabled={"crypto": False},
        executors={"paper": object()},
        env=env_without_creds,
    )
    assert_true(paper_report["ready"] is True, "Paper mode should be ready when paper executor exists")

    live_report = execution_readiness_report(
        assets=[crypto_asset()],
        broker_configs=brokers,
        mode="live_guarded",
        live_trading_enabled={"crypto": True},
        executors={},
        env=env_with_creds,
    )
    live_blockers = blocker_names(live_report)
    assert_true(live_report["ready"] is False, "Live Bybit should remain blocked until adapter is wired")
    assert_true("executor_missing" in live_blockers, "Missing live executor should be reported")
    assert_true("adapter_validate_only" in live_blockers, "Validate-only adapter should be reported")
    assert_true("credentials_missing" not in live_blockers, "Present credentials should not be reported missing")
    assert_true("fake-key-value" not in str(live_report), "Readiness report must not echo API key values")
    assert_true("fake-secret-value" not in str(live_report), "Readiness report must not echo API secret values")

    missing_credential_report = execution_readiness_report(
        assets=[crypto_asset()],
        broker_configs=brokers,
        mode="live_guarded",
        live_trading_enabled={"crypto": True},
        executors={"bybit": object()},
        env=env_without_creds,
    )
    assert_true(
        "credentials_missing" in blocker_names(missing_credential_report),
        "Missing credential names should be reported without values",
    )

    print("Execution readiness smoke complete")
    print("ok=True")
    print(f"scan_blockers={scan_report['top_blockers']}")
    print(f"paper_ready={paper_report['ready']}")
    print(f"live_blockers={live_report['top_blockers']}")


if __name__ == "__main__":
    main()
