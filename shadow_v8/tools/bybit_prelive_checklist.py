from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any, Mapping, Sequence

from shadow_v8.data.bybit_market_data import BybitMarketData
from shadow_v8.execution.bybit_order_manager import BybitOrderManager
from shadow_v8.models import AssetConfig
from shadow_v8.tools.bybit_public_dry_run_batch import (
    build_bybit_public_dry_run_batch,
    offline_sample_instrument,
    parse_symbols,
)
from shadow_v8.tools.bybit_private_validation_probe import build_bybit_private_validation_probe
from shadow_v8.tools.execution_readiness_report import build_execution_readiness_report


def _asset(symbol: str) -> AssetConfig:
    return AssetConfig(
        symbol=symbol.upper(),
        asset_class="crypto",
        broker="bybit",
        primary_timeframe="15m",
        confirmation_timeframe="1h",
        allow_long=True,
        allow_short=True,
        max_risk_pct=0.03,
    )


def _public_instrument(symbol: str, base_url: str | None) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = BybitMarketData(base_url=base_url).get_linear_instrument(symbol)
    except Exception as exc:
        return None, f"public_instrument_fetch_failed:{type(exc).__name__}"
    if not payload:
        return None, "public_instrument_missing"
    return payload, None


def _blocker_counter(*groups: Any) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for group in groups:
        if isinstance(group, Mapping):
            counter.update({str(key): int(value) for key, value in group.items()})
        else:
            counter.update(str(item) for item in (group or []))
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _execution_blockers(report: Mapping[str, Any]) -> list[str]:
    return [str(item.get("reason")) for item in report.get("top_blockers") or [] if item.get("reason")]


def _status(*, payload_validate_ready: bool, credential_ready: bool, public_blockers: list[str]) -> str:
    if public_blockers or not payload_validate_ready:
        return "BLOCKED"
    if not credential_ready:
        return "CREDENTIALS_PENDING"
    return "VALIDATE_ONLY_READY"


def _next_actions(status: str, blockers: Mapping[str, int]) -> list[str]:
    actions = ["keep_live_orders_disabled"]
    if status == "BLOCKED":
        actions.append("fix_payload_or_public_instrument_blockers")
    if status == "CREDENTIALS_PENDING" or "credentials_missing" in blockers or "signed:credentials_missing" in blockers:
        actions.append("verify_bybit_credentials_on_ec2")
    if status == "VALIDATE_ONLY_READY":
        actions.append("run_private_signed_validation_before_live_unlock")
    if "private_validation_request_failed" in blockers or "private_validation_ret_code_nonzero" in blockers:
        actions.append("inspect_private_validation_probe")
    actions.append("do_not_enable_live_orders_yet")
    return actions


