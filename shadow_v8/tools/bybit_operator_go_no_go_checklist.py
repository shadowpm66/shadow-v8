from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable, Mapping, Sequence

from shadow_v8.tools.bybit_live_go_no_go_report import build_bybit_live_go_no_go_report
from shadow_v8.tools.bybit_live_unlock_review import build_bybit_live_unlock_review
from shadow_v8.tools.bybit_public_dry_run_batch import parse_symbols
from shadow_v8.tools.ec2_prelive_rehearsal import build_ec2_prelive_rehearsal


def _unique(items: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _status(go_no_go_decision: str, rehearsal_status: str, live_review_status: str) -> str:
    if go_no_go_decision == "NO_GO_LIVE_UNLOCK_ALREADY_SET":
        return "HALT_LIVE_UNLOCK_ALREADY_SET"
    if go_no_go_decision == "NO_GO_LOAD_EC2_ENV_FIRST":
        return "WAITING_FOR_EC2_ENV"
    if go_no_go_decision == "NO_GO_RUN_READ_ONLY_PRIVATE_VALIDATION":
        return "WAITING_FOR_READ_ONLY_PRIVATE_VALIDATION"
    if go_no_go_decision == "NO_GO_ROTATE_DASHBOARD_TOKEN":
        return "WAITING_FOR_DASHBOARD_TOKEN_ROTATION"
    if (
        go_no_go_decision == "READY_FOR_OPERATOR_GO_NO_GO_REVIEW"
        and rehearsal_status == "REHEARSAL_READY_FOR_OPERATOR_REVIEW"
        and live_review_status == "READY_FOR_FINAL_MANUAL_LIVE_UNLOCK_REVIEW"
    ):
        return "READY_FOR_FINAL_OPERATOR_CHECKLIST"
    return "BLOCKED_INSPECT_PRELIVE_REPORTS"


def _operator_confirmations(status: str) -> list[str]:
    base = [
        "confirm_latest_github_main_is_running_on_ec2",
        "confirm_live_orders_are_still_disabled",
        "confirm_shadow_live_unlock_brokers_is_empty",
    ]
    if status == "READY_FOR_FINAL_OPERATOR_CHECKLIST":
        return base + [
            "confirm_read_only_private_validation_succeeded",
            "confirm_dashboard_token_rotated",
            "confirm_dashboard_and_telegram_status_match",
            "confirm_strategy_risk_and_position_size_are_approved",
            "confirm_tiny_live_unlock_plan_is_written_down",
            "record_manual_operator_go_no_go_decision",
        ]
    if status == "HALT_LIVE_UNLOCK_ALREADY_SET":
        return ["clear_shadow_live_unlock_brokers", "restart_services", "rerun_operator_checklist"]
    if status == "WAITING_FOR_EC2_ENV":
        return base + ["load_ec2_env_without_printing", "rerun_operator_checklist"]
    if status == "WAITING_FOR_READ_ONLY_PRIVATE_VALIDATION":
        return base + ["run_read_only_private_validation", "rerun_operator_checklist"]
    if status == "WAITING_FOR_DASHBOARD_TOKEN_ROTATION":
        return base + ["rotate_dashboard_token", "restart_dashboard_service", "rerun_operator_checklist"]
    return base + ["inspect_blockers", "rerun_ec2_prelive_rehearsal"]


def _next_command(status: str, symbols: Sequence[str]) -> str:
    symbol_text = ",".join(symbols) if symbols else "ETHUSDT,BTCUSDT"
    if status == "HALT_LIVE_UNLOCK_ALREADY_SET":
        return "Clear SHADOW_LIVE_UNLOCK_BROKERS, restart services, then rerun this checklist."
    if status == "WAITING_FOR_EC2_ENV":
        return (
            "cd ~/shadow-v8 && set -a && source .env && set +a && "
            f"python -m shadow_v8.tools.bybit_operator_go_no_go_checklist --symbols {symbol_text} --compact"
        )
    if status == "WAITING_FOR_READ_ONLY_PRIVATE_VALIDATION":
        return (
            "cd ~/shadow-v8 && "
            f"python -m shadow_v8.tools.bybit_operator_go_no_go_checklist --symbols {symbol_text} "
            "--execute-private-validation --compact"
        )
    if status == "WAITING_FOR_DASHBOARD_TOKEN_ROTATION":
        return (
            "Rotate DASHBOARD_TOKEN, restart shadow-v8-dashboard, then run: "
            f"python -m shadow_v8.tools.bybit_operator_go_no_go_checklist --symbols {symbol_text} "
            "--execute-private-validation --dashboard-token-rotated --compact"
        )
    if status == "READY_FOR_FINAL_OPERATOR_CHECKLIST":
        return "Stop here for human go/no-go approval. This checklist never enables live orders."
    return f"cd ~/shadow-v8 && python -m shadow_v8.tools.ec2_prelive_rehearsal --symbols {symbol_text} --compact"


def _summary(
    go_no_go: Mapping[str, Any],
    rehearsal: Mapping[str, Any],
    live_review: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "go_no_go_decision": go_no_go.get("decision"),
        "rehearsal_status": rehearsal.get("rehearsal_status"),
        "live_review_status": live_review.get("status"),
        "private_validation_status": live_review.get("private_validation_status"),
        "dashboard_token_rotated": live_review.get("dashboard_token_rotated"),
        "private_validation_complete": live_review.get("private_validation_complete"),
    }


def build_bybit_operator_go_no_go_checklist(
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
    go_no_go = build_bybit_live_go_no_go_report(
        symbols=parsed_symbols,
        execute_private_validation=execute_private_validation,
        dashboard_token_rotated=dashboard_token_rotated,
        fetch_public_instrument=fetch_public_instrument,
        base_url=base_url,
        env=resolved_env,
        private_http_get=private_http_get,
        timestamp_ms=timestamp_ms,
    )
    rehearsal = build_ec2_prelive_rehearsal(
        symbols=parsed_symbols,
        execute_private_validation=execute_private_validation,
        dashboard_token_rotated=dashboard_token_rotated,
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
    status = _status(
        str(go_no_go.get("decision") or ""),
        str(rehearsal.get("rehearsal_status") or ""),
        str(live_review.get("status") or ""),
    )
    blockers = _unique(
        list(go_no_go.get("hard_blockers") or [])
        + list((rehearsal.get("go_no_go") or {}).get("hard_blockers") or [])
        + list(live_review.get("blockers") or [])
    )
    if status == "READY_FOR_FINAL_OPERATOR_CHECKLIST":
        blockers = [
            item
            for item in blockers
            if item
            not in {
                "live_orders_disabled_until_manual_unlock",
                "live_orders_disabled_until_operator_go_no_go",
                "live_orders_disabled_validate_only",
            }
        ]
    return {
        "ok": status == "READY_FOR_FINAL_OPERATOR_CHECKLIST",
        "mode": "bybit_operator_go_no_go_checklist_validate_only",
        "status": status,
        "symbols": parsed_symbols,
        "execute_private_validation": execute_private_validation,
        "dashboard_token_rotated": dashboard_token_rotated,
        "fetch_public_instrument": fetch_public_instrument,
        "live_orders_enabled": False,
        "safe_to_enable_live": False,
        "manual_operator_approval_required": True,
        "manual_live_unlock_required": True,
        "next_command": _next_command(status, parsed_symbols),
        "operator_confirmations": _operator_confirmations(status),
        "blockers": blockers,
        "report_summary": _summary(go_no_go, rehearsal, live_review),
    }


def compact_lines(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "Shadow v8 Bybit operator go/no-go checklist",
        f"Checklist status: {report.get('status', '-')}",
        f"Ready for final operator checklist: {report.get('ok')}",
        f"Symbols: {', '.join(report.get('symbols') or [])}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        f"Safe to enable live from this tool: {report.get('safe_to_enable_live')}",
        f"Manual operator approval required: {report.get('manual_operator_approval_required')}",
        f"Manual live unlock required: {report.get('manual_live_unlock_required')}",
        f"Next command: {report.get('next_command', '-')}",
    ]
    summary = report.get("report_summary") or {}
    lines.append("Report summary:")
    for key in (
        "go_no_go_decision",
        "rehearsal_status",
        "live_review_status",
        "private_validation_status",
        "dashboard_token_rotated",
        "private_validation_complete",
    ):
        lines.append(f"- {key}: {summary.get(key, '-')}")
    lines.append("Operator confirmations:")
    for item in report.get("operator_confirmations") or []:
        lines.append(f"- {item}")
    blockers = report.get("blockers") or []
    lines.append("Blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a validate-only Bybit final operator go/no-go checklist.")
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

    report = build_bybit_operator_go_no_go_checklist(
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
