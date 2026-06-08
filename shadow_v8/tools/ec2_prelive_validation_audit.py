from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable, Mapping, Sequence

from shadow_v8.tools.bybit_private_validation_runbook import build_bybit_private_validation_runbook
from shadow_v8.tools.bybit_public_dry_run_batch import parse_symbols


ENV_KEYS = (
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "DASHBOARD_TOKEN",
    "SHADOW_EXECUTION_MODE",
    "SHADOW_LIVE_UNLOCK_BROKERS",
)


def _env_presence(env: Mapping[str, str]) -> dict[str, bool]:
    return {key: bool(str(env.get(key, "")).strip()) for key in ENV_KEYS}


def _live_unlock_brokers(env: Mapping[str, str]) -> list[str]:
    raw = str(env.get("SHADOW_LIVE_UNLOCK_BROKERS", "") or "")
    return sorted({item.strip().lower() for item in raw.split(",") if item.strip()})


def _ec2_commands(
    symbols: Sequence[str],
    *,
    execute_private_validation: bool,
    fetch_public_instrument: bool,
) -> list[dict[str, str]]:
    symbol_text = ",".join(symbols) if symbols else "ETHUSDT,BTCUSDT"
    audit_flags = f"--symbols {symbol_text} --compact"
    runbook_flags = f"--symbols {symbol_text} --compact"
    if fetch_public_instrument:
        audit_flags += " --fetch-public-instrument"
        runbook_flags += " --fetch-public-instrument"
    if execute_private_validation:
        audit_flags += " --execute-private-validation"
        runbook_flags += " --execute-private-validation"
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
            "step": "ec2_prelive_audit",
            "command": f"cd ~/shadow-v8 && python -m shadow_v8.tools.ec2_prelive_validation_audit {audit_flags}",
        },
        {
            "step": "private_validation_runbook",
            "command": f"cd ~/shadow-v8 && python -m shadow_v8.tools.bybit_private_validation_runbook {runbook_flags}",
        },
        {
            "step": "engine_service_status",
            "command": "sudo systemctl status shadow-v8-engine --no-pager",
        },
        {
            "step": "dashboard_service_status",
            "command": "sudo systemctl status shadow-v8-dashboard --no-pager",
        },
    ]


def _status(
    *,
    runbook_status: str,
    credentials_present: bool,
    live_unlock_brokers: Sequence[str],
    execute_private_validation: bool,
) -> str:
    if live_unlock_brokers:
        return "HALT_LIVE_UNLOCK_ALREADY_SET"
    if not credentials_present or runbook_status == "WAITING_FOR_EC2_CREDENTIALS":
        return "WAITING_FOR_EC2_CREDENTIALS"
    if execute_private_validation and runbook_status == "PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY":
        return "EC2_PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY"
    if runbook_status == "READY_FOR_READ_ONLY_PRIVATE_VALIDATION":
        return "READY_FOR_EC2_READ_ONLY_PRIVATE_VALIDATION"
    return "BLOCKED"


def _security_tasks(env: Mapping[str, str]) -> list[dict[str, Any]]:
    dashboard_token_present = bool(str(env.get("DASHBOARD_TOKEN", "")).strip())
    return [
        {
            "name": "rotate_dashboard_token_before_live",
            "required_before_live": True,
            "status": "rotate_required" if dashboard_token_present else "set_new_token_required",
            "prints_secret": False,
        },
        {
            "name": "keep_env_private",
            "required_before_live": True,
            "status": "required",
            "prints_secret": False,
        },
    ]


def _next_actions(status: str) -> list[str]:
    actions = ["keep_live_orders_disabled", "rotate_dashboard_token_before_live"]
    if status == "HALT_LIVE_UNLOCK_ALREADY_SET":
        actions.append("clear_shadow_live_unlock_brokers_until_final_review")
    elif status == "WAITING_FOR_EC2_CREDENTIALS":
        actions.append("load_ec2_env_without_printing")
    elif status == "READY_FOR_EC2_READ_ONLY_PRIVATE_VALIDATION":
        actions.append("run_read_only_private_validation_on_ec2")
    elif status == "EC2_PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY":
        actions.append("review_private_validation_then_prepare_live_unlock_decision")
    else:
        actions.append("inspect_ec2_audit_blockers")
    actions.append("do_not_place_live_orders")
    return actions


