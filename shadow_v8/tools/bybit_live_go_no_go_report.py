from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable, Mapping, Sequence

from shadow_v8.tools.bybit_public_dry_run_batch import parse_symbols
from shadow_v8.tools.ec2_prelive_sequence_report import build_ec2_prelive_sequence_report


def _decision_for_status(status: str) -> str:
    if status == "HALT_LIVE_UNLOCK_ALREADY_SET":
        return "NO_GO_LIVE_UNLOCK_ALREADY_SET"
    if status == "WAITING_FOR_EC2_CREDENTIALS":
        return "NO_GO_LOAD_EC2_ENV_FIRST"
    if status == "READY_FOR_READ_ONLY_PRIVATE_VALIDATION":
        return "NO_GO_RUN_READ_ONLY_PRIVATE_VALIDATION"
    if status == "PRIVATE_VALIDATION_DONE_ROTATE_DASHBOARD_TOKEN":
        return "NO_GO_ROTATE_DASHBOARD_TOKEN"
    if status == "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW":
        return "READY_FOR_OPERATOR_GO_NO_GO_REVIEW"
    return "NO_GO_INSPECT_BLOCKERS"


def _stage_for_decision(decision: str) -> str:
    return {
        "NO_GO_LIVE_UNLOCK_ALREADY_SET": "halt_live_unlock_already_set",
        "NO_GO_LOAD_EC2_ENV_FIRST": "1_load_ec2_env",
        "NO_GO_RUN_READ_ONLY_PRIVATE_VALIDATION": "2_run_read_only_private_validation",
        "NO_GO_ROTATE_DASHBOARD_TOKEN": "3_rotate_dashboard_token",
        "READY_FOR_OPERATOR_GO_NO_GO_REVIEW": "4_operator_live_unlock_review",
    }.get(decision, "blocked")


def _required_before_live(decision: str) -> list[str]:
    base = ["keep_live_orders_disabled", "keep_shadow_live_unlock_brokers_empty"]
    if decision == "NO_GO_LIVE_UNLOCK_ALREADY_SET":
        return ["clear_shadow_live_unlock_brokers", "rerun_validate_only_go_no_go_report"]
    if decision == "NO_GO_LOAD_EC2_ENV_FIRST":
        return base + ["load_ec2_env_without_printing", "rerun_go_no_go_report_on_ec2"]
    if decision == "NO_GO_RUN_READ_ONLY_PRIVATE_VALIDATION":
        return base + ["run_bybit_read_only_private_validation", "confirm_private_validation_success"]
    if decision == "NO_GO_ROTATE_DASHBOARD_TOKEN":
        return base + ["rotate_dashboard_token", "restart_dashboard_service", "rerun_final_live_unlock_review"]
    if decision == "READY_FOR_OPERATOR_GO_NO_GO_REVIEW":
        return [
            "operator_review_strategy_and_risk",
            "operator_review_dashboard_and_telegram_status",
            "operator_confirm_tiny_live_unlock_plan",
            "manual_live_unlock_change_required",
        ]
    return base + ["inspect_blockers", "rerun_ec2_prelive_sequence_report"]


def _safe_next_command(decision: str, symbols: Sequence[str]) -> str:
    symbol_text = ",".join(symbols) if symbols else "ETHUSDT,BTCUSDT"
    if decision == "NO_GO_LIVE_UNLOCK_ALREADY_SET":
        return "Clear SHADOW_LIVE_UNLOCK_BROKERS on EC2, restart services, then rerun this report."
    if decision == "NO_GO_LOAD_EC2_ENV_FIRST":
        return (
            "cd ~/shadow-v8 && set -a && source .env && set +a && "
            f"python -m shadow_v8.tools.bybit_live_go_no_go_report --symbols {symbol_text} --compact"
        )
    if decision == "NO_GO_RUN_READ_ONLY_PRIVATE_VALIDATION":
        return (
            "cd ~/shadow-v8 && "
            f"python -m shadow_v8.tools.bybit_live_go_no_go_report --symbols {symbol_text} "
            "--execute-private-validation --compact"
        )
    if decision == "NO_GO_ROTATE_DASHBOARD_TOKEN":
        return (
            "Rotate DASHBOARD_TOKEN, restart shadow-v8-dashboard, then run: "
            f"python -m shadow_v8.tools.bybit_live_go_no_go_report --symbols {symbol_text} "
            "--execute-private-validation --dashboard-token-rotated --compact"
        )
    if decision == "READY_FOR_OPERATOR_GO_NO_GO_REVIEW":
        return "Pause here for manual operator review. Do not unlock live trading from this report."
    return f"cd ~/shadow-v8 && python -m shadow_v8.tools.ec2_prelive_sequence_report --symbols {symbol_text} --compact"


