from __future__ import annotations

import json
from typing import Any, Mapping

from shadow_v8.tools.ec2_prelive_sequence_report import (
    build_ec2_prelive_sequence_report,
    compact_lines,
)


FAKE_ENV = {
    "BYBIT_API_KEY": "fake-bybit-key",
    "BYBIT_API_SECRET": "fake-bybit-secret",
    "TELEGRAM_BOT_TOKEN": "fake-telegram-token",
    "TELEGRAM_CHAT_ID": "fake-chat-id",
    "DASHBOARD_TOKEN": "fake-dashboard-token",
    "SHADOW_EXECUTION_MODE": "live_guarded",
    "SHADOW_LIVE_UNLOCK_BROKERS": "",
}


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "accountType": "UNIFIED",
                        "coin": [{"coin": "USDT", "walletBalance": "fake-wallet-balance"}],
                    }
                ]
            },
        }


def fake_private_get(url: str, *, params: Mapping[str, Any], headers: Mapping[str, str], timeout: int) -> FakeResponse:
    assert_true("wallet-balance" in url, "Private sequence should use wallet-balance validation")
    assert_true(params["accountType"] == "UNIFIED", "Private sequence should validate unified account only")
    assert_true(bool(headers.get("X-BAPI-SIGN")), "Private sequence should sign the read-only request")
    assert_true(timeout == 10, "Private sequence should keep request timeout bounded")
    return FakeResponse()


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_sanitized(report: Mapping[str, Any]) -> None:
    text = json.dumps(report, sort_keys=True, default=str)
    for secret in (
        "fake-bybit-key",
        "fake-bybit-secret",
        "fake-dashboard-token",
        "fake-telegram-token",
        "fake-chat-id",
        "walletBalance",
        "fake-wallet-balance",
    ):
        assert_true(secret not in text, f"Sequence report must not expose {secret}")


def main() -> None:
    waiting = build_ec2_prelive_sequence_report(symbols="ETHUSDT,BTCUSDT", env={})
    assert_true(waiting["status"] == "WAITING_FOR_EC2_CREDENTIALS", "Missing env should wait for EC2 credentials")
    assert_true(waiting["live_orders_enabled"] is False, "Sequence report must not enable live orders")
    assert_true("run_this_report_on_ec2_after_loading_env" in waiting["next_actions"], "Missing env should point to EC2")
    assert_sanitized(waiting)

    ready = build_ec2_prelive_sequence_report(symbols=["ETHUSDT", "BTCUSDT"], env=FAKE_ENV)
    assert_true(
        ready["status"] == "READY_FOR_READ_ONLY_PRIVATE_VALIDATION",
        "Fake credentials should be ready for the read-only private step",
    )
    assert_true(ready["ok"] is True, "Read-only ready sequence should be ok")
    assert_true(
        "run_ec2_prelive_sequence_with_execute_private_validation" in ready["next_actions"],
        "Ready sequence should ask for private validation next",
    )
    assert_sanitized(ready)

    token_waiting = build_ec2_prelive_sequence_report(
        symbols="ETHUSDT,BTCUSDT",
        env=FAKE_ENV,
        execute_private_validation=True,
        private_http_get=fake_private_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        token_waiting["status"] == "PRIVATE_VALIDATION_DONE_ROTATE_DASHBOARD_TOKEN",
        "Completed private validation should still require dashboard token rotation",
    )
    assert_true(
        "rotate_dashboard_token_before_final_live_review" in token_waiting["next_actions"],
        "Sequence should make dashboard token rotation explicit",
    )
    assert_sanitized(token_waiting)

    final_review = build_ec2_prelive_sequence_report(
        symbols="ETHUSDT,BTCUSDT",
        env=FAKE_ENV,
        execute_private_validation=True,
        dashboard_token_rotated=True,
        private_http_get=fake_private_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        final_review["status"] == "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW",
        "Validated and token-rotated state should be ready for manual review only",
    )
    assert_true(final_review["manual_live_unlock_required"] is True, "Manual live unlock must remain required")
    assert_true(final_review["live_orders_enabled"] is False, "Final review must still not enable live orders")
    assert_sanitized(final_review)

    unlocked = build_ec2_prelive_sequence_report(
        symbols="ETHUSDT",
        env={**FAKE_ENV, "SHADOW_LIVE_UNLOCK_BROKERS": "bybit"},
    )
    assert_true(unlocked["status"] == "HALT_LIVE_UNLOCK_ALREADY_SET", "Early live unlock should halt the sequence")
    assert_true("clear_shadow_live_unlock_brokers_until_final_review" in unlocked["next_actions"], "Unlock halt should say what to clear")
    assert_sanitized(unlocked)

    compact = "\n".join(compact_lines(final_review))
    assert_true("Shadow v8 EC2 pre-live sequence report" in compact, "Compact output should include title")
    assert_true("READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW" in compact, "Compact output should show final state")
    assert_true("cd ~/shadow-v8 && git pull --ff-only" in compact, "Compact output should include EC2 pull command")
    assert_true("fake-bybit-key" not in compact, "Compact output must not leak API key")
    assert_true("fake-bybit-secret" not in compact, "Compact output must not leak API secret")
    assert_true("fake-dashboard-token" not in compact, "Compact output must not leak dashboard token")

    print("EC2 pre-live sequence report smoke complete")
    print("ok=True")
    print(f"waiting_status={waiting['status']}")
    print(f"ready_status={ready['status']}")
    print(f"token_waiting_status={token_waiting['status']}")
    print(f"final_review_status={final_review['status']}")


if __name__ == "__main__":
    main()