def build_ec2_prelive_validation_audit(
    *,
    symbols: str | Sequence[str] | None = None,
    execute_private_validation: bool = False,
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
    env_presence = _env_presence(resolved_env)
    unlock_brokers = _live_unlock_brokers(resolved_env)
    status = _status(
        runbook_status=str(runbook.get("status")),
        credentials_present=bool(runbook.get("credentials_present")),
        live_unlock_brokers=unlock_brokers,
        execute_private_validation=execute_private_validation,
    )
    blockers = set(str(item) for item in runbook.get("blockers") or [])
    if unlock_brokers:
        blockers.add("live_unlock_already_set")
    if not env_presence["BYBIT_API_KEY"] or not env_presence["BYBIT_API_SECRET"]:
        blockers.add("bybit_credentials_missing")
    blockers.add("dashboard_token_rotation_required_before_live")
    blockers.add("live_orders_disabled_validate_only")
    return {
        "ok": status in {
            "READY_FOR_EC2_READ_ONLY_PRIVATE_VALIDATION",
            "EC2_PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY",
        },
        "mode": "ec2_prelive_validation_audit_validate_only",
        "status": status,
        "symbols": parsed_symbols,
        "execute_private_validation": execute_private_validation,
        "fetch_public_instrument": fetch_public_instrument,
        "live_orders_enabled": False,
        "env_presence": env_presence,
        "live_unlock_brokers": unlock_brokers,
        "security_tasks": _security_tasks(resolved_env),
        "runbook_status": runbook.get("status"),
        "private_validation_status": runbook.get("private_validation_status"),
        "prelive_checklist_status": runbook.get("prelive_checklist_status"),
        "request_attempted": runbook.get("request_attempted"),
        "commands": _ec2_commands(
            parsed_symbols,
            execute_private_validation=execute_private_validation,
            fetch_public_instrument=fetch_public_instrument,
        ),
        "blockers": sorted(blockers),
        "next_actions": _next_actions(status),
        "runbook": runbook,
    }


def compact_lines(report: Mapping[str, Any]) -> list[str]:
    env_presence = report.get("env_presence") or {}
    security_tasks = report.get("security_tasks") or []
    unlock_brokers = report.get("live_unlock_brokers") or []
    lines = [
        "Shadow v8 EC2 pre-live validation audit",
        f"Status: {report.get('status', '-')}",
        f"Symbols: {', '.join(report.get('symbols') or [])}",
        f"Runbook status: {report.get('runbook_status', '-')}",
        f"Private validation status: {report.get('private_validation_status', '-')}",
        f"Pre-live checklist status: {report.get('prelive_checklist_status', '-')}",
        f"Private request attempted: {report.get('request_attempted')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        "Env presence:",
    ]
    for key in ENV_KEYS:
        lines.append(f"- {key}: {bool(env_presence.get(key))}")
    lines.append("Live unlock brokers: " + (", ".join(str(item) for item in unlock_brokers) or "none"))
    lines.append("Security tasks:")
    for item in security_tasks:
        lines.append(f"- {item.get('name')}: {item.get('status')}; required_before_live={item.get('required_before_live')}")
    lines.append("EC2 commands:")
    for item in report.get("commands") or []:
        lines.append(f"- {item.get('step')}: {item.get('command')}")
    blockers = report.get("blockers") or []
    lines.append("Blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"))
    lines.append("Next actions: " + ", ".join(str(item) for item in report.get("next_actions") or []))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a sanitized EC2 pre-live validation audit.")
    parser.add_argument("--symbols", default="ETHUSDT,BTCUSDT")
    parser.add_argument("--base-url")
    parser.add_argument("--fetch-public-instrument", action="store_true")
    parser.add_argument(
        "--execute-private-validation",
        action="store_true",
        help="Run the read-only private validation probe. Never places orders.",
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_ec2_prelive_validation_audit(
        symbols=args.symbols,
        execute_private_validation=args.execute_private_validation,
        fetch_public_instrument=args.fetch_public_instrument,
        base_url=args.base_url,
    )
    if args.compact:
        print("\n".join(compact_lines(report)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
