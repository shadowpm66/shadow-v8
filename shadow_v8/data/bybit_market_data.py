from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from shadow_v8.config import BROKERS
from shadow_v8.data.market_data import MarketDataProvider
from shadow_v8.models import AssetConfig, Candle, MarketDataBundle


class BybitMarketData(MarketDataProvider):
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or BROKERS["bybit"].base_url or "https://api.bybit.com").rstrip("/")

    def _fetch_candles(self, symbol: str, interval: str, limit: int = 300) -> list[Candle]:
        url = f"{self.base_url}/v5/market/kline"
        params: dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if payload.get("retCode") != 0:
            return []
        rows = payload.get("result", {}).get("list", []) or []
        candles: list[Candle] = []
        for row in reversed(rows):
            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return candles

    def _last_price(self, symbol: str) -> float | None:
        url = f"{self.base_url}/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        rows = response.json().get("result", {}).get("list", []) or []
        return float(rows[0]["lastPrice"]) if rows else None

    def list_linear_usdt_symbols(self, max_symbols: int | None = None) -> list[str]:
        url = f"{self.base_url}/v5/market/instruments-info"
        symbols: list[str] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"category": "linear", "status": "Trading", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            payload = response.json()
            if payload.get("retCode") != 0:
                break
            result = payload.get("result", {}) or {}
            for item in result.get("list", []) or []:
                symbol = str(item.get("symbol") or "")
                quote = str(item.get("quoteCoin") or "")
                status = str(item.get("status") or "")
                if status == "Trading" and quote == "USDT" and symbol.endswith("USDT"):
                    symbols.append(symbol)
                    if max_symbols and len(symbols) >= max_symbols:
                        return symbols
            cursor = result.get("nextPageCursor") or None
            if not cursor:
                break
        return symbols[:max_symbols] if max_symbols else symbols

    def load(self, asset: AssetConfig) -> MarketDataBundle:
        timeframes = {"D", "W", asset.primary_timeframe, asset.confirmation_timeframe, *asset.intraday_timeframes}
        candles = {tf: self._fetch_candles(asset.symbol, tf) for tf in sorted(timeframes)}
        return MarketDataBundle(
            symbol=asset.symbol,
            asset_class=asset.asset_class,
            candles=candles,
            last_price=self._last_price(asset.symbol),
        )
