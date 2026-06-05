from __future__ import annotations

import os
import time
from dataclasses import dataclass
from hashlib import sha256
from hmac import new as hmac_new
from urllib.parse import urlencode
from typing import Any, Mapping

from shadow_v8.config import BROKERS
from shadow_v8.models import AssetConfig, EntryDecision, ExitDecision


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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

