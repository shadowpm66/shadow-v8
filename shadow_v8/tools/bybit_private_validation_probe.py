from __future__ import annotations

import argparse
import json
from hashlib import sha256
from hmac import new as hmac_new
from time import time
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from shadow_v8.config import BROKERS
from shadow_v8.execution.bybit_order_manager import BybitOrderManager


PRIVATE_VALIDATION_PATH = "/v5/account/wallet-balance"
PRIVATE_VALIDATION_PARAMS = {"accountType": "UNIFIED"}


def _requests_get(url: str, *, params: Mapping[str, Any], headers: Mapping[str, str], timeout: int) -> Any:
    import requests

    return requests.get(url, params=params, headers=headers, timeout=timeout)


def _signed_get_headers(
    *,
    env: Mapping[str, str],
    params: Mapping[str, Any],
    timestamp_ms: int,
    recv_window: str,
) -> dict[str, str]:
    api_key = str(env.get("BYBIT_API_KEY", "") or "").strip()
    api_secret = str(env.get("BYBIT_API_SECRET", "") or "").strip()
    query = urlencode(sorted((key, str(value)) for key, value in params.items()))
    sign_payload = f"{timestamp_ms}{api_key}{recv_window}{query}"
    signature = hmac_new(api_secret.encode("utf-8"), sign_payload.encode("utf-8"), sha256).hexdigest()
    return {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": str(timestamp_ms),
        "X-BAPI-RECV-WINDOW": recv_window,
    }


def _sanitize_private_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload, Mapping) else None
    rows = (result or {}).get("list") if isinstance(result, Mapping) else []
    coin_count = 0
    account_types: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                account_type = row.get("accountType")
                if account_type:
                    account_types.append(str(account_type))
                coins = row.get("coin")
                if isinstance(coins, list):
                    coin_count += len(coins)
    return {
        "ret_code": payload.get("retCode"),
        "ret_msg": payload.get("retMsg"),
        "result_present": isinstance(result, Mapping),
        "account_types": sorted(set(account_types)),
        "account_count": len(rows) if isinstance(rows, list) else 0,
        "coin_count": coin_count,
    }


def build_bybit_private_validation_probe(
    *,
    execute_private_request: bool = False,
    base_url: str | None = None,
    env: Mapping[str, str] | None = None,
    http_get: Callable[..., Any] | None = None,
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    manager = BybitOrderManager(env=env)
    config = manager.validate_config()
    timestamp_ms = timestamp_ms or int(time() * 1000)
    params = dict(PRIVATE_VALIDATION_PARAMS)
    signed_preview = manager.signed_request_preview(
        method="GET",
        path=PRIVATE_VALIDATION_PATH,
        params=params,
        timestamp_ms=timestamp_ms,
    )
    blockers = list(config["blockers"])
    blockers.extend(f"signed:{blocker}" for blocker in signed_preview["blockers"])
    private_result = None
    request_attempted = False
    base = (base_url or BROKERS["bybit"].base_url or "https://api.bybit.com").rstrip("/")

    if execute_private_request:
        request_attempted = True
        if not signed_preview["ok"]:
            blockers.append("signed_preview_not_ready")
        else:
            try:
                headers = _signed_get_headers(
                    env=manager.env,
                    params=params,
                    timestamp_ms=timestamp_ms,
                    recv_window=manager.recv_window,
                )
                response = (http_get or _requests_get)(
                    f"{base}{PRIVATE_VALIDATION_PATH}",
                    params=params,
                    headers=headers,
                    timeout=10,
                )
                response.raise_for_status()
                payload = response.json()
                private_result = _sanitize_private_payload(payload)
                if payload.get("retCode") != 0:
                    blockers.append("private_validation_ret_code_nonzero")
            except Exception as exc:  # noqa: BLE001 - sanitized operator probe output.
                private_result = {"error_type": type(exc).__name__}
                blockers.append("private_validation_request_failed")

    credentials_present = bool(config.get("credentials_present"))
    private_ok = bool(private_result and private_result.get("ret_code") == 0)
    if not credentials_present:
        status = "CREDENTIALS_PENDING"
    elif execute_private_request and private_ok:
        status = "PRIVATE_VALIDATION_READY"
    elif execute_private_request:
        status = "PRIVATE_VALIDATION_BLOCKED"
    elif signed_preview["ok"]:
        status = "SIGNED_PREVIEW_READY"
    else:
        status = "SIGNED_PREVIEW_BLOCKED"

    return {
        "ok": status in {"SIGNED_PREVIEW_READY", "PRIVATE_VALIDATION_READY"},
        "mode": "bybit_private_validation_validate_only",
        "status": status,
        "endpoint": PRIVATE_VALIDATION_PATH,
        "method": "GET",
        "params": params,
        "request_attempted": request_attempted,
        "execute_private_request": execute_private_request,
        "live_orders_enabled": False,
        "credentials_present": credentials_present,
        "config": config,
        "signed_preview": signed_preview,
        "private_result": private_result,
        "blockers": sorted(set(blockers)),
        "next_actions": _next_actions(status),
    }


def _next_actions(status: str) -> list[str]:
    actions = ["keep_live_orders_disabled"]
    if status == "CREDENTIALS_PENDING":
        actions.append("load_bybit_credentials_on_ec2")
    elif status == "SIGNED_PREVIEW_READY":
        actions.append("run_with_execute_private_request_on_ec2")
    elif status == "PRIVATE_VALIDATION_READY":
        actions.append("continue_to_testnet_or_tiny_live_unlock_review")
    else:
        actions.append("inspect_private_validation_blockers")
    actions.append("do_not_place_live_orders")
    return actions


def compact_lines(report: Mapping[str, Any]) -> list[str]:
    private_result = report.get("private_result") or {}
    lines = [
        "Shadow v8 Bybit private validation probe",
        f"Status: {report.get('status', '-')}",
        f"Endpoint: {report.get('method', '-')} {report.get('endpoint', '-')}",
        f"Request attempted: {report.get('request_attempted')}",
        f"Credentials present: {report.get('credentials_present')}",
        f"Signed preview ok: {(report.get('signed_preview') or {}).get('ok')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
    ]
    if private_result:
        lines.append(f"Private retCode: {private_result.get('ret_code', '-')}")
        lines.append(f"Private result present: {private_result.get('result_present', '-')}")
        lines.append(f"Private account count: {private_result.get('account_count', '-')}")
        lines.append(f"Private coin count: {private_result.get('coin_count', '-')}")
    blockers = report.get("blockers") or []
    lines.append("Blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"))
    lines.append("Next actions: " + ", ".join(str(item) for item in report.get("next_actions") or []))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a sanitized validate-only Bybit private validation probe.")
    parser.add_argument("--base-url")
    parser.add_argument(
        "--execute-private-request",
        action="store_true",
        help="Make a read-only signed Bybit account request. Never places orders.",
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_bybit_private_validation_probe(
        execute_private_request=args.execute_private_request,
        base_url=args.base_url,
    )
    if args.compact:
        print("\n".join(compact_lines(report)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
