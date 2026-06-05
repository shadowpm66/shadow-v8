from __future__ import annotations

import argparse
import json

from shadow_v8.config import ASSETS
from shadow_v8.data.bybit_market_data import BybitMarketData
from shadow_v8.execution.bybit_order_manager import BybitOrderManager
from shadow_v8.models import AssetConfig


def _asset_for_symbol(symbol: str) -> AssetConfig:
    symbol = symbol.upper()
    for asset in ASSETS:
        if asset.symbol.upper() == symbol:
            return asset
    return AssetConfig(symbol=symbol, asset_class="crypto", broker="bybit", allow_long=True, allow_short=True)


def compact_lines(report: dict) -> list[str]:
    instrument = report.get("instrument") or {}
    rules = instrument.get("rules") or {}
    blockers = report.get("blockers") or []
    return [
        "Shadow v8 Bybit preflight",
        f"Symbol: {report.get('symbol', '-')}",
        f"Mode: {report.get('mode', '-')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        f"Config credentials present: {report.get('config', {}).get('credentials_present')}",
        f"Instrument ok: {instrument.get('ok')}",
        f"Instrument status: {rules.get('status', '-')}",
        f"Tick size: {rules.get('tick_size', '-')}",
        f"Qty step: {rules.get('qty_step', '-')}",
        f"Min order qty: {rules.get('min_order_qty', '-')}",
        f"Min notional: {rules.get('min_notional_value', '-')}",
        "Blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"),
    ]


def build_bybit_preflight_report(*, symbol: str, fetch_public_instrument: bool = False) -> dict:
    asset = _asset_for_symbol(symbol)
    instrument_payload = None
    fetch_error = None
    if fetch_public_instrument:
        try:
            instrument_payload = BybitMarketData().get_linear_instrument(asset.symbol)
        except Exception as exc:  # noqa: BLE001 - tool reports public-data failure without secrets.
            fetch_error = type(exc).__name__
    report = BybitOrderManager().preflight_report(asset, instrument_payload)
    if fetch_error:
        report["blockers"] = sorted(set([*report["blockers"], "public_instrument_fetch_failed"]))
        report["public_fetch_error"] = fetch_error
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a sanitized Bybit validation-only preflight report.")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--fetch-public-instrument", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_bybit_preflight_report(
        symbol=args.symbol,
        fetch_public_instrument=args.fetch_public_instrument,
    )
    if args.compact:
        print("\n".join(compact_lines(report)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
