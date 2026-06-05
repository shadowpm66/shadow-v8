from __future__ import annotations

import os
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from hashlib import sha256
from hmac import new as hmac_new
from typing import Any, Mapping
from urllib.parse import urlencode

from shadow_v8.config import BROKERS
from shadow_v8.models import AssetConfig, EntryDecision, ExitDecision
from shadow_v8.strategy.position_sizer import size_by_risk


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_down(value: float, step: float | None) -> float:
    if step is None or step <= 0:
        return float(value)
    try:
        decimal_value = Decimal(str(value))
        decimal_step = Decimal(str(step))
        return float((decimal_value / decimal_step).to_integral_value(rounding=ROUND_DOWN) * decimal_step)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return float(value)


def _redacted(value: str | None) -> str:
    if not value:
        return ""
    return f"{value[:3]}...{value[-3:]}" if len(value) > 6 else "***"


@dataclass(frozen=True)
class BybitInstrumentRules:
    symbol: str
    status: str
    base_coin: str
    quote_coin: str
    qty_step: float | None = None
    min_order_qty: float | None = None
    max_order_qty: float | None = None
    min_notional_value: float | None = None
    tick_size: float | None = None
    max_leverage: float | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "BybitInstrumentRules":
        lot_filter = payload.get("lotSizeFilter") or {}
        price_filter = payload.get("priceFilter") or {}
        leverage_filter = payload.get("leverageFilter") or {}
        return cls(
            symbol=str(payload.get("symbol", "")).upper(),
            status=str(payload.get("status", "")),
            base_coin=str(payload.get("baseCoin", "")).upper(),
            quote_coin=str(payload.get("quoteCoin", "")).upper(),
            qty_step=_to_float(lot_filter.get("qtyStep")),
            min_order_qty=_to_float(lot_filter.get("minOrderQty")),
            max_order_qty=_to_float(lot_filter.get("maxOrderQty")),
            min_notional_value=_to_float(lot_filter.get("minNotionalValue")),
            tick_size=_to_float(price_filter.get("tickSize")),
            max_leverage=_to_float(leverage_filter.get("maxLeverage")),
        )

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "base_coin": self.base_coin,
            "quote_coin": self.quote_coin,
            "qty_step": self.qty_step,
            "min_order_qty": self.min_order_qty,
            "max_order_qty": self.max_order_qty,
            "min_notional_value": self.min_notional_value,
            "tick_size": self.tick_size,
            "max_leverage": self.max_leverage,
        }


