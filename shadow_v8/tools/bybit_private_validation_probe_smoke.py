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
        self.status_code = 200
        self.reason = "OK"
        self.text = json.dumps(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Mapping[str, Any]:
        return self.payload


class FakeHTTPError(Exception):
    def __init__(self, response: Any) -> None:
        super().__init__("fake http error with raw response hidden")
        self.response = response


class FakeHTTPErrorResponse:
    def __init__(
        self,
        *,
        status_code: int,
        reason: str,
        payload: Mapping[str, Any] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self.reason = reason
        self.payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        raise FakeHTTPError(self)

    def json(self) -> Mapping[str, Any]:
        if self.payload is None:
            raise ValueError("not json")
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


def http_error_json_http_get(
    url: str, *, params: Mapping[str, Any], headers: Mapping[str, str], timeout: int
) -> FakeHTTPErrorResponse:
    return FakeHTTPErrorResponse(
        status_code=403,
        reason="Forbidden",
        payload={
            "retCode": 10010,
            "retMsg": "Unmatched IP, please check your API key's bound IP addresses",
            "retExtInfo": {"ip": "172.31.31.167", "secret_hint": "fake-secret-value"},
            "result": {
                "list": [
                    {
                        "accountType": "UNIFIED",
                        "coin": [{"coin": "USDT", "walletBalance": "999999"}],
                    }
                ]
            },
        },
        text='{"retCode":10010,"retMsg":"Unmatched IP","walletBalance":"999999","apiKey":"fake-key-value"}',
    )


def http_error_text_http_get(
    url: str, *, params: Mapping[str, Any], headers: Mapping[str, str], timeout: int
) -> FakeHTTPErrorResponse:
    return FakeHTTPErrorResponse(
        status_code=401,
        reason="Unauthorized",
        payload=None,
        text="raw body fake-secret-value walletBalance 888888",
    )


def assert_sanitized(report: Mapping[str, Any]) -> None:
    text = json.dumps(report, sort_keys=True, default=str)
    assert_true("fake-key-value" not in text, "Report must not expose raw API key")
    assert_true("fake-secret-value" not in text, "Report must not expose raw API secret")
    assert_true("123.45" not in text, "Report must not expose account balances")
    assert_true("999999" not in text, "Report must not expose balances from failed responses")
    assert_true("888888" not in text, "Report must not expose raw failed response text")
    assert_true("172.31.31.167" not in text, "Report must not expose retExtInfo values")
    assert_true("walletBalance" not in text, "Report must not expose private balance field names")


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
    assert_true((executed["private_result"] or {}).get("body_kind") == "json", "Success response kind should be JSON")
    assert_true(
        (executed["private_result"] or {}).get("ret_ext_info_present") is False,
        "Success retExtInfo presence should be shape-only",
    )
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

    http_blocked = build_bybit_private_validation_probe(
        execute_private_request=True,
        env=FAKE_ENV,
        http_get=http_error_json_http_get,
        timestamp_ms=1_700_000_000_000,
    )
    http_result = http_blocked["private_result"] or {}
    assert_true(
        http_blocked["status"] == "PRIVATE_VALIDATION_BLOCKED",
        "HTTP errors should block private validation",
    )
    assert_true(http_result.get("error_type") == "FakeHTTPError", "HTTP error type should be surfaced")
    assert_true(http_result.get("http_status") == 403, "HTTP status should be surfaced")
    assert_true(http_result.get("body_kind") == "json", "JSON error body kind should be surfaced")
    assert_true(http_result.get("bybit_ret_code") == 10010, "Bybit retCode should be surfaced safely")
    assert_true(
        "Unmatched IP" in str(http_result.get("bybit_ret_msg")),
        "Bybit retMsg should be surfaced safely",
    )
    assert_true(http_result.get("bybit_result_present") is True, "Result presence should be shape-only")
    assert_true(
        http_result.get("bybit_ret_ext_info_present") is True,
        "retExtInfo presence should be surfaced without values",
    )
    assert_true(http_result.get("response_text_present") is True, "Raw response presence should be shape-only")
    assert_sanitized(http_blocked)

    text_blocked = build_bybit_private_validation_probe(
        execute_private_request=True,
        env=FAKE_ENV,
        http_get=http_error_text_http_get,
        timestamp_ms=1_700_000_000_000,
    )
    text_result = text_blocked["private_result"] or {}
    assert_true(text_result.get("http_status") == 401, "HTTP status should be surfaced for non-JSON failures")
    assert_true(text_result.get("body_kind") == "text", "Text error body kind should be surfaced")
    assert_true(text_result.get("response_json_present") is False, "Non-JSON response should be identified")
    assert_true(text_result.get("response_text_present") is True, "Text presence should be shape-only")
    assert_true("bybit_ret_msg" not in text_result, "Raw non-JSON text must not be surfaced as retMsg")
    assert_sanitized(text_blocked)

    compact = "\n".join(compact_lines(executed))
    assert_true("Shadow v8 Bybit private validation probe" in compact, "Compact report should include title")
    assert_true("Status: PRIVATE_VALIDATION_READY" in compact, "Compact report should include status")
    assert_true("Live orders enabled: False" in compact, "Compact report should show safety state")
    error_compact = "\n".join(compact_lines(http_blocked))
    assert_true("Private HTTP status: 403" in error_compact, "Compact report should include safe HTTP status")
    assert_true("Private body kind: json" in error_compact, "Compact report should include safe body kind")
    assert_true("Private Bybit retCode: 10010" in error_compact, "Compact report should include safe Bybit retCode")
    assert_true("Private Bybit retMsg: Unmatched IP" in error_compact, "Compact report should include safe Bybit retMsg")
    assert_true(
        "Private Bybit retExtInfo present: True" in error_compact,
        "Compact report should include retExtInfo presence only",
    )
    assert_true("walletBalance" not in error_compact, "Compact report must not expose raw private payload fields")

    print("Bybit private validation probe smoke complete")
    print("ok=True")
    print(f"preview_status={preview['status']}")
    print(f"executed_status={executed['status']}")


if __name__ == "__main__":
    main()
