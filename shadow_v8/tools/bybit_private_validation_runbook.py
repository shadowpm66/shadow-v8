from __future__ import annotations

import argparse
import json
from typing import Any, Callable, Mapping, Sequence

from shadow_v8.tools.bybit_prelive_checklist import build_bybit_prelive_checklist
from shadow_v8.tools.bybit_private_validation_probe import build_bybit_private_validation_probe
from shadow_v8.tools.bybit_public_dry_run_batch import parse_symbols


def _ec2_commands(symbols: Sequence[str], execute_private_validation: bool) -> list[dict[str, str]]:
    symbol_text = ",".join(symbols) if symbols else "ETHUSDT,BTCUSDT"
    commands = [
        {
            "step": "pull_latest_main",
            "command": "cd ~/shadow-v8 && git pull --ff-only",
        },
        {
            "step": "load_credentials_without_printing",
            "command": "cd ~/shadow-v8 && set -a && source .env && set +a",
        },
        {
            "step": "signed_preview_only",
            "command": "cd ~/shadow-v8 && python -m shadow_v8.tools.bybit_private_validation_probe --compact",
        },
        {
            "step": "prelive_checklist_with_private_preview",
            "command": (
                "cd ~/shadow-v8 && python -m shadow_v8.tools.bybit_prelive_checklist "
                f"--symbols {symbol_text} --include-private-validation --compact"
            ),
        },
    ]
    if execute_private_validation:
        commands.append(
            {
                "step": "read_only_private_validation",
                "command": (
                    "cd ~/shadow-v8 && python -m shadow_v8.tools.bybit_private_validation_probe "
                    "--execute-private-request --compact"
                ),
            }
        )
        commands.append(
            {
                "step": "prelive_checklist_with_read_only_private_validation",
                "command": (
                    "cd ~/shadow-v8 && python -m shadow_v8.tools.bybit_prelive_checklist "
                    f"--symbols {symbol_text} --execute-private-validation --compact"
                ),
            }
        )
    return commands


def _status(checklist_status: str, private_status: str, execute_private_validation: bool) -> str:
    if checklist_status == "UNSAFE_LIVE_ENABLED":
        return "HALT_UNSAFE_LIVE_ENABLED"
    if private_status == "CREDENTIALS_PENDING" or checklist_status == "CREDENTIALS_PENDING":
        return "WAITING_FOR_EC2_CREDENTIALS"
    if execute_private_validation and private_status == "PRIVATE_VALIDATION_READY":
        return "PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY"
    if private_status == "SIGNED_PREVIEW_READY":
        return "READY_FOR_READ_ONLY_PRIVATE_VALIDATION"
    return "BLOCKED"


def _next_actions(status: str) -> list[str]:
    actions = ["keep_live_orders_disabled"]
    if status == "WAITING_FOR_EC2_CREDENTIALS":
        actions.append("run_on_ec2_with_env_loaded")
    elif status == "READY_FOR_READ_ONLY_PRIVATE_VALIDATION":
        actions.append("run_execute_private_request_on_ec2")
    elif status == "PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY":
        actions.append("prepare_testnet_or_tiny_live_unlock_review")
    elif status == "HALT_UNSAFE_LIVE_ENABLED":
        actions.append("stop_and_restore_validate_only_mode")
    else:
        actions.append("inspect_runbook_blockers")
    actions.append("do_not_place_live_orders")
    return actions


def build_bybit_private_validation_runbook(
    *,
    symbols: str | Sequence[str] | None = None,
    execute_private_validation: bool = False,
    fetch_public_instrument: bool = False,
    base_url: str | None = None,
    env: Mapping[str, str] | None = None,
    private_http_get: Callable[..., Any] | None = None,
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    parsed_symbols = parse_symbols(symbols)
    private_probe = build_bybit_private_validation_probe(
        execute_private_request=execute_private_validation,
        base_url=base_url,
        env=env,
        http_get=private_http_get,
        timestamp_ms=timestamp_ms,
    )
    checklist = build_bybit_prelive_checklist(
        symbols=parsed_symbols,
        fetch_public_instrument=fetch_public_instrument,
        base_url=base_url,
        include_private_validation=True,
        execute_private_validation=execute_private_validation,
        private_http_get=private_http_get,
        private_timestamp_ms=timestamp_ms,
        env=env,
    )
    status = _status(
        checklist_status=str(checklist.get("status")),
        private_status=str(private_probe.get("status")),
        execute_private_validation=execute_private_validation,
    )
    blockers = sorted(
        set(
            list(private_probe.get("blockers") or [])
            + list((checklist.get("blocker_counts") or {}).keys())
            + ["live_orders_disabled_validate_only"]
        )
    )
    return {
        "ok": status in {
            "READY_FOR_READ_ONLY_PRIVATE_VALIDATION",
            "PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY",
        },
        "mode": "bybit_private_validation_runbook_validate_only",
        "status": status,
        "symbols": parsed_symbols,
        "execute_private_validation": execute_private_validation,
        "fetch_public_instrument": fetch_public_instrument,
        "live_orders_enabled": False,
        "private_validation_status": private_probe.get("status"),
        "prelive_checklist_status": checklist.get("status"),
        "request_attempted": private_probe.get("request_attempted"),
        "credentials_present": private_probe.get("credentials_present"),
        "commands": _ec2_commands(parsed_symbols, execute_private_validation),
        "guardrails": [
            "never_print_env",
            "never_commit_env",
            "never_print_api_keys_or_signatures",
            "keep_live_orders_disabled",
            "private_probe_is_read_only",
        ],
        "blockers": blockers,
        "next_actions": _next_actions(status),
        "private_validation": private_probe,
        "prelive_checklist": checklist,
    }


def compact_lines(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "Shadow v8 Bybit private validation runbook",
        f"Status: {report.get('status', '-')}",
        f"Symbols: {', '.join(report.get('symbols') or [])}",
        f"Credentials present: {report.get('credentials_present')}",
        f"Private validation status: {report.get('private_validation_status')}",
        f"Pre-live checklist status: {report.get('prelive_checklist_status')}",
        f"Private request attempted: {report.get('request_attempted')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        "EC2 commands:",
    ]
    for item in report.get("commands") or []:
        lines.append(f"- {item.get('step')}: {item.get('command')}")
    blockers = report.get("blockers") or []
    lines.append("Blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"))
    lines.append("Guardrails: " + ", ".join(str(item) for item in report.get("guardrails") or []))
    lines.append("Next actions: " + ", ".join(str(item) for item in report.get("next_actions") or []))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a validate-only Bybit private validation runbook.")
    parser.add_argument("--symbols", default="ETHUSDT,BTCUSDT")
    parser.add_argument("--base-url")
    parser.add_argument("--fetch-public-instrument", action="store_true")
    parser.add_argument(
        "--execute-private-validation",
        action="store_true",
        help="Include and run the read-only private validation probe. Never places orders.",
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_bybit_private_validation_runbook(
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
