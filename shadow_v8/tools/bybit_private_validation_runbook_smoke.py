from __future__ import annotations

import json
from typing import Any, Mapping

from shadow_v8.tools.bybit_private_validation_runbook import (
    build_bybit_private_validation_runbook,
    compact_lines,
)


FAKE_ENV = {
    "BYBIT_API_KEY": "fake-key-value",
    "BYBIT_API_SECRET": "fake-secret-value",
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
                        "coin": [
                            {
                                "coin": "USDT",
                                "walletBalance": "123.45",
                            }
                        ],
                    }
                ]
            },
        }


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_sanitized(report: Mapping[str, Any]) -> None:
    text = json.dumps(report, sort_keys=True, default=str)
    assert_true("fake-key-value" not in text, "Runbook must not expose raw API key")
    assert_true("fake-secret-value" not in text, "Runbook must not expose raw API secret")
    assert_true("walletBalance" not in text, "Runbook must not expose private balance fields")
    assert_true("123.45" not in text, "Runbook must not expose private balances")


def fake_http_get(url: str, *, params: Mapping[str, Any], headers: Mapping[str, str], timeout: int) -> FakeResponse:
    assert_true(url.endswith("/v5/account/wallet-balance"), "Runbook should call wallet-balance through probe")
    assert_true(dict(params) == {"accountType": "UNIFIED"}, "Runbook should request unified account only")
    assert_true(bool(headers.get("X-BAPI-SIGN")), "Signed request should include a signature")
    assert_true(timeout == 10, "Private validation should use bounded timeout")
    return FakeResponse()


def main() -> None:
    waiting = build_bybit_private_validation_runbook(
        symbols="ETHUSDT,BTCUSDT",
        env={},
    )
    assert_true(waiting["status"] == "WAITING_FOR_EC2_CREDENTIALS", "Missing credentials should wait for EC2 env")
    assert_true(waiting["live_orders_enabled"] is False, "Runbook must keep live orders disabled")
    assert_true("run_on_ec2_with_env_loaded" in waiting["next_actions"], "Runbook should direct EC2 credential loading")
    assert_true(any(item["step"] == "load_credentials_without_printing" for item in waiting["commands"]), "Env step missing")

    ready = build_bybit_private_validation_runbook(
        symbols=["ETHUSDT", "BTCUSDT"],
        env=FAKE_ENV,
    )
    assert_true(
        ready["status"] == "READY_FOR_READ_ONLY_PRIVATE_VALIDATION",
        "Fake credentials should be ready for read-only validation",
    )
    assert_true(ready["private_validation_status"] == "SIGNED_PREVIEW_READY", "Signed preview status should be exposed")
    assert_true(ready["prelive_checklist_status"] == "VALIDATE_ONLY_READY", "Checklist status should be exposed")
    assert_true("run_execute_private_request_on_ec2" in ready["next_actions"], "Next action should be private probe")
    assert_true(
        any(item["step"] == "read_only_private_validation" for item in ready["commands"]) is False,
        "Default runbook should not include execute-private command",
    )
    assert_sanitized(ready)

    execute_ready = build_bybit_private_validation_runbook(
        symbols="ETHUSDT,BTCUSDT",
        execute_private_validation=True,
        env=FAKE_ENV,
        private_http_get=fake_http_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(
        execute_ready["status"] == "PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY",
        "Injected execute path should report private validation completion",
    )
    assert_true(
        any(item["step"] == "read_only_private_validation" for item in execute_ready["commands"]),
        "Execute runbook should include the read-only private validation command",
    )
    assert_true(
        "do_not_place_live_orders" in execute_ready["next_actions"],
        "Runbook should keep live order placement blocked",
    )
    assert_sanitized(execute_ready)

    compact = "\n".join(compact_lines(ready))
    assert_true("Shadow v8 Bybit private validation runbook" in compact, "Compact output should include title")
    assert_true("Status: READY_FOR_READ_ONLY_PRIVATE_VALIDATION" in compact, "Compact output should show status")
    assert_true("Live orders enabled: False" in compact, "Compact output should show live-order safety")
    assert_true("cd ~/shadow-v8 && git pull --ff-only" in compact, "Compact output should include EC2 pull command")

    print("Bybit private validation runbook smoke complete")
    print("ok=True")
    print(f"waiting_status={waiting['status']}")
    print(f"ready_status={ready['status']}")


if __name__ == "__main__":
    main()
