from __future__ import annotations

import argparse
import json
from dataclasses import replace
from typing import Mapping

from shadow_v8.config import ASSETS, BROKERS, EXECUTION_CONFIG, FEATURE_FLAGS, enabled_assets
from shadow_v8.execution.readiness import EnvReader, execution_readiness_report


def build_execution_readiness_report(
    *,
    mode: str | None = None,
    include_disabled_assets: bool = False,
    env: EnvReader | None = None,
    executors: Mapping[str, object] | None = None,
) -> dict:
    mode_label = (mode or EXECUTION_CONFIG["mode"]).lower().strip()
    assets = ASSETS if include_disabled_assets else enabled_assets()
    if mode_label == "paper":
        assets = [replace(asset, broker="paper") for asset in assets]
    if executors is None:
        executors = {"paper": object()} if mode_label == "paper" else {}
    return execution_readiness_report(
        assets=assets,
        broker_configs=BROKERS,
        mode=mode_label,
        live_trading_enabled={
            "crypto": FEATURE_FLAGS["crypto_live_trading_enabled"],
            "forex": FEATURE_FLAGS["crypto_live_trading_enabled"],
            "stock": FEATURE_FLAGS["stock_live_trading_enabled"],
        },
        executors=executors,
        env=env,
    )


def compact_lines(report: dict) -> list[str]:
    readiness = "READY" if report.get("ready") else "BLOCKED"
    lines = [
        "Shadow v8 execution readiness",
        f"Mode: {report.get('mode', '-')}",
        f"Readiness: {readiness}",
        f"Brokers checked: {report.get('brokers_checked', 0)}",
        f"Assets checked: {report.get('assets_checked', 0)}",
    ]
    blockers = report.get("top_blockers") or []
    if blockers:
        lines.append("Top blockers:")
        lines.extend(f"- {item.get('reason')} ({item.get('count')})" for item in blockers[:8])
    else:
        lines.append("Top blockers: none")
    broker_reports = report.get("broker_reports") or []
    if broker_reports:
        lines.append("Brokers:")
        for broker in broker_reports:
            broker_state = "READY" if broker.get("ready") else "BLOCKED"
            missing = broker.get("missing_credentials") or []
            missing_text = ",".join(str(item) for item in missing) if missing else "none"
            lines.append(
                f"- {broker.get('broker')}: {broker_state}; adapter={broker.get('adapter_status')}; "
                f"executor={broker.get('executor_present')}; missing_env={missing_text}"
            )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a sanitized Shadow v8 execution readiness report.")
    parser.add_argument("--mode", choices=("scan_only", "paper", "live_guarded"), default=None)
    parser.add_argument("--include-disabled-assets", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_execution_readiness_report(
        mode=args.mode,
        include_disabled_assets=args.include_disabled_assets,
    )
    if args.compact:
        print("\n".join(compact_lines(report)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
