from __future__ import annotations

import json
from typing import Any, Mapping

from shadow_v8.tools.bybit_private_validation_probe import build_bybit_private_validation_probe, compact_lines


FAKE_ENV = {
    "BYBIT_API_KEY": "fake-key-value",
    "BYBIT_API_SECRET": "fake-secret-value",
}


class FakeResponse:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Mapping[str, Any]:
        return self.payload


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fake_http_get(url: str, *, params: Mapping[str, Any], headers: Mapping[str, str], timeout: int) -> FakeResponse:
    assert_true(url.endswith("/v5/account/wallet-balance"), "Private validation should call wallet-balance")
    assert_true(dict(params) == {"accountType": "UNIFIED"}, "Private validation should request unified account only")
    assert_true(headers.get("X-BAPI-API-KEY") == FAKE_ENV["BYBIT_API_KEY"], "Request should be signed with fake key")
    assert_true(bool(headers.get("X-BAPI-SIGN")), "Request should include a signature")
    assert_true(timeout == 10, "Private validation should use a bounded timeout")
    return FakeResponse(
        {
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
    )


def failing_ret_code_http_get(
    url: str, *, params: Mapping[str, Any], headers: Mapping[str, str], timeout: int
) -> FakeResponse:
    return FakeResponse({"retCode": 10001, "retMsg": "invalid request", "result": {}})


def assert_sanitized(report: Mapping[str, Any]) -> None:
    text = json.dumps(report, sort_keys=True, default=str)
    assert_true("fake-key-value" not in text, "Report must not expose raw API key")
    assert_true("fake-secret-value" not in text, "Report must not expose raw API secret")
    assert_true("123.45" not in text, "Report must not expose account balances")


def main() -> None:
    preview = build_bybit_private_validation_probe(env=FAKE_ENV, timestamp_ms=1_700_000_000_000)
    assert_true(preview["status"] == "SIGNED_PREVIEW_READY", "Fake credentials should produce a signed preview")
    assert_true(preview["ok"] is True, "Signed preview readiness should be ok")
    assert_true(preview["request_attempted"] is False, "Default probe should not call private Bybit endpoints")
    assert_true(preview["live_orders_enabled"] is False, "Probe must never enable live orders")
    assert_true("live_orders_disabled_validate_only" in preview["blockers"], "Validate-only safety blocker should remain")
    assert_sanitized(preview)

    executed = build_bybit_private_validation_probe(
        execute_private_request=True,
        env=FAKE_ENV,
        http_get=fake_http_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(executed["status"] == "PRIVATE_VALIDATION_READY", "Successful private probe should be ready")
    assert_true(executed["request_attempted"] is True, "Executed probe should attempt the private request")
    assert_true((executed["private_result"] or {}).get("ret_code") == 0, "Sanitized retCode should be retained")
    assert_true((executed["private_result"] or {}).get("account_count") == 1, "Account count should be retained")
    assert_true((executed["private_result"] or {}).get("coin_count") == 1, "Coin count should be retained")
    assert_sanitized(executed)

    missing = build_bybit_private_validation_probe(env={})
    assert_true(missing["status"] == "CREDENTIALS_PENDING", "Missing credentials should be explicit")
    assert_true("credentials_missing" in missing["blockers"], "Missing credentials blocker should be present")

    blocked = build_bybit_private_validation_probe(
        execute_private_request=True,
        env=FAKE_ENV,
        http_get=failing_ret_code_http_get,
        timestamp_ms=1_700_000_000_000,
    )
    assert_true(blocked["status"] == "PRIVATE_VALIDATION_BLOCKED", "Nonzero retCode should block private validation")
    assert_true(
        "private_validation_ret_code_nonzero" in blocked["blockers"],
        "Nonzero retCode blocker should be present",
    )
    assert_sanitized(blocked)

    compact = "\n".join(compact_lines(executed))
    assert_true("Shadow v8 Bybit private validation probe" in compact, "Compact report should include title")
    assert_true("Status: PRIVATE_VALIDATION_READY" in compact, "Compact report should include status")
    assert_true("Live orders enabled: False" in compact, "Compact report should show safety state")

    print("Bybit private validation probe smoke complete")
    print("ok=True")
    print(f"preview_status={preview['status']}")
    print(f"executed_status={executed['status']}")


if __name__ == "__main__":
    main()
