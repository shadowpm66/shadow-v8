from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable, Mapping, Sequence

from shadow_v8.tools.bybit_live_unlock_review import build_bybit_live_unlock_review
from shadow_v8.tools.bybit_private_validation_runbook import build_bybit_private_validation_runbook
from shadow_v8.tools.bybit_public_dry_run_batch import parse_symbols
from shadow_v8.tools.ec2_prelive_validation_audit import build_ec2_prelive_validation_audit


def _sequence_status(
    *,
    audit_status: str,
    runbook_status: str,
    live_review_status: str,
    dashboard_token_rotated: bool,
    execute_private_validation: bool,
) -> str:
    if live_review_status == "HALT_LIVE_UNLOCK_ALREADY_SET":
        return "HALT_LIVE_UNLOCK_ALREADY_SET"
    if audit_status == "WAITING_FOR_EC2_CREDENTIALS" or runbook_status == "WAITING_FOR_EC2_CREDENTIALS":
        return "WAITING_FOR_EC2_CREDENTIALS"
    if not execute_private_validation:
        return "READY_FOR_READ_ONLY_PRIVATE_VALIDATION"
    if live_review_status == "BLOCKED_DASHBOARD_TOKEN_ROTATION_REQUIRED":
        return "PRIVATE_VALIDATION_DONE_ROTATE_DASHBOARD_TOKEN"
    if live_review_status == "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW" and dashboard_token_rotated:
        return "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW"
    return "BLOCKED"


def _commands(symbols: Sequence[str], *, execute_private_validation: bool, dashboard_token_rotated: bool) -> list[dict[str, str]]:
    symbol_text = ",".join(symbols) if symbols else "ETHUSDT,BTCUSDT"
    audit_flags = f"--symbols {symbol_text} --compact"
    review_flags = f"--symbols {symbol_text} --compact"
    if execute_private_validation:
        audit_flags += " --execute-private-validation"
        review_flags += " --execute-private-validation"
    if dashboard_token_rotated:
        review_flags += " --dashboard-token-rotated"
    return [
        {
            "step": "pull_latest_main",
            "command": "cd ~/shadow-v8 && git pull --ff-only",
        },
        {
            "step": "load_env_without_printing",
            "command": "cd ~/shadow-v8 && set -a && source .env && set +a",
        },
        {
            "step": "validate_only_public_and_private_preview",
            "command": f"cd ~/shadow-v8 && python -m shadow_v8.tools.bybit_prelive_checklist --symbols {symbol_text} --include-private-validation --compact",
        },
        {
            "step": "ec2_prelive_audit",
            "command": f"cd ~/shadow-v8 && python -m shadow_v8.tools.ec2_prelive_validation_audit {audit_flags}",
        },
        {
            "step": "live_unlock_review_validate_only",
            "command": f"cd ~/shadow-v8 && python -m shadow_v8.tools.bybit_live_unlock_review {review_flags}",
        },
        {
            "step": "confirm_dashboard_and_telegram_status",
            "command": "cd ~/shadow-v8 && python -m shadow_v8.tools.ec2_prelive_sequence_report --compact",
        },
    ]


def _next_actions(status: str) -> list[str]:
    actions = ["keep_live_orders_disabled"]
    if status == "WAITING_FOR_EC2_CREDENTIALS":
        actions.append("run_this_report_on_ec2_after_loading_env")
    elif status == "READY_FOR_READ_ONLY_PRIVATE_VALIDATION":
        actions.append("run_ec2_prelive_sequence_with_execute_private_validation")
    elif status == "PRIVATE_VALIDATION_DONE_ROTATE_DASHBOARD_TOKEN":
        actions.append("rotate_dashboard_token_before_final_live_review")
    elif status == "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW":
        actions.append("pause_for_manual_operator_review")
        actions.append("prepare_tiny_testnet_or_live_unlock_plan")
    elif status == "HALT_LIVE_UNLOCK_ALREADY_SET":
        actions.append("clear_shadow_live_unlock_brokers_until_final_review")
    else:
        actions.append("inspect_sequence_blockers")
    actions.append("do_not_set_shadow_live_unlock_brokers_yet")
    return actions


