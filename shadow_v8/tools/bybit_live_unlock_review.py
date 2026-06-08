from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable, Mapping, Sequence

from shadow_v8.tools.bybit_public_dry_run_batch import parse_symbols
from shadow_v8.tools.ec2_prelive_validation_audit import build_ec2_prelive_validation_audit


def _env_flag(env: Mapping[str, str], key: str) -> bool:
    return str(env.get(key, "") or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _status(
    *,
    audit_status: str,
    live_unlock_brokers: Sequence[str],
    dashboard_token_rotated: bool,
    private_validation_complete: bool,
) -> str:
    if live_unlock_brokers:
        return "HALT_LIVE_UNLOCK_ALREADY_SET"
    if not private_validation_complete:
        if audit_status == "WAITING_FOR_EC2_CREDENTIALS":
            return "WAITING_FOR_EC2_CREDENTIALS"
        return "WAITING_FOR_EC2_PRIVATE_VALIDATION"
    if not dashboard_token_rotated:
        return "BLOCKED_DASHBOARD_TOKEN_ROTATION_REQUIRED"
    return "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW"


def _next_actions(status: str) -> list[str]:
    actions = ["keep_live_orders_disabled"]
    if status == "HALT_LIVE_UNLOCK_ALREADY_SET":
        actions.append("clear_shadow_live_unlock_brokers_until_final_review")
    elif status == "WAITING_FOR_EC2_CREDENTIALS":
        actions.append("load_ec2_env_without_printing")
    elif status == "WAITING_FOR_EC2_PRIVATE_VALIDATION":
        actions.append("run_ec2_prelive_audit_with_execute_private_validation")
    elif status == "BLOCKED_DASHBOARD_TOKEN_ROTATION_REQUIRED":
        actions.append("rotate_dashboard_token_before_live_unlock_review")
    elif status == "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW":
        actions.append("prepare_final_manual_live_unlock_change_request")
        actions.append("document_operator_approval_before_any_live_order")
    else:
        actions.append("inspect_live_unlock_review_blockers")
    actions.append("do_not_set_shadow_live_unlock_brokers_yet")
    return actions


def _blockers(
    *,
    status: str,
    audit_blockers: Sequence[str],
    dashboard_token_rotated: bool,
    private_validation_complete: bool,
) -> list[str]:
    blockers = set(str(item) for item in audit_blockers)
    blockers.add("live_orders_disabled_until_manual_unlock")
    if status == "HALT_LIVE_UNLOCK_ALREADY_SET":
        blockers.add("live_unlock_already_set")
    if not private_validation_complete:
        blockers.add("ec2_private_validation_not_complete")
    if not dashboard_token_rotated:
        blockers.add("dashboard_token_rotation_required_before_live")
    if status == "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW":
        blockers.discard("dashboard_token_rotation_required_before_live")
        blockers.discard("live_orders_disabled_validate_only")
    return sorted(blockers)


def build_bybit_live_unlock_review(
    *,
    symbols: str | Sequence[str] | None = None,
    execute_private_validation: bool = False,
    fetch_public_instrument: bool = False,
    dashboard_token_rotated: bool | None = None,
    base_url: str | None = None,
    env: Mapping[str, str] | None = None,
    private_http_get: Callable[..., Any] | None = None,
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    resolved_env = env if env is not None else os.environ
    parsed_symbols = parse_symbols(symbols)
    token_rotated = (
        _env_flag(resolved_env, "SHADOW_DASHBOARD_TOKEN_ROTATED")
        if dashboard_token_rotated is None
        else dashboard_token_rotated
    )
    audit = build_ec2_prelive_validation_audit(
        symbols=parsed_symbols,
        execute_private_validation=execute_private_validation,
        fetch_public_instrument=fetch_public_instrument,
        base_url=base_url,
        env=resolved_env,
        private_http_get=private_http_get,
        timestamp_ms=timestamp_ms,
    )
    audit_status = str(audit.get("status") or "")
    live_unlock_brokers = list(audit.get("live_unlock_brokers") or [])
    private_validation_complete = audit_status == "EC2_PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY"
    status = _status(
        audit_status=audit_status,
        live_unlock_brokers=live_unlock_brokers,
        dashboard_token_rotated=token_rotated,
        private_validation_complete=private_validation_complete,
    )
    blockers = _blockers(
        status=status,
        audit_blockers=audit.get("blockers") or [],
        dashboard_token_rotated=token_rotated,
        private_validation_complete=private_validation_complete,
    )
    return {
        "ok": status == "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW",
        "mode": "bybit_live_unlock_review_validate_only",
        "status": status,
        "symbols": parsed_symbols,
        "execute_private_validation": execute_private_validation,
        "fetch_public_instrument": fetch_public_instrument,
        "live_orders_enabled": False,
        "manual_live_unlock_required": True,
        "dashboard_token_rotated": token_rotated,
        "private_validation_complete": private_validation_complete,
        "audit_status": audit_status,
        "private_validation_status": audit.get("private_validation_status"),
        "prelive_checklist_status": audit.get("prelive_checklist_status"),
        "live_unlock_brokers": live_unlock_brokers,
        "blockers": blockers,
        "next_actions": _next_actions(status),
        "audit": audit,
    }


def compact_lines(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "Shadow v8 Bybit live unlock review",
        f"Status: {report.get('status', '-')}",
        f"Symbols: {', '.join(report.get('symbols') or [])}",
        f"Audit status: {report.get('audit_status', '-')}",
        f"Private validation status: {report.get('private_validation_status', '-')}",
        f"Pre-live checklist status: {report.get('prelive_checklist_status', '-')}",
        f"Private validation complete: {report.get('private_validation_complete')}",
        f"Dashboard token rotated: {report.get('dashboard_token_rotated')}",
        f"Manual live unlock required: {report.get('manual_live_unlock_required')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        "Live unlock brokers: " + (", ".join(str(item) for item in report.get("live_unlock_brokers") or []) or "none"),
        "Blockers: " + (", ".join(str(item) for item in report.get("blockers") or []) or "none"),
        "Next actions: " + (", ".join(str(item) for item in report.get("next_actions") or []) or "none"),
    ]
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Review whether Bybit is ready for a final manual live-unlock decision.")
    parser.add_argument("--symbols", default="ETHUSDT,BTCUSDT")
    parser.add_argument("--base-url")
    parser.add_argument("--fetch-public-instrument", action="store_true")
    parser.add_argument(
        "--execute-private-validation",
        action="store_true",
        help="Run the read-only private validation probe. Never places orders.",
    )
    parser.add_argument(
        "--dashboard-token-rotated",
        action="store_true",
        help="Confirm the exposed dashboard token has been rotated before final live-unlock review.",
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_bybit_live_unlock_review(
        symbols=args.symbols,
        execute_private_validation=args.execute_private_validation,
        fetch_public_instrument=args.fetch_public_instrument,
        dashboard_token_rotated=args.dashboard_token_rotated,
        base_url=args.base_url,
    )
    if args.compact:
        print("\n".join(compact_lines(report)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
