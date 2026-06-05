from __future__ import annotations

import os
from collections import Counter
from typing import Mapping, Protocol

from shadow_v8.models import AssetConfig, BrokerConfig


class EnvReader(Protocol):
    def get(self, key: str, default: str | None = None) -> str | None: ...


BROKER_CREDENTIAL_ENV = {
    "bybit": ("BYBIT_API_KEY", "BYBIT_API_SECRET"),
    "ibkr": ("IBKR_ACCOUNT_ID",),
    "paper": (),
}

BROKER_ADAPTER_STATUS = {
    "bybit": "validate_only",
    "ibkr": "placeholder",
    "paper": "connected",
}


def execution_readiness_report(
    *,
    assets: list[AssetConfig],
    broker_configs: Mapping[str, BrokerConfig],
    mode: str,
    live_trading_enabled: Mapping[str, bool],
    executors: Mapping[str, object] | None = None,
    env: EnvReader | None = None,
) -> dict:
    env = env or os.environ
    executors = executors or {}
    mode_label = mode.lower().strip()
    broker_names = sorted({asset.broker for asset in assets} | {"paper"})
    broker_reports = [
        _broker_report(
            broker_name,
            broker_configs.get(broker_name),
            mode_label=mode_label,
            live_trading_enabled=live_trading_enabled,
            asset_classes={asset.asset_class for asset in assets if asset.broker == broker_name},
            executor_present=broker_name in executors,
            env=env,
        )
        for broker_name in broker_names
    ]
    asset_routes = [
        _asset_route_report(asset, mode_label, live_trading_enabled, broker_configs, broker_reports)
        for asset in assets
    ]
    blockers = Counter(
        blocker
        for report in broker_reports
        for blocker in report["blockers"]
    )
    route_blockers = Counter(
        blocker
        for route in asset_routes
        for blocker in route["blockers"]
    )
    blockers.update(route_blockers)
    live_mode = mode_label == "live_guarded"
    report_ready = any(route["ready"] for route in asset_routes) and not blockers
    if not live_mode and mode_label != "paper":
        report_ready = False
    return {
        "mode": mode_label,
        "ready": report_ready,
        "brokers_checked": len(broker_reports),
        "assets_checked": len(asset_routes),
        "broker_reports": broker_reports,
        "asset_routes": asset_routes[:20],
        "top_blockers": [
            {"reason": reason, "count": count}
            for reason, count in blockers.most_common(8)
        ],
    }


def _broker_report(
    broker_name: str,
    broker: BrokerConfig | None,
    *,
    mode_label: str,
    live_trading_enabled: Mapping[str, bool],
    asset_classes: set[str],
    executor_present: bool,
    env: EnvReader,
) -> dict:
    blockers = []
    credential_keys = BROKER_CREDENTIAL_ENV.get(broker_name, ())
    missing_credentials = [key for key in credential_keys if not str(env.get(key, "") or "").strip()]
    adapter_status = BROKER_ADAPTER_STATUS.get(broker_name, "unknown")
    enabled = bool(broker.enabled) if broker else False
    paper = bool(broker.paper) if broker else False
    live_flags = {asset_class: bool(live_trading_enabled.get(asset_class, False)) for asset_class in sorted(asset_classes)}

    if broker is None:
        blockers.append("broker_config_missing")
    elif not enabled:
        blockers.append("broker_disabled")
    if mode_label == "scan_only":
        blockers.append("execution_mode_scan_only")
    if broker_name != "paper" and mode_label == "live_guarded":
        if paper:
            blockers.append("broker_configured_as_paper")
        if missing_credentials:
            blockers.append("credentials_missing")
        if not executor_present:
            blockers.append("executor_missing")
        if adapter_status in ("placeholder", "validate_only"):
            blockers.append(f"adapter_{adapter_status}")
        if asset_classes and not any(live_flags.values()):
            blockers.append("live_flag_disabled")
    if broker_name == "paper" and mode_label == "paper" and not executor_present:
        blockers.append("executor_missing")

    return {
        "broker": broker_name,
        "enabled": enabled,
        "paper": paper,
        "executor_present": executor_present,
        "adapter_status": adapter_status,
        "credentials_present": not missing_credentials,
        "missing_credentials": missing_credentials,
        "live_flags": live_flags,
        "ready": not blockers,
        "blockers": blockers,
    }


def _asset_route_report(
    asset: AssetConfig,
    mode_label: str,
    live_trading_enabled: Mapping[str, bool],
    broker_configs: Mapping[str, BrokerConfig],
    broker_reports: list[dict],
) -> dict:
    broker_lookup = {report["broker"]: report for report in broker_reports}
    broker_report = broker_lookup.get(asset.broker, {})
    blockers = []
    if not asset.enabled:
        blockers.append("asset_disabled")
    if mode_label == "scan_only":
        blockers.append("execution_mode_scan_only")
    if mode_label == "live_guarded":
        broker = broker_configs.get(asset.broker)
        if broker is None:
            blockers.append("broker_config_missing")
        elif broker.paper:
            blockers.append("broker_configured_as_paper")
        if not live_trading_enabled.get(asset.asset_class, False):
            blockers.append("live_flag_disabled")
    if broker_report.get("blockers"):
        blockers.extend(f"broker:{blocker}" for blocker in broker_report["blockers"])
    return {
        "symbol": asset.symbol,
        "asset_class": asset.asset_class,
        "broker": asset.broker,
        "live_flag_enabled": bool(live_trading_enabled.get(asset.asset_class, False)),
        "ready": not blockers,
        "blockers": sorted(set(blockers)),
    }
