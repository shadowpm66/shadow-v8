from __future__ import annotations

from typing import Any, Mapping

from shadow_v8.tools.bybit_live_unlock_review import build_bybit_live_unlock_review, compact_lines


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
                        "coin": [
                            {"coin": "USDT", "walletBalance": "1000"},
                            {"coin": "BTC", "walletBalance": "1"},
                        ],
                    }
                ]
            },
        }


def fake_private_get(url: str, *, params: Mapping[str, Any], headers: Mapping[str, str], timeout: int) -> FakeResponse:
    assert "wallet-balance" in url
    assert params["accountType"] == "UNIFIED"
    assert headers["X-BAPI-API-KEY"] == FAKE_ENV["BYBIT_API_KEY"]
    assert timeout == 10
    return FakeResponse()


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    waiting = build_bybit_live_unlock_review(symbols="ETHUSDT,BTCUSDT", env=FAKE_ENV)
    assert_true(
        waiting["status"] == "WAITING_FOR_EC2_PRIVATE_VALIDATION",
        "Review should wait until read-only private validation has completed",
    )
    assert_true(waiting["live_orders_enabled"] is False, "Review must not enable live orders")
    assert_true("ec2_private_validation_not_complete" in waiting["blockers"], "Missing private validation should block")

    token_blocked = build_bybit_live_unlock_review(
        symbols=["ETHUSDT", "BTCUSDT"],
        env=FAKE_ENV,
        execute_private_validation=True,
        private_http_get=fake_private_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        token_blocked["status"] == "BLOCKED_DASHBOARD_TOKEN_ROTATION_REQUIRED",
        "Completed private validation should still require dashboard token rotation",
    )
    assert_true(token_blocked["private_validation_complete"] is True, "Private validation should be complete")
    assert_true("dashboard_token_rotation_required_before_live" in token_blocked["blockers"], "Token rotation should block")

    ready = build_bybit_live_unlock_review(
        symbols=["ETHUSDT", "BTCUSDT"],
        env=FAKE_ENV,
        execute_private_validation=True,
        private_http_get=fake_private_get,
        timestamp_ms=1_700_000_000_000,
        dashboard_token_rotated=True,
    )
    assert_true(
        ready["status"] == "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW",
        "Validated and rotated state should be ready for manual review only",
    )
    assert_true(ready["ok"] is True, "Ready review should be ok")
    assert_true(ready["manual_live_unlock_required"] is True, "Manual unlock must remain required")
    assert_true(ready["live_orders_enabled"] is False, "Ready review still must not enable live orders")
    assert_true("do_not_set_shadow_live_unlock_brokers_yet" in ready["next_actions"], "Review should not set unlock env")

    unlocked = build_bybit_live_unlock_review(
        symbols=["ETHUSDT"],
        env={**FAKE_ENV, "SHADOW_LIVE_UNLOCK_BROKERS": "bybit"},
        execute_private_validation=True,
        private_http_get=fake_private_get,
        dashboard_token_rotated=True,
    )
    assert_true(unlocked["status"] == "HALT_LIVE_UNLOCK_ALREADY_SET", "Early live unlock should halt review")
    assert_true("live_unlock_already_set" in unlocked["blockers"], "Early live unlock blocker should be explicit")

    compact = "\n".join(compact_lines(ready))
    assert_true("Shadow v8 Bybit live unlock review" in compact, "Compact report should include title")
    assert_true("READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW" in compact, "Compact report should show final review state")
    assert_true("fake-bybit-key" not in compact, "Compact report must not leak API key")
    assert_true("fake-bybit-secret" not in compact, "Compact report must not leak API secret")
    assert_true("fake-dashboard-token" not in compact, "Compact report must not leak dashboard token")

    print("Bybit live unlock review smoke complete")
    print("ok=True")
    print(f"waiting_status={waiting['status']}")
    print(f"token_blocked_status={token_blocked['status']}")
    print(f"ready_status={ready['status']}")


if __name__ == "__main__":
    main()
