from __future__ import annotations

import json
from typing import Any, Mapping

from shadow_v8.tools.ec2_prelive_validation_audit import (
    build_ec2_prelive_validation_audit,
    compact_lines,
)


FAKE_ENV = {
    "BYBIT_API_KEY": "fake-key-value",
    "BYBIT_API_SECRET": "fake-secret-value",
    "DASHBOARD_TOKEN": "fake-dashboard-token",
    "TELEGRAM_BOT_TOKEN": "fake-telegram-token",
    "TELEGRAM_CHAT_ID": "fake-chat-id",
    "SHADOW_EXECUTION_MODE": "live_guarded",
}


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> Mapping[str, Any]:
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "accountType": "UNIFIED",
                        "coin": [{"coin": "USDT", "walletBalance": "123.45"}],
                    }
                ]
            },
        }


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fake_http_get(url: str, *, params: Mapping[str, Any], headers: Mapping[str, str], timeout: int) -> FakeResponse:
    assert_true(url.endswith("/v5/account/wallet-balance"), "Audit should use the read-only wallet endpoint")
    assert_true(dict(params) == {"accountType": "UNIFIED"}, "Audit should request unified account only")
    assert_true(bool(headers.get("X-BAPI-SIGN")), "Audit should use a signed private preview/request")
    assert_true(timeout == 10, "Audit should keep private validation timeout bounded")
    return FakeResponse()


def assert_sanitized(report: Mapping[str, Any]) -> None:
    text = json.dumps(report, sort_keys=True, default=str)
    for secret in (
        "fake-key-value",
        "fake-secret-value",
        "fake-dashboard-token",
        "fake-telegram-token",
        "fake-chat-id",
        "walletBalance",
        "123.45",
    ):
        assert_true(secret not in text, f"Audit must not expose {secret}")


def main() -> None:
    waiting = build_ec2_prelive_validation_audit(symbols="ETHUSDT,BTCUSDT", env={})
    assert_true(waiting["status"] == "WAITING_FOR_EC2_CREDENTIALS", "Missing env should wait for EC2 credentials")
    assert_true(waiting["env_presence"]["BYBIT_API_KEY"] is False, "Env presence should be boolean only")
    assert_true("load_ec2_env_without_printing" in waiting["next_actions"], "Audit should tell EC2 to load env safely")
    assert_true(waiting["live_orders_enabled"] is False, "Audit must not enable live orders")
    assert_sanitized(waiting)

    ready = build_ec2_prelive_validation_audit(symbols=["ETHUSDT", "BTCUSDT"], env=FAKE_ENV)
    assert_true(
        ready["status"] == "READY_FOR_EC2_READ_ONLY_PRIVATE_VALIDATION",
        "Fake credentials should be ready for read-only private validation",
    )
    assert_true(ready["ok"] is True, "Ready audit should be ok while still validate-only")
    assert_true(ready["env_presence"]["BYBIT_API_SECRET"] is True, "Env presence should show credential availability")
    assert_true(
        "rotate_dashboard_token_before_live" in ready["next_actions"],
        "Dashboard token rotation should remain a pre-live action",
    )
    assert_sanitized(ready)

    unlocked = build_ec2_prelive_validation_audit(
        symbols="ETHUSDT,BTCUSDT",
        env={**FAKE_ENV, "SHADOW_LIVE_UNLOCK_BROKERS": "bybit"},
    )
    assert_true(
        unlocked["status"] == "HALT_LIVE_UNLOCK_ALREADY_SET",
        "Audit should halt if live unlock is set before final review",
    )
    assert_true("live_unlock_already_set" in unlocked["blockers"], "Live unlock blocker should be explicit")
    assert_true(
        "clear_shadow_live_unlock_brokers_until_final_review" in unlocked["next_actions"],
        "Audit should ask to clear early live unlocks",
    )
    assert_sanitized(unlocked)

    complete = build_ec2_prelive_validation_audit(
        symbols="ETHUSDT,BTCUSDT",
        execute_private_validation=True,
        env=FAKE_ENV,
        private_http_get=fake_http_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        complete["status"] == "EC2_PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY",
        "Read-only private validation should complete without live trading",
    )
    assert_true(complete["request_attempted"] is True, "Executed audit should attempt the read-only request")
    assert_true(
        "review_private_validation_then_prepare_live_unlock_decision" in complete["next_actions"],
        "Completed private validation should move to review, not live orders",
    )
    assert_sanitized(complete)

    compact = "\n".join(compact_lines(ready))
    assert_true("Shadow v8 EC2 pre-live validation audit" in compact, "Compact output should include title")
    assert_true("Status: READY_FOR_EC2_READ_ONLY_PRIVATE_VALIDATION" in compact, "Compact output should show status")
    assert_true("BYBIT_API_KEY: True" in compact, "Compact output should show boolean env presence")
    assert_true("fake-key-value" not in compact, "Compact output must not expose secrets")
    assert_true("cd ~/shadow-v8 && git pull --ff-only" in compact, "Compact output should include EC2 pull command")

    print("EC2 pre-live validation audit smoke complete")
    print("ok=True")
    print(f"waiting_status={waiting['status']}")
    print(f"ready_status={ready['status']}")
    print(f"complete_status={complete['status']}")


if __name__ == "__main__":
    main()