def build_bybit_prelive_checklist(
    *,
    symbols: str | Sequence[str] | None = None,
    direction: str = "LONG",
    risk_pct: float = 0.01,
    account_balance: float = 10_000.0,
    fetch_public_instrument: bool = True,
    base_url: str | None = None,
    include_signed_preview: bool = True,
    include_private_validation: bool = False,
    execute_private_validation: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    parsed_symbols = parse_symbols(symbols)
    primary_symbol = parsed_symbols[0] if parsed_symbols else "ETHUSDT"
    public_blockers: list[str] = []

    execution = build_execution_readiness_report(
        mode="live_guarded",
        include_disabled_assets=False,
        env=env,
        executors={"bybit": object()},
    )

    if fetch_public_instrument:
        instrument_payload, public_error = _public_instrument(primary_symbol, base_url)
        if public_error:
            public_blockers.append(public_error)
    else:
        instrument_payload = offline_sample_instrument(primary_symbol)

    preflight = BybitOrderManager(env=env).preflight_report(
        _asset(primary_symbol),
        instrument_payload,
        include_signed_preview=include_signed_preview,
    )
    batch = build_bybit_public_dry_run_batch(
        symbols=parsed_symbols,
        direction=direction,
        risk_pct=risk_pct,
        account_balance=account_balance,
        fetch_public_instrument=fetch_public_instrument,
        base_url=base_url,
        env=env,
    )
    private_validation = None
    if include_private_validation:
        private_validation = build_bybit_private_validation_probe(
            execute_private_request=execute_private_validation,
            base_url=base_url,
            env=env,
        )

    batch_summary = batch.get("summary") or {}
    payload_validate_ready = bool(batch.get("ready_for_validate_only")) and not public_blockers
    credential_ready = bool((preflight.get("config") or {}).get("credentials_present"))
    signed_preview = preflight.get("signed_preview") or {}
    if include_signed_preview:
        credential_ready = credential_ready and bool(signed_preview.get("ok"))
    live_orders_enabled = any(
        bool(item)
        for item in (
            batch.get("live_orders_enabled"),
            batch_summary.get("live_orders_enabled_any"),
            preflight.get("live_orders_enabled"),
        )
    )

    blocker_counts = _blocker_counter(
        _execution_blockers(execution),
        preflight.get("blockers") or [],
        batch_summary.get("blocker_counts") or {},
        public_blockers,
        (private_validation or {}).get("blockers") or [],
    )
    status = "UNSAFE_LIVE_ENABLED" if live_orders_enabled else _status(
        payload_validate_ready=payload_validate_ready,
        credential_ready=credential_ready,
        public_blockers=public_blockers,
    )
    private_status = (private_validation or {}).get("status")
    if private_status == "PRIVATE_VALIDATION_BLOCKED":
        status = "BLOCKED"
    elif private_status == "CREDENTIALS_PENDING":
        status = "CREDENTIALS_PENDING"
    return {
        "ok": status == "VALIDATE_ONLY_READY",
        "mode": "bybit_prelive_checklist_validate_only",
        "status": status,
        "symbols": parsed_symbols,
        "primary_symbol": primary_symbol,
        "direction": direction.upper(),
        "fetch_public_instrument": fetch_public_instrument,
        "include_signed_preview": include_signed_preview,
        "include_private_validation": include_private_validation,
        "execute_private_validation": execute_private_validation,
        "payload_validate_ready": payload_validate_ready,
        "credential_ready": credential_ready,
        "live_orders_enabled": live_orders_enabled,
        "public_blockers": public_blockers,
        "blocker_counts": blocker_counts,
        "next_actions": _next_actions(status, blocker_counts),
        "execution_readiness": execution,
        "bybit_preflight": preflight,
        "public_dry_run_batch": batch,
        "private_validation": private_validation,
    }


def compact_lines(report: Mapping[str, Any]) -> list[str]:
    batch_summary = ((report.get("public_dry_run_batch") or {}).get("summary") or {})
    preflight = report.get("bybit_preflight") or {}
    config = preflight.get("config") or {}
    instrument = preflight.get("instrument") or {}
    signed_preview = preflight.get("signed_preview") or {}
    private_validation = report.get("private_validation") or {}
    lines = [
        "Shadow v8 Bybit pre-live checklist",
        f"Status: {report.get('status', '-')}",
        f"Symbols: {', '.join(report.get('symbols') or [])}",
        f"Primary symbol: {report.get('primary_symbol', '-')}",
        f"Payload validate-ready: {report.get('payload_validate_ready')}",
        f"Credential ready: {report.get('credential_ready')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        f"Payload ready: {batch_summary.get('payload_ready_count', 0)}/{batch_summary.get('symbols_checked', 0)}",
        f"Preflight credentials present: {config.get('credentials_present')}",
        f"Preflight instrument ok: {instrument.get('ok')}",
    ]
    if report.get("include_signed_preview"):
        lines.append(f"Signed preview ok: {signed_preview.get('ok')}")
    if report.get("include_private_validation"):
        lines.append(f"Private validation status: {private_validation.get('status', '-')}")
        lines.append(f"Private request attempted: {private_validation.get('request_attempted', '-')}")
    blockers = report.get("blocker_counts") or {}
    if blockers:
        lines.append("Top blockers:")
        lines.extend(f"- {name}: {count}" for name, count in list(blockers.items())[:10])
    else:
        lines.append("Top blockers: none")
    actions = report.get("next_actions") or []
    lines.append("Next actions: " + (", ".join(str(item) for item in actions) if actions else "none"))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a sanitized Bybit pre-live validate-only checklist.")
    parser.add_argument("--symbols", default="ETHUSDT,BTCUSDT,SOLUSDT")
    parser.add_argument("--direction", choices=("LONG", "SHORT"), default="LONG")
    parser.add_argument("--risk-pct", type=float, default=0.01)
    parser.add_argument("--account-balance", type=float, default=10_000.0)
    parser.add_argument("--base-url")
    parser.add_argument("--offline-sample", action="store_true", help="Use bundled sample instruments instead of public lookup")
    parser.add_argument("--no-signed-preview", action="store_true")
    parser.add_argument("--include-private-validation", action="store_true")
    parser.add_argument(
        "--execute-private-validation",
        action="store_true",
        help="Make a read-only signed Bybit account request. Never places orders.",
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_bybit_prelive_checklist(
        symbols=args.symbols,
        direction=args.direction,
        risk_pct=args.risk_pct,
        account_balance=args.account_balance,
        fetch_public_instrument=not args.offline_sample,
        base_url=args.base_url,
        include_signed_preview=not args.no_signed_preview,
        include_private_validation=args.include_private_validation or args.execute_private_validation,
        execute_private_validation=args.execute_private_validation,
    )
    if args.compact:
        print("\n".join(compact_lines(report)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