class BybitOrderManager:
    """Bybit execution adapter in validation-only mode.

    This adapter validates credentials and instrument constraints, but deliberately
    refuses to place live orders until the signed order path is fully tested.
    """

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self.broker = BROKERS["bybit"]
        self.env = env or os.environ
        self.recv_window = "5000"

    def validate_config(self) -> dict:
        credential_keys = ("BYBIT_API_KEY", "BYBIT_API_SECRET")
        missing_credentials = [key for key in credential_keys if not str(self.env.get(key, "") or "").strip()]
        blockers = []
        if not self.broker.enabled:
            blockers.append("broker_disabled")
        if self.broker.paper:
            blockers.append("broker_configured_as_paper")
        if not self.broker.base_url:
            blockers.append("base_url_missing")
        if missing_credentials:
            blockers.append("credentials_missing")
        blockers.append("live_orders_disabled_validate_only")
        return {
            "ok": False,
            "mode": "validate_only",
            "broker": "bybit",
            "base_url_present": bool(self.broker.base_url),
            "credentials_present": not missing_credentials,
            "missing_credentials": missing_credentials,
            "live_orders_enabled": False,
            "blockers": blockers,
        }

    def signed_request_preview(
        self,
        *,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
        body: str = "",
        timestamp_ms: int | None = None,
    ) -> dict:
        api_key = str(self.env.get("BYBIT_API_KEY", "") or "").strip()
        api_secret = str(self.env.get("BYBIT_API_SECRET", "") or "").strip()
        timestamp_ms = timestamp_ms or int(time.time() * 1000)
        method_label = method.upper().strip()
        params = params or {}
        blockers = []
        if not api_key or not api_secret:
            blockers.append("credentials_missing")
        if method_label not in {"GET", "POST"}:
            blockers.append("unsupported_method")
        if not path.startswith("/"):
            blockers.append("path_missing_leading_slash")
        query = urlencode(sorted((key, str(value)) for key, value in params.items())) if params else ""
        payload = query if method_label == "GET" else body
        sign_payload = f"{timestamp_ms}{api_key}{self.recv_window}{payload}"
        signature = hmac_new(api_secret.encode("utf-8"), sign_payload.encode("utf-8"), sha256).hexdigest() if api_secret else ""
        headers = {
            "X-BAPI-API-KEY": _redacted(api_key),
            "X-BAPI-SIGN": _redacted(signature),
            "X-BAPI-TIMESTAMP": str(timestamp_ms),
            "X-BAPI-RECV-WINDOW": self.recv_window,
        }
        return {
            "ok": not blockers,
            "mode": "validate_only",
            "method": method_label,
            "path": path,
            "query": query,
            "body_present": bool(body),
            "timestamp_ms": timestamp_ms,
            "recv_window": int(self.recv_window),
            "signature_present": bool(signature),
            "signature_length": len(signature),
            "headers_preview": headers,
            "blockers": blockers,
        }

    def validate_instrument(self, asset: AssetConfig, payload: Mapping[str, Any]) -> dict:
        rules = BybitInstrumentRules.from_payload(payload)
        blockers = []
        if asset.asset_class != "crypto":
            blockers.append("asset_class_not_crypto")
        if rules.symbol != asset.symbol.upper():
            blockers.append("symbol_mismatch")
        if rules.status != "Trading":
            blockers.append("instrument_not_trading")
        if rules.quote_coin != "USDT":
            blockers.append("quote_not_usdt")
        if rules.qty_step is None:
            blockers.append("qty_step_missing")
        if rules.min_order_qty is None:
            blockers.append("min_order_qty_missing")
        if rules.tick_size is None:
            blockers.append("tick_size_missing")
        return {
            "ok": not blockers,
            "mode": "validate_only",
            "symbol": asset.symbol,
            "rules": rules.as_dict(),
            "blockers": blockers,
        }

    def build_entry_intent_preview(
        self,
        asset: AssetConfig,
        decision: EntryDecision,
        instrument_payload: Mapping[str, Any],
        *,
        account_balance: float = 10_000.0,
    ) -> dict:
        rules = BybitInstrumentRules.from_payload(instrument_payload)
        instrument_check = self.validate_instrument(asset, instrument_payload)
        blockers = [f"instrument:{blocker}" for blocker in instrument_check["blockers"]]
        if decision.action != "ENTER":
            blockers.append("entry_action_not_enter")
        if decision.entry is None:
            blockers.append("entry_missing")
        if decision.stop is None:
            blockers.append("stop_missing")
        side = "Buy" if decision.direction == "LONG" else "Sell" if decision.direction == "SHORT" else ""
        if not side:
            blockers.append("direction_not_supported")

        entry = float(decision.entry or 0.0)
        stop = float(decision.stop or 0.0)
        if entry <= 0:
            blockers.append("entry_invalid")
        if stop <= 0:
            blockers.append("stop_invalid")
        if decision.direction == "LONG" and stop >= entry:
            blockers.append("invalid_long_stop_side")
        if decision.direction == "SHORT" and stop <= entry:
            blockers.append("invalid_short_stop_side")

        risk_pct = float(decision.metadata.get("risk_pct") or asset.max_risk_pct or 0.0)
        raw_qty = _to_float(decision.metadata.get("qty"))
        sizing_model = "provided_qty" if raw_qty is not None else "risk_pct"
        if raw_qty is None:
            raw_qty = size_by_risk(float(account_balance), risk_pct, entry, stop) if entry > 0 and stop > 0 else 0.0
        rounded_qty = _round_down(raw_qty, rules.qty_step)
        rounded_entry = _round_down(entry, rules.tick_size)
        rounded_stop = _round_down(stop, rules.tick_size)
        notional = rounded_qty * rounded_entry

        if rounded_qty <= 0:
            blockers.append("qty_zero_after_rounding")
        if rules.min_order_qty is not None and rounded_qty < rules.min_order_qty:
            blockers.append("qty_below_min_order_qty")
        if rules.max_order_qty is not None and rounded_qty > rules.max_order_qty:
            blockers.append("qty_above_max_order_qty")
        if rules.min_notional_value is not None and notional < rules.min_notional_value:
            blockers.append("notional_below_min")

        return {
            "ok": not blockers,
            "mode": "validate_only",
            "symbol": asset.symbol,
            "side": side,
            "order_type": "Market",
            "time_in_force": "GTC",
            "reduce_only": False,
            "sizing_model": sizing_model,
            "risk_pct": round(risk_pct, 6),
            "account_balance": round(float(account_balance), 2),
            "raw_qty": round(float(raw_qty or 0.0), 8),
            "qty": round(float(rounded_qty), 8),
            "entry": round(float(rounded_entry), 8),
            "stop": round(float(rounded_stop), 8),
            "notional": round(float(notional), 4),
            "rules": rules.as_dict(),
            "blockers": sorted(set(blockers)),
            "live_orders_enabled": False,
        }

    def preflight_report(
        self,
        asset: AssetConfig,
        instrument_payload: Mapping[str, Any] | None = None,
        *,
        include_signed_preview: bool = False,
    ) -> dict:
        config = self.validate_config()
        instrument = None
        signed_preview = None
        blockers = list(config["blockers"])
        if instrument_payload is None:
            blockers.append("instrument_payload_missing")
        else:
            instrument = self.validate_instrument(asset, instrument_payload)
            blockers.extend(f"instrument:{blocker}" for blocker in instrument["blockers"])
        if include_signed_preview:
            signed_preview = self.signed_request_preview(
                method="GET",
                path="/v5/order/realtime",
                params={"category": "linear", "symbol": asset.symbol},
            )
            blockers.extend(f"signed:{blocker}" for blocker in signed_preview["blockers"])
        return {
            "ok": False,
            "mode": "validate_only",
            "broker": "bybit",
            "symbol": asset.symbol,
            "asset_class": asset.asset_class,
            "config": config,
            "instrument": instrument,
            "signed_preview": signed_preview,
            "live_orders_enabled": False,
            "blockers": sorted(set(blockers)),
        }

    def enter(self, asset: AssetConfig, decision: EntryDecision) -> dict:
        return {
            "ok": False,
            "reason": "Bybit adapter is validate-only; live order placement is disabled",
            "symbol": asset.symbol,
            "action": decision.action,
        }

    def apply_exit(self, asset: AssetConfig, decision: ExitDecision) -> dict:
        return {
            "ok": False,
            "reason": "Bybit adapter is validate-only; live exit placement is disabled",
            "symbol": asset.symbol,
            "action": decision.action,
        }

