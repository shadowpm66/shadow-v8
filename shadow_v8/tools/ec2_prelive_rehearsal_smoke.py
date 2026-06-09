from __future__ import annotations

import json
from typing import Any, Mapping

from shadow_v8.tools.ec2_prelive_rehearsal import build_ec2_prelive_rehearsal, compact_lines


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
    assert_true("wallet-balance" in url, "Rehearsal should use wallet-balance validation")
    assert_true(params["accountType"] == "UNIFIED", "Rehearsal should validate unified account only")
    assert_true(bool(headers.get("X-BAPI-SIGN")), "Rehearsal should sign the read-only request")
    assert_true(timeout == 10, "Rehearsal should keep request timeout bounded")
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
        assert_true(secret not in text, f"Rehearsal report must not expose {secret}")


def main() -> None:
    missing_env = build_ec2_prelive_rehearsal(symbols="ETHUSDT,BTCUSDT", env={})
    assert_true(
        missing_env["rehearsal_status"] == "REHEARSAL_WAITING_FOR_EC2_ENV",
        "Missing env should wait for EC2 env load",
    )
    assert_true(missing_env["safe_to_enable_live"] is False, "Rehearsal must never mark live enablement safe")
    assert_sanitized(missing_env)

    needs_private = build_ec2_prelive_rehearsal(symbols=["ETHUSDT", "BTCUSDT"], env=FAKE_ENV)
    assert_true(
        needs_private["rehearsal_status"] == "REHEARSAL_WAITING_FOR_PRIVATE_VALIDATION",
        "Credentials should lead to read-only private validation",
    )
    assert_true(needs_private["live_orders_enabled"] is False, "Rehearsal must not enable live orders")
    assert_sanitized(needs_private)

    needs_token = build_ec2_prelive_rehearsal(
        symbols="ETHUSDT,BTCUSDT",
        env=FAKE_ENV,
        execute_private_validation=True,
        private_http_get=fake_private_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        needs_token["rehearsal_status"] == "REHEARSAL_WAITING_FOR_DASHBOARD_TOKEN_ROTATION",
        "Private validation should still require dashboard token rotation",
    )
    assert_true("rotate_dashboard_token" in needs_token["operator_must_do"], "Token rotation should be explicit")
    assert_sanitized(needs_token)

    final_review = build_ec2_prelive_rehearsal(
        symbols="ETHUSDT,BTCUSDT",
        env=FAKE_ENV,
        execute_private_validation=True,
        dashboard_token_rotated=True,
        private_http_get=fake_private_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        final_review["rehearsal_status"] == "REHEARSAL_READY_FOR_OPERATOR_REVIEW",
        "Validated and token-rotated state should be ready for operator review",
    )
    assert_true(final_review["ok"] is True, "Final rehearsal should be operator-review ready")
    assert_true(final_review["safe_to_enable_live"] is False, "Final rehearsal still must not enable live")
    assert_true(final_review["manual_live_unlock_required"] is True, "Manual live unlock must remain required")
    assert_sanitized(final_review)

    unlocked = build_ec2_prelive_rehearsal(
        symbols="ETHUSDT",
        env={**FAKE_ENV, "SHADOW_LIVE_UNLOCK_BROKERS": "bybit"},
    )
    assert_true(
        unlocked["rehearsal_status"] == "REHEARSAL_HALTED_LIVE_UNLOCK_ALREADY_SET",
        "Early live unlock should halt rehearsal",
    )
    assert_true(unlocked["safe_to_enable_live"] is False, "Early unlock halt must not enable live")
    assert_sanitized(unlocked)

    compact = "\n".join(compact_lines(final_review))
    assert_true("Shadow v8 EC2 pre-live rehearsal" in compact, "Compact output should include title")
    assert_true("REHEARSAL_READY_FOR_OPERATOR_REVIEW" in compact, "Compact output should show final status")
    assert_true("Safe to enable live from this tool: False" in compact, "Compact output should show live safety")
    assert_true("fake-bybit-key" not in compact, "Compact output must not leak API key")
    assert_true("fake-bybit-secret" not in compact, "Compact output must not leak API secret")
    assert_true("fake-dashboard-token" not in compact, "Compact output must not leak dashboard token")

    print("EC2 pre-live rehearsal smoke complete")
    print("ok=True")
    print(f"missing_env_status={missing_env['rehearsal_status']}")
    print(f"needs_private_status={needs_private['rehearsal_status']}")
    print(f"needs_token_status={needs_token['rehearsal_status']}")
    print(f"final_review_status={final_review['rehearsal_status']}")


if __name__ == "__main__":
    main()
