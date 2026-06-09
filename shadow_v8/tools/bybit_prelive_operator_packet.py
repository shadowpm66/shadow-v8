from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable, Mapping, Sequence

from shadow_v8.tools.bybit_live_go_no_go_report import build_bybit_live_go_no_go_report
from shadow_v8.tools.bybit_operator_go_no_go_checklist import build_bybit_operator_go_no_go_checklist
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


def _packet_status(checklist_status: str) -> str:
    if checklist_status == "READY_FOR_FINAL_OPERATOR_CHECKLIST":
        return "PACKET_READY_FOR_FINAL_OPERATOR_REVIEW"
    if checklist_status == "HALT_LIVE_UNLOCK_ALREADY_SET":
        return "PACKET_HALTED_LIVE_UNLOCK_ALREADY_SET"
    if checklist_status == "WAITING_FOR_EC2_ENV":
        return "PACKET_WAITING_FOR_EC2_ENV"
    if checklist_status == "WAITING_FOR_READ_ONLY_PRIVATE_VALIDATION":
        return "PACKET_WAITING_FOR_READ_ONLY_PRIVATE_VALIDATION"
    if checklist_status == "WAITING_FOR_DASHBOARD_TOKEN_ROTATION":
        return "PACKET_WAITING_FOR_DASHBOARD_TOKEN_ROTATION"
    return "PACKET_BLOCKED_INSPECT_PRELIVE_REPORTS"


def _collect_blockers(
    checklist: Mapping[str, Any],
    go_no_go: Mapping[str, Any],
    rehearsal: Mapping[str, Any],
    packet_status: str,
) -> list[str]:
    blockers = _unique(
        list(checklist.get("blockers") or [])
        + list(go_no_go.get("hard_blockers") or [])
        + list((rehearsal.get("go_no_go") or {}).get("hard_blockers") or [])
    )
    if packet_status == "PACKET_READY_FOR_FINAL_OPERATOR_REVIEW":
        blockers = [
            item
            for item in blockers
            if item
            not in {
                "live_orders_disabled_validate_only",
                "live_orders_disabled_until_manual_unlock",
                "live_orders_disabled_until_operator_go_no_go",
            }
        ]
    return blockers


def _readiness_summary(
    checklist: Mapping[str, Any],
    go_no_go: Mapping[str, Any],
    rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    checklist_summary = checklist.get("report_summary") or {}
    return {
        "checklist_status": checklist.get("status"),
        "go_no_go_decision": go_no_go.get("decision"),
        "go_no_go_stage": go_no_go.get("readiness_stage"),
        "rehearsal_status": rehearsal.get("rehearsal_status"),
        "sequence_status": go_no_go.get("sequence_status"),
        "private_validation_status": checklist_summary.get("private_validation_status"),
        "private_validation_complete": checklist_summary.get("private_validation_complete"),
        "dashboard_token_rotated": checklist_summary.get("dashboard_token_rotated"),
    }


def _report_summaries(
    checklist: Mapping[str, Any],
    go_no_go: Mapping[str, Any],
    rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "operator_checklist": {
            "ok": checklist.get("ok"),
            "status": checklist.get("status"),
            "next_command": checklist.get("next_command"),
            "confirmations": checklist.get("operator_confirmations") or [],
        },
        "go_no_go_report": {
            "ok": go_no_go.get("ok"),
            "decision": go_no_go.get("decision"),
            "readiness_stage": go_no_go.get("readiness_stage"),
            "safe_next_command": go_no_go.get("safe_next_command"),
            "required_before_live": go_no_go.get("required_before_live") or [],
        },
        "ec2_rehearsal": {
            "ok": rehearsal.get("ok"),
            "rehearsal_status": rehearsal.get("rehearsal_status"),
            "next_command": rehearsal.get("next_command"),
            "operator_must_do": rehearsal.get("operator_must_do") or [],
        },
    }


def build_bybit_prelive_operator_packet(
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
    checklist = build_bybit_operator_go_no_go_checklist(
        symbols=parsed_symbols,
        execute_private_validation=execute_private_validation,
        dashboard_token_rotated=dashboard_token_rotated,
        fetch_public_instrument=fetch_public_instrument,
        base_url=base_url,
        env=resolved_env,
        private_http_get=private_http_get,
        timestamp_ms=timestamp_ms,
    )
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
    status = _packet_status(str(checklist.get("status") or ""))
    return {
        "ok": status == "PACKET_READY_FOR_FINAL_OPERATOR_REVIEW",
        "mode": "bybit_prelive_operator_packet_validate_only",
        "status": status,
        "symbols": parsed_symbols,
        "execute_private_validation": execute_private_validation,
        "dashboard_token_rotated": dashboard_token_rotated,
        "fetch_public_instrument": fetch_public_instrument,
        "live_orders_enabled": False,
        "safe_to_enable_live": False,
        "manual_operator_approval_required": True,
        "manual_live_unlock_required": True,
        "operator_packet_sections": [
            "operator_checklist",
            "go_no_go_report",
            "ec2_rehearsal",
            "manual_confirmations",
            "blockers",
            "next_actions",
        ],
        "next_command": checklist.get("next_command") or go_no_go.get("safe_next_command") or rehearsal.get("next_command"),
        "readiness": _readiness_summary(checklist, go_no_go, rehearsal),
        "manual_confirmations": checklist.get("operator_confirmations") or [],
        "blockers": _collect_blockers(checklist, go_no_go, rehearsal, status),
        "reports": _report_summaries(checklist, go_no_go, rehearsal),
    }


def compact_lines(packet: Mapping[str, Any]) -> list[str]:
    lines = [
        "Shadow v8 Bybit pre-live operator packet",
        f"Packet status: {packet.get('status', '-')}",
        f"Ready for final operator review: {packet.get('ok')}",
        f"Symbols: {', '.join(packet.get('symbols') or [])}",
        f"Live orders enabled: {packet.get('live_orders_enabled')}",
        f"Safe to enable live from this tool: {packet.get('safe_to_enable_live')}",
        f"Manual operator approval required: {packet.get('manual_operator_approval_required')}",
        f"Manual live unlock required: {packet.get('manual_live_unlock_required')}",
    ]
    readiness = packet.get("readiness") or {}
    lines.append("Readiness:")
    for key in (
        "checklist_status",
        "go_no_go_decision",
        "go_no_go_stage",
        "rehearsal_status",
        "sequence_status",
        "private_validation_status",
        "private_validation_complete",
        "dashboard_token_rotated",
    ):
        lines.append(f"- {key}: {readiness.get(key, '-')}")
    lines.append(f"Next command: {packet.get('next_command', '-')}")
    lines.append("Manual confirmations:")
    for item in packet.get("manual_confirmations") or []:
        lines.append(f"- {item}")
    blockers = packet.get("blockers") or []
    lines.append("Blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a validate-only Bybit pre-live operator packet.")
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

    packet = build_bybit_prelive_operator_packet(
        symbols=args.symbols,
        execute_private_validation=args.execute_private_validation,
        dashboard_token_rotated=args.dashboard_token_rotated,
        fetch_public_instrument=args.fetch_public_instrument,
        base_url=args.base_url,
    )
    if args.compact:
        print("\n".join(compact_lines(packet)))
    else:
        print(json.dumps(packet, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
