from __future__ import annotations

import argparse
import json
from typing import Mapping

from shadow_v8.config import BROKERS
from shadow_v8.data.bybit_market_data import BybitMarketData
from shadow_v8.execution.bybit_order_manager import BybitOrderManager
from shadow_v8.execution.execution_router import ExecutionRouter
from shadow_v8.models import AssetConfig, BrokerConfig, EntryDecision


def _asset(symbol: str) -> AssetConfig:
    return AssetConfig(symbol=symbol.upper(), asset_class="crypto", broker="bybit", allow_long=True, allow_short=True)


def _broker_config() -> BrokerConfig:
    broker = BROKERS["bybit"]
    return BrokerConfig(name="bybit", enabled=broker.enabled, paper=broker.paper, base_url=broker.base_url)


def _entry_decision(
    *,
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    risk_pct: float | None,
    qty: float | None,
    account_balance: float,
    instrument_payload: Mapping | None,
) -> EntryDecision:
    metadata = {"account_balance": account_balance}
    if risk_pct is not None:
        metadata["risk_pct"] = risk_pct
    if qty is not None:
        metadata["qty"] = qty
    if instrument_payload is not None:
        metadata["instrument_payload"] = instrument_payload
    return EntryDecision(
        action="ENTER",
        symbol=symbol.upper(),
        direction=direction.upper(),
        reason="bybit_router_preview",
        entry=entry,
        stop=stop,
        metadata=metadata,
    )


def build_bybit_router_preview_report(
    *,
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    risk_pct: float | None = None,
    qty: float | None = None,
    account_balance: float = 10_000.0,
    fetch_public_instrument: bool = False,
    instrument_payload: Mapping | None = None,
    env: Mapping[str, str] | None = None,
) -> dict:
    asset = _asset(symbol)
    fetch_error = None
    if instrument_payload is None and fetch_public_instrument:
        try:
            instrument_payload = BybitMarketData().get_linear_instrument(asset.symbol)
        except Exception as exc:  # noqa: BLE001 - sanitized public-data failure for operator diagnostics.
            fetch_error = type(exc).__name__

    manager = BybitOrderManager(env=env)
    router = ExecutionRouter(
        {"bybit": manager},
        mode="live_guarded",
        broker_configs={"bybit": _broker_config()},
        live_trading_enabled={"crypto": True},
        live_order_unlocked={"bybit": True},
    )
    decision = _entry_decision(
        symbol=asset.symbol,
        direction=direction,
        entry=entry,
        stop=stop,
        risk_pct=risk_pct,
        qty=qty,
        account_balance=account_balance,
        instrument_payload=instrument_payload,
    )
    preflight = router.preflight(asset, action="enter", direction=decision.direction)
    enter_result = router.enter(asset, decision)
    blockers = set(enter_result.get("blockers") or [])
    if fetch_error:
        blockers.add("public_instrument_fetch_failed")
        enter_result["public_fetch_error"] = fetch_error
        enter_result["blockers"] = sorted(blockers)

    return {
        "ok": False,
        "mode": "live_guarded",
        "symbol": asset.symbol,
        "direction": decision.direction,
        "router_preflight": preflight,
        "entry_result": enter_result,
        "payload_ok": enter_result.get("payload_ok", False),
        "payload": enter_result.get("payload"),
        "signed_preview": enter_result.get("signed_preview"),
        "safety_block": bool(enter_result.get("safety_block", True)),
        "live_orders_enabled": bool(enter_result.get("live_orders_enabled", False)),
        "blockers": sorted(blockers),
        "public_fetch_error": fetch_error,
    }


def compact_lines(report: dict) -> list[str]:
    entry_result = report.get("entry_result") or {}
    preflight = report.get("router_preflight") or {}
    payload = report.get("payload") or {}
    signed = report.get("signed_preview") or {}
    blockers = report.get("blockers") or []
    lines = [
        "Shadow v8 Bybit router preview",
        f"Symbol: {report.get('symbol', '-')}",
        f"Direction: {report.get('direction', '-')}",
        f"Router preflight ok: {preflight.get('ok')}",
        f"Payload ready: {report.get('payload_ok')}",
        f"Safety block: {report.get('safety_block')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        f"Side: {payload.get('side', '-')}",
        f"Qty: {payload.get('qty', '-')}",
        f"Stop loss: {payload.get('stopLoss', '-')}",
        f"Signed preview ok: {signed.get('ok')}",
        f"Reason: {entry_result.get('reason', '-')}",
        "Blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"),
    ]
    fetch_error = report.get("public_fetch_error")
    if fetch_error:
        lines.append(f"Public instrument fetch error: {fetch_error}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a sanitized Bybit entry through the execution router preview path.")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--direction", choices=("LONG", "SHORT"), default="LONG")
    parser.add_argument("--entry", type=float, required=True)
    parser.add_argument("--stop", type=float, required=True)
    parser.add_argument("--risk-pct", type=float)
    parser.add_argument("--qty", type=float)
    parser.add_argument("--account-balance", type=float, default=10_000.0)
    parser.add_argument("--fetch-public-instrument", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_bybit_router_preview_report(
        symbol=args.symbol,
        direction=args.direction,
        entry=args.entry,
        stop=args.stop,
        risk_pct=args.risk_pct,
        qty=args.qty,
        account_balance=args.account_balance,
        fetch_public_instrument=args.fetch_public_instrument,
    )
    if args.compact:
        print("\n".join(compact_lines(report)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