def build_ec2_prelive_sequence_report(
    *,
    symbols: str | Sequence[str] | None = None,
    execute_private_validation: bool = False,
    dashboard_token_rotated: bool = False,
    fetch_public_instrument: bool = False,
    base_url: str | None = None,
    env: Mapping[str, str] | None = None,
    private_http_get: Callable[..., Any] | None = None,
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    resolved_env = env if env is not None else os.environ
    parsed_symbols = parse_symbols(symbols)
    runbook = build_bybit_private_validation_runbook(
        symbols=parsed_symbols,
        execute_private_validation=execute_private_validation,
        fetch_public_instrument=fetch_public_instrument,
        base_url=base_url,
        env=resolved_env,
        private_http_get=private_http_get,
        timestamp_ms=timestamp_ms,
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
    live_review = build_bybit_live_unlock_review(
        symbols=parsed_symbols,
        execute_private_validation=execute_private_validation,
        fetch_public_instrument=fetch_public_instrument,
        dashboard_token_rotated=dashboard_token_rotated,
        base_url=base_url,
        env=resolved_env,
        private_http_get=private_http_get,
        timestamp_ms=timestamp_ms,
    )
    status = _sequence_status(
        audit_status=str(audit.get("status") or ""),
        runbook_status=str(runbook.get("status") or ""),
        live_review_status=str(live_review.get("status") or ""),
        dashboard_token_rotated=dashboard_token_rotated,
        execute_private_validation=execute_private_validation,
    )
    blockers = sorted(
        set(
            list(runbook.get("blockers") or [])
            + list(audit.get("blockers") or [])
            + list(live_review.get("blockers") or [])
            + ["live_orders_disabled_until_manual_unlock"]
        )
    )
    if status == "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW":
        blockers = [
            item
            for item in blockers
            if item
            not in {
                "dashboard_token_rotation_required_before_live",
                "ec2_private_validation_not_complete",
                "live_orders_disabled_validate_only",
            }
        ]
    return {
        "ok": status in {
            "READY_FOR_READ_ONLY_PRIVATE_VALIDATION",
            "PRIVATE_VALIDATION_DONE_ROTATE_DASHBOARD_TOKEN",
            "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW",
        },
        "mode": "ec2_prelive_sequence_report_validate_only",
        "status": status,
        "symbols": parsed_symbols,
        "execute_private_validation": execute_private_validation,
        "dashboard_token_rotated": dashboard_token_rotated,
        "fetch_public_instrument": fetch_public_instrument,
        "live_orders_enabled": False,
        "runbook_status": runbook.get("status"),
        "audit_status": audit.get("status"),
        "live_review_status": live_review.get("status"),
        "private_validation_status": audit.get("private_validation_status"),
        "prelive_checklist_status": audit.get("prelive_checklist_status"),
        "manual_live_unlock_required": True,
        "commands": _commands(
            parsed_symbols,
            execute_private_validation=execute_private_validation,
            dashboard_token_rotated=dashboard_token_rotated,
        ),
        "blockers": blockers,
        "next_actions": _next_actions(status),
        "runbook": runbook,
        "audit": audit,
        "live_review": live_review,
    }


def compact_lines(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "Shadow v8 EC2 pre-live sequence report",
        f"Status: {report.get('status', '-')}",
        f"Symbols: {', '.join(report.get('symbols') or [])}",
        f"Runbook status: {report.get('runbook_status', '-')}",
        f"Audit status: {report.get('audit_status', '-')}",
        f"Live review status: {report.get('live_review_status', '-')}",
        f"Private validation status: {report.get('private_validation_status', '-')}",
        f"Pre-live checklist status: {report.get('prelive_checklist_status', '-')}",
        f"Dashboard token rotated: {report.get('dashboard_token_rotated')}",
        f"Manual live unlock required: {report.get('manual_live_unlock_required')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        "Commands:",
    ]
    for item in report.get("commands") or []:
        lines.append(f"- {item.get('step')}: {item.get('command')}")
    blockers = report.get("blockers") or []
    lines.append("Blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"))
    lines.append("Next actions: " + ", ".join(str(item) for item in report.get("next_actions") or []))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a validate-only EC2 pre-live sequence report.")
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
        help="Confirm dashboard token rotation for final manual live-unlock review.",
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_ec2_prelive_sequence_report(
        symbols=args.symbols,
        execute_private_validation=args.execute_private_validation,
        dashboard_token_rotated=args.dashboard_token_rotated,
        fetch_public_instrument=args.fetch_public_instrument,
        base_url=args.base_url,
    )
    if args.compact:
        print("\n".join(compact_lines(report)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
