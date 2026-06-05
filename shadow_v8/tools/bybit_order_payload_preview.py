from __future__ import annotations

import argparse
import json

from shadow_v8.data.bybit_market_data import BybitMarketData
from shadow_v8.execution.bybit_order_manager import BybitOrderManager
from shadow_v8.models import AssetConfig, EntryDecision


def _asset(symbol: str) -> AssetConfig:
    return AssetConfig(symbol=symbol.upper(), asset_class="crypto", broker="bybit", allow_long=True, allow_short=True)


def compact_lines(report: dict) -> list[str]:
    intent = report.get("intent") or {}
    payload = report.get("payload") or {}
    signed = report.get("signed_preview") or {}
    blockers = report.get("blockers") or []
    return [
        "Shadow v8 Bybit order payload preview",
        f"Symbol: {report.get('symbol', '-')}",
        f"Mode: {report.get('mode', '-')}",
        f"Payload ready: {report.get('payload_ok')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        f"Side: {payload.get('side', '-')}",
        f"Order type: {payload.get('orderType', '-')}",
        f"Qty: {payload.get('qty', '-')}",
        f"Stop loss: {payload.get('stopLoss', '-')}",
        f"Notional: {intent.get('notional', '-')}",
        f"Signed preview ok: {signed.get('ok')}",
        "Blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"),
    ]


def build_bybit_order_payload_preview(
    *,
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    risk_pct: float | None = None,
    qty: float | None = None,
    account_balance: float = 10_000.0,
    fetch_public_instrument: bool = False,
    instrument_payload: dict | None = None,
) -> dict:
    asset = _asset(symbol)
    fetch_error = None
    if instrument_payload is None and fetch_public_instrument:
        try:
            instrument_payload = BybitMarketData().get_linear_instrument(asset.symbol)
        except Exception as exc:  # noqa: BLE001 - tool reports public-data failure without secrets.
            fetch_error = type(exc).__name__
    if instrument_payload is None:
        instrument_payload = {}
    metadata = {}
    if risk_pct is not None:
        metadata["risk_pct"] = risk_pct
    if qty is not None:
        metadata["qty"] = qty
    decision = EntryDecision(
        action="ENTER",
        symbol=asset.symbol,
        direction=direction.upper(),
        reason="bybit_payload_preview",
        entry=entry,
        stop=stop,
        metadata=metadata,
    )
    report = BybitOrderManager().build_entry_order_payload_preview(
        asset,
        decision,
        instrument_payload,
        account_balance=account_balance,
    )
    if fetch_error:
        report["blockers"] = sorted(set([*report["blockers"], "public_instrument_fetch_failed"]))
        report["public_fetch_error"] = fetch_error
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a sanitized Bybit create-order payload preview.")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--direction", choices=["LONG", "SHORT"], default="LONG")
    parser.add_argument("--entry", type=float, required=True)
    parser.add_argument("--stop", type=float, required=True)
    parser.add_argument("--risk-pct", type=float)
    parser.add_argument("--qty", type=float)
    parser.add_argument("--account-balance", type=float, default=10_000.0)
    parser.add_argument("--fetch-public-instrument", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_bybit_order_payload_preview(
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