def _operator_checks() -> list[str]:
    return [
        "latest_github_main_pulled_on_ec2",
        "ec2_env_loaded_without_printing",
        "read_only_private_validation_succeeded",
        "dashboard_token_rotated",
        "dashboard_and_telegram_status_match",
        "risk_and_position_sizing_confirmed",
        "manual_approval_recorded",
        "live_unlock_env_empty_until_explicit_final_change",
    ]


def _sequence_summary(sequence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": sequence.get("status"),
        "runbook_status": sequence.get("runbook_status"),
        "audit_status": sequence.get("audit_status"),
        "live_review_status": sequence.get("live_review_status"),
        "private_validation_status": sequence.get("private_validation_status"),
        "prelive_checklist_status": sequence.get("prelive_checklist_status"),
        "next_actions": sequence.get("next_actions") or [],
        "commands": sequence.get("commands") or [],
    }


def build_bybit_live_go_no_go_report(
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
    sequence = build_ec2_prelive_sequence_report(
        symbols=parsed_symbols,
        execute_private_validation=execute_private_validation,
        dashboard_token_rotated=dashboard_token_rotated,
        fetch_public_instrument=fetch_public_instrument,
        base_url=base_url,
        env=resolved_env,
        private_http_get=private_http_get,
        timestamp_ms=timestamp_ms,
    )
    sequence_status = str(sequence.get("status") or "")
    decision = _decision_for_status(sequence_status)
    hard_blockers = sorted(
        set(list(sequence.get("blockers") or []) + ["live_orders_disabled_until_operator_go_no_go"])
    )
    if decision == "READY_FOR_OPERATOR_GO_NO_GO_REVIEW":
        hard_blockers = [
            item
            for item in hard_blockers
            if item
            not in {
                "live_orders_disabled_until_manual_unlock",
                "live_orders_disabled_until_operator_go_no_go",
            }
        ]
    return {
        "ok": decision == "READY_FOR_OPERATOR_GO_NO_GO_REVIEW",
        "mode": "bybit_live_go_no_go_report_validate_only",
        "decision": decision,
        "readiness_stage": _stage_for_decision(decision),
        "sequence_status": sequence_status,
        "symbols": parsed_symbols,
        "execute_private_validation": execute_private_validation,
        "dashboard_token_rotated": dashboard_token_rotated,
        "fetch_public_instrument": fetch_public_instrument,
        "live_orders_enabled": False,
        "manual_live_unlock_required": True,
        "safe_next_command": _safe_next_command(decision, parsed_symbols),
        "required_before_live": _required_before_live(decision),
        "hard_blockers": hard_blockers,
        "operator_checks": _operator_checks(),
        "sequence": _sequence_summary(sequence),
    }


def compact_lines(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "Shadow v8 Bybit live go/no-go report",
        f"Decision: {report.get('decision', '-')}",
        f"Readiness stage: {report.get('readiness_stage', '-')}",
        f"Ready for operator review: {report.get('ok')}",
        f"Sequence status: {report.get('sequence_status', '-')}",
        f"Symbols: {', '.join(report.get('symbols') or [])}",
        f"Manual live unlock required: {report.get('manual_live_unlock_required')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        f"Safe next command: {report.get('safe_next_command', '-')}",
        "Required before live:",
    ]
    for item in report.get("required_before_live") or []:
        lines.append(f"- {item}")
    blockers = report.get("hard_blockers") or []
    lines.append("Hard blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"))
    lines.append("Operator checks:")
    for item in report.get("operator_checks") or []:
        lines.append(f"- {item}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a validate-only Bybit live go/no-go report.")
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

    report = build_bybit_live_go_no_go_report(
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
