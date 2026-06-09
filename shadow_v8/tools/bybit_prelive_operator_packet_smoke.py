from __future__ import annotations

import json
from typing import Any, Mapping

from shadow_v8.tools.bybit_prelive_operator_packet import (
    build_bybit_prelive_operator_packet,
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
    assert_true("wallet-balance" in url, "Operator packet should use wallet-balance validation")
    assert_true(params["accountType"] == "UNIFIED", "Operator packet should validate unified account only")
    assert_true(bool(headers.get("X-BAPI-SIGN")), "Operator packet should sign the read-only request")
    assert_true(timeout == 10, "Operator packet should keep request timeout bounded")
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
        assert_true(secret not in text, f"Operator packet must not expose {secret}")


def main() -> None:
    missing_env = build_bybit_prelive_operator_packet(symbols="ETHUSDT,BTCUSDT", env={})
    assert_true(
        missing_env["status"] == "PACKET_WAITING_FOR_EC2_ENV",
        "Missing env should wait for EC2 env load",
    )
    assert_true(missing_env["safe_to_enable_live"] is False, "Operator packet must never enable live")
    assert_sanitized(missing_env)

    needs_private = build_bybit_prelive_operator_packet(symbols=["ETHUSDT", "BTCUSDT"], env=FAKE_ENV)
    assert_true(
        needs_private["status"] == "PACKET_WAITING_FOR_READ_ONLY_PRIVATE_VALIDATION",
        "Credentials should ask for read-only private validation",
    )
    assert_true(
        "run_read_only_private_validation" in needs_private["manual_confirmations"],
        "Private validation confirmation should be explicit",
    )
    assert_sanitized(needs_private)

    needs_token = build_bybit_prelive_operator_packet(
        symbols="ETHUSDT,BTCUSDT",
        env=FAKE_ENV,
        execute_private_validation=True,
        private_http_get=fake_private_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        needs_token["status"] == "PACKET_WAITING_FOR_DASHBOARD_TOKEN_ROTATION",
        "Private validation should still require dashboard token rotation",
    )
    assert_true("rotate_dashboard_token" in needs_token["manual_confirmations"], "Token rotation should be explicit")
    assert_sanitized(needs_token)

    ready = build_bybit_prelive_operator_packet(
        symbols="ETHUSDT,BTCUSDT",
        env=FAKE_ENV,
        execute_private_validation=True,
        dashboard_token_rotated=True,
        private_http_get=fake_private_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        ready["status"] == "PACKET_READY_FOR_FINAL_OPERATOR_REVIEW",
        "Validated and token-rotated state should reach final operator review",
    )
    assert_true(ready["ok"] is True, "Ready packet should mark ok for final operator review")
    assert_true(ready["live_orders_enabled"] is False, "Ready packet still must not enable live")
    assert_true(ready["safe_to_enable_live"] is False, "Ready packet must not mark live enablement safe")
    assert_true(
        "record_manual_operator_go_no_go_decision" in ready["manual_confirmations"],
        "Ready packet should require a recorded manual decision",
    )
    assert_sanitized(ready)

    unlocked = build_bybit_prelive_operator_packet(
        symbols="ETHUSDT",
        env={**FAKE_ENV, "SHADOW_LIVE_UNLOCK_BROKERS": "bybit"},
    )
    assert_true(
        unlocked["status"] == "PACKET_HALTED_LIVE_UNLOCK_ALREADY_SET",
        "Early live unlock should halt the packet",
    )
    assert_true("clear_shadow_live_unlock_brokers" in unlocked["manual_confirmations"], "Unlock halt should say what to clear")
    assert_sanitized(unlocked)

    compact = "\n".join(compact_lines(ready))
    assert_true("Shadow v8 Bybit pre-live operator packet" in compact, "Compact output should include title")
    assert_true("PACKET_READY_FOR_FINAL_OPERATOR_REVIEW" in compact, "Compact output should show packet status")
    assert_true("Safe to enable live from this tool: False" in compact, "Compact output should show live safety")
    assert_true("fake-bybit-key" not in compact, "Compact output must not leak API key")
    assert_true("fake-bybit-secret" not in compact, "Compact output must not leak API secret")
    assert_true("fake-dashboard-token" not in compact, "Compact output must not leak dashboard token")

    print("Bybit pre-live operator packet smoke complete")
    print("ok=True")
    print(f"missing_env_status={missing_env['status']}")
    print(f"needs_private_status={needs_private['status']}")
    print(f"needs_token_status={needs_token['status']}")
    print(f"ready_status={ready['status']}")


if __name__ == "__main__":
    main()
