from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable, Mapping, Sequence

from shadow_v8.tools.bybit_live_go_no_go_report import build_bybit_live_go_no_go_report
from shadow_v8.tools.bybit_public_dry_run_batch import parse_symbols


def _rehearsal_status(decision: str) -> str:
    if decision == "NO_GO_LIVE_UNLOCK_ALREADY_SET":
        return "REHEARSAL_HALTED_LIVE_UNLOCK_ALREADY_SET"
    if decision == "NO_GO_LOAD_EC2_ENV_FIRST":
        return "REHEARSAL_WAITING_FOR_EC2_ENV"
    if decision == "NO_GO_RUN_READ_ONLY_PRIVATE_VALIDATION":
        return "REHEARSAL_WAITING_FOR_PRIVATE_VALIDATION"
    if decision == "NO_GO_ROTATE_DASHBOARD_TOKEN":
        return "REHEARSAL_WAITING_FOR_DASHBOARD_TOKEN_ROTATION"
    if decision == "READY_FOR_OPERATOR_GO_NO_GO_REVIEW":
        return "REHEARSAL_READY_FOR_OPERATOR_REVIEW"
    return "REHEARSAL_BLOCKED"


def _step(name: str, status: str, detail: str) -> dict[str, Any]:
    return {
        "step": name,
        "status": status,
        "passed": status == "passed",
        "detail": detail,
    }


def _build_steps(report: Mapping[str, Any], dashboard_token_rotated: bool) -> list[dict[str, Any]]:
    decision = str(report.get("decision") or "")
    steps = [
        _step(
            "pull_latest_github_main_on_ec2",
            "operator_confirm_required",
            "Run git pull --ff-only on EC2 before trusting the rehearsal.",
        )
    ]
    if decision == "NO_GO_LIVE_UNLOCK_ALREADY_SET":
        steps.append(
            _step(
                "live_unlock_env_guard",
                "blocked",
                "SHADOW_LIVE_UNLOCK_BROKERS is already set. Clear it before pre-live rehearsal.",
            )
        )
        return steps

    env_loaded = decision != "NO_GO_LOAD_EC2_ENV_FIRST"
    steps.append(
        _step(
            "load_ec2_env_without_printing",
            "passed" if env_loaded else "blocked",
            "EC2 credential placeholders are present." if env_loaded else "Load .env with set -a; source .env; set +a.",
        )
    )

    private_done = decision not in {"NO_GO_LOAD_EC2_ENV_FIRST", "NO_GO_RUN_READ_ONLY_PRIVATE_VALIDATION"}
    steps.append(
        _step(
            "read_only_private_validation",
            "passed" if private_done else "blocked",
            (
                "Read-only private validation is complete."
                if private_done
                else "Run the signed read-only Bybit validation. This does not place orders."
            ),
        )
    )

    token_done = dashboard_token_rotated and decision not in {
        "NO_GO_LOAD_EC2_ENV_FIRST",
        "NO_GO_RUN_READ_ONLY_PRIVATE_VALIDATION",
        "NO_GO_ROTATE_DASHBOARD_TOKEN",
    }
    steps.append(
        _step(
            "dashboard_token_rotation",
            "passed" if token_done else "blocked",
            (
                "Dashboard token rotation has been confirmed."
                if token_done
                else "Rotate DASHBOARD_TOKEN and restart the dashboard before final review."
            ),
        )
    )

    operator_ready = decision == "READY_FOR_OPERATOR_GO_NO_GO_REVIEW"
    steps.append(
        _step(
            "operator_go_no_go_review",
            "operator_confirm_required" if operator_ready else "blocked",
            (
                "Review dashboard, Telegram status, risk sizing, and tiny live-unlock plan manually."
                if operator_ready
                else "Earlier rehearsal steps must pass before operator review."
            ),
        )
    )
    return steps


def _operator_must_do(report: Mapping[str, Any]) -> list[str]:
    decision = str(report.get("decision") or "")
    if decision == "READY_FOR_OPERATOR_GO_NO_GO_REVIEW":
        return [
            "confirm_latest_main_is_running_on_ec2",
            "compare_dashboard_and_telegram_readiness_status",
            "review_risk_and_position_sizing_limits",
            "write_down_manual_go_no_go_decision",
            "keep_live_orders_disabled_until_explicit_manual_unlock",
        ]
    return list(report.get("required_before_live") or [])


def _go_no_go_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision": report.get("decision"),
        "readiness_stage": report.get("readiness_stage"),
        "sequence_status": report.get("sequence_status"),
        "safe_next_command": report.get("safe_next_command"),
        "required_before_live": report.get("required_before_live") or [],
        "hard_blockers": report.get("hard_blockers") or [],
    }


def build_ec2_prelive_rehearsal(
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
    status = _rehearsal_status(str(go_no_go.get("decision") or ""))
    return {
        "ok": status == "REHEARSAL_READY_FOR_OPERATOR_REVIEW",
        "mode": "ec2_prelive_rehearsal_validate_only",
        "rehearsal_status": status,
        "symbols": parsed_symbols,
        "execute_private_validation": execute_private_validation,
        "dashboard_token_rotated": dashboard_token_rotated,
        "fetch_public_instrument": fetch_public_instrument,
        "live_orders_enabled": False,
        "safe_to_enable_live": False,
        "manual_live_unlock_required": True,
        "next_command": go_no_go.get("safe_next_command"),
        "operator_must_do": _operator_must_do(go_no_go),
        "rehearsal_steps": _build_steps(go_no_go, dashboard_token_rotated),
        "go_no_go": _go_no_go_summary(go_no_go),
    }


def compact_lines(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "Shadow v8 EC2 pre-live rehearsal",
        f"Rehearsal status: {report.get('rehearsal_status', '-')}",
        f"Ready for operator review: {report.get('ok')}",
        f"Symbols: {', '.join(report.get('symbols') or [])}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        f"Safe to enable live from this tool: {report.get('safe_to_enable_live')}",
        f"Manual live unlock required: {report.get('manual_live_unlock_required')}",
        f"Next command: {report.get('next_command', '-')}",
        "Rehearsal steps:",
    ]
    for step in report.get("rehearsal_steps") or []:
        lines.append(f"- {step.get('step')}: {step.get('status')} - {step.get('detail')}")
    lines.append("Operator must do:")
    for item in report.get("operator_must_do") or []:
        lines.append(f"- {item}")
    go_no_go = report.get("go_no_go") or {}
    blockers = go_no_go.get("hard_blockers") or []
    lines.append("Hard blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a validate-only EC2 Bybit pre-live rehearsal report.")
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

    report = build_ec2_prelive_rehearsal(
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
