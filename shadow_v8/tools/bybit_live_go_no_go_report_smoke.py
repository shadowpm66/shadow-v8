from __future__ import annotations

import json
from typing import Any, Mapping

from shadow_v8.tools.bybit_live_go_no_go_report import (
    build_bybit_live_go_no_go_report,
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
    assert_true("wallet-balance" in url, "Go/no-go report should use wallet-balance validation")
    assert_true(params["accountType"] == "UNIFIED", "Go/no-go report should validate unified account only")
    assert_true(bool(headers.get("X-BAPI-SIGN")), "Go/no-go report should sign the read-only request")
    assert_true(timeout == 10, "Go/no-go report should keep request timeout bounded")
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
        assert_true(secret not in text, f"Go/no-go report must not expose {secret}")


def main() -> None:
    missing_env = build_bybit_live_go_no_go_report(symbols="ETHUSDT,BTCUSDT", env={})
    assert_true(missing_env["decision"] == "NO_GO_LOAD_EC2_ENV_FIRST", "Missing env should block on EC2 env load")
    assert_true(missing_env["ok"] is False, "Missing env must not be operator-ready")
    assert_true(".env" in missing_env["safe_next_command"], "Missing env should point to loading .env")
    assert_sanitized(missing_env)

    needs_private = build_bybit_live_go_no_go_report(symbols=["ETHUSDT", "BTCUSDT"], env=FAKE_ENV)
    assert_true(
        needs_private["decision"] == "NO_GO_RUN_READ_ONLY_PRIVATE_VALIDATION",
        "Credentials without private validation should ask for read-only private validation",
    )
    assert_true(needs_private["live_orders_enabled"] is False, "Report must never enable live orders")
    assert_sanitized(needs_private)

    needs_token = build_bybit_live_go_no_go_report(
        symbols="ETHUSDT,BTCUSDT",
        env=FAKE_ENV,
        execute_private_validation=True,
        private_http_get=fake_private_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        needs_token["decision"] == "NO_GO_ROTATE_DASHBOARD_TOKEN",
        "Private validation should still require dashboard token rotation",
    )
    assert_true("rotate_dashboard_token" in needs_token["required_before_live"], "Token state should list rotation")
    assert_sanitized(needs_token)

    final_review = build_bybit_live_go_no_go_report(
        symbols="ETHUSDT,BTCUSDT",
        env=FAKE_ENV,
        execute_private_validation=True,
        dashboard_token_rotated=True,
        private_http_get=fake_private_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        final_review["decision"] == "READY_FOR_OPERATOR_GO_NO_GO_REVIEW",
        "Validated and token-rotated state should be ready for operator review",
    )
    assert_true(final_review["ok"] is True, "Final review state should be operator-ready")
    assert_true(final_review["manual_live_unlock_required"] is True, "Manual live unlock must remain required")
    assert_true(final_review["live_orders_enabled"] is False, "Final review must still not enable live orders")
    assert_true(
        "manual_live_unlock_change_required" in final_review["required_before_live"],
        "Final review should still require a manual live unlock change",
    )
    assert_sanitized(final_review)

    unlocked = build_bybit_live_go_no_go_report(
        symbols="ETHUSDT",
        env={**FAKE_ENV, "SHADOW_LIVE_UNLOCK_BROKERS": "bybit"},
    )
    assert_true(
        unlocked["decision"] == "NO_GO_LIVE_UNLOCK_ALREADY_SET",
        "Early live unlock should block the go/no-go report",
    )
    assert_true("clear_shadow_live_unlock_brokers" in unlocked["required_before_live"], "Unlock halt should say what to clear")
    assert_sanitized(unlocked)

    compact = "\n".join(compact_lines(final_review))
    assert_true("Shadow v8 Bybit live go/no-go report" in compact, "Compact output should include title")
    assert_true("READY_FOR_OPERATOR_GO_NO_GO_REVIEW" in compact, "Compact output should show final decision")
    assert_true("Live orders enabled: False" in compact, "Compact output should show live orders disabled")
    assert_true("fake-bybit-key" not in compact, "Compact output must not leak API key")
    assert_true("fake-bybit-secret" not in compact, "Compact output must not leak API secret")
    assert_true("fake-dashboard-token" not in compact, "Compact output must not leak dashboard token")

    print("Bybit live go/no-go report smoke complete")
    print("ok=True")
    print(f"missing_env_decision={missing_env['decision']}")
    print(f"needs_private_decision={needs_private['decision']}")
    print(f"needs_token_decision={needs_token['decision']}")
    print(f"final_review_decision={final_review['decision']}")


if __name__ == "__main__":
    main()
