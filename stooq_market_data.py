from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from typing import Any

import pandas as pd
import requests

from shadow_v8.data.market_data import MarketDataProvider
from shadow_v8.models import AssetConfig, Candle, MarketDataBundle


class StooqMarketData(MarketDataProvider):
    """Daily/weekly stock OHLCV provider with Stooq first and Yahoo fallback."""

    def __init__(self, suffix: str = "us", timeout_sec: float = 10.0) -> None:
        self.suffix = suffix.strip().lower() or "us"
        self.timeout_sec = timeout_sec
        self.base_url = "https://stooq.com/q/d/l/"
        self.yahoo_base_url = "https://query1.finance.yahoo.com/v8/finance/chart"

    def _stooq_symbol(self, symbol: str) -> str:
        cleaned = symbol.strip().lower().replace("-", ".")
        if "." in cleaned:
            return cleaned
        return f"{cleaned}.{self.suffix}"

    def _normalize_daily_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        required = {"Date", "Open", "High", "Low", "Close", "Volume"}
        if not required.issubset(frame.columns):
            return pd.DataFrame()

        frame = frame.loc[:, ["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        frame["Date"] = pd.to_datetime(frame["Date"], utc=True, errors="coerce")
        for col in ("Open", "High", "Low", "Close", "Volume"):
            frame[col] = pd.to_numeric(frame[col], errors="coerce")

        frame = frame.dropna(subset=["Date", "Open", "High", "Low", "Close"])
        frame = frame.sort_values("Date")
        frame = frame[frame["Close"] > 0]
        return frame.tail(650).reset_index(drop=True)

    def _parse_stooq_csv(self, text: str) -> pd.DataFrame:
        text = text.strip()
        if not text or text.lower().startswith("no data"):
            return pd.DataFrame()
        if "<html" in text.lower() or "<!doctype" in text.lower():
            raise ValueError("Stooq returned HTML instead of CSV")

        for sep in (",", ";"):
            try:
                frame = pd.read_csv(StringIO(text), sep=sep, engine="python", on_bad_lines="skip")
            except pd.errors.ParserError:
                continue
            normalized = self._normalize_daily_frame(frame)
            if not normalized.empty:
                return normalized

        raise ValueError("Stooq response did not contain daily OHLCV columns")

    def _fetch_stooq_daily_frame(self, symbol: str) -> pd.DataFrame:
        params: dict[str, Any] = {"s": self._stooq_symbol(symbol), "i": "d"}
        response = requests.get(
            self.base_url,
            params=params,
            headers={"User-Agent": "Shadow v8 research"},
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        return self._parse_stooq_csv(response.text)

    def _fetch_yahoo_daily_frame(self, symbol: str) -> pd.DataFrame:
        url = f"{self.yahoo_base_url}/{symbol.strip().upper()}"
        response = requests.get(
            url,
            params={"range": "3y", "interval": "1d", "events": "history", "includeAdjustedClose": "true"},
            headers={"User-Agent": "Shadow v8 research"},
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()

        chart = payload.get("chart") or {}
        error = chart.get("error")
        if error:
            raise ValueError(str(error))

        results = chart.get("result") or []
        if not results:
            return pd.DataFrame()

        result = results[0]
        timestamps = result.get("timestamp") or []
        quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        if not timestamps or not quotes:
            return pd.DataFrame()

        frame = pd.DataFrame(
            {
                "Date": pd.to_datetime(timestamps, unit="s", utc=True, errors="coerce"),
                "Open": quotes.get("open") or [],
                "High": quotes.get("high") or [],
                "Low": quotes.get("low") or [],
                "Close": quotes.get("close") or [],
                "Volume": quotes.get("volume") or [],
            }
        )
        return self._normalize_daily_frame(frame)

    def _fetch_daily_frame(self, symbol: str, metadata: dict[str, Any]) -> pd.DataFrame:
        try:
            frame = self._fetch_stooq_daily_frame(symbol)
            if not frame.empty:
                metadata["source"] = "stooq"
                return frame
            metadata["stooq_status"] = "empty"
        except Exception as exc:
            metadata["stooq_error"] = f"{type(exc).__name__}: {exc}"

        try:
            frame = self._fetch_yahoo_daily_frame(symbol)
            if not frame.empty:
                metadata["source"] = "yahoo_fallback"
                metadata["yahoo_symbol"] = symbol.strip().upper()
                return frame
            metadata["yahoo_status"] = "empty"
        except Exception as exc:
            metadata["yahoo_error"] = f"{type(exc).__name__}: {exc}"

        metadata["source"] = "stock_market_unavailable"
        return pd.DataFrame()

    def _weekly_frame(self, daily: pd.DataFrame) -> pd.DataFrame:
        if daily.empty:
            return pd.DataFrame()

        weekly = (
            daily.set_index("Date")
            .resample("W-FRI")
            .agg(
                {
                    "Open": "first",
                    "High": "max",
                    "Low": "min",
                    "Close": "last",
                    "Volume": "sum",
                }
            )
            .dropna(subset=["Open", "High", "Low", "Close"])
            .reset_index()
        )
        return weekly.tail(220)

    def _to_candles(self, frame: pd.DataFrame) -> list[Candle]:
        candles: list[Candle] = []
        for row in frame.itertuples(index=False):
            timestamp = row.Date.to_pydatetime() if hasattr(row.Date, "to_pydatetime") else row.Date
            if not isinstance(timestamp, datetime):
                timestamp = datetime.now(timezone.utc)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            candles.append(
                Candle(
                    timestamp=timestamp,
                    open=float(row.Open),
                    high=float(row.High),
                    low=float(row.Low),
                    close=float(row.Close),
                    volume=float(row.Volume or 0.0),
                )
            )
        return candles

    def load(self, asset: AssetConfig) -> MarketDataBundle:
        metadata = {"source": "stooq", "stooq_symbol": self._stooq_symbol(asset.symbol)}
        daily_frame = self._fetch_daily_frame(asset.symbol, metadata)

        if daily_frame.empty:
            metadata["status"] = "empty"
            return MarketDataBundle(
                symbol=asset.symbol,
                asset_class=asset.asset_class,
                metadata=metadata,
            )

        daily = self._to_candles(daily_frame)
        weekly = self._to_candles(self._weekly_frame(daily_frame))
        return MarketDataBundle(
            symbol=asset.symbol,
            asset_class=asset.asset_class,
            candles={"D": daily, "W": weekly},
            last_price=float(daily[-1].close) if daily else None,
            metadata=metadata,
        )
