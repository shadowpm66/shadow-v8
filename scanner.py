from __future__ import annotations

from shadow_v8.models import AssetConfig, ScannerConfig
from shadow_v8.data.bybit_market_data import BybitMarketData


class StockScanner:
    """Configurable stock universe scanner.

    This is intentionally selection-only for now. It creates stock candidates for
    the strategy/fundamental engines, while execution stays paper/disabled until
    a stock broker route is explicitly enabled.
    """

    def scan(self, config: dict | ScannerConfig) -> list[AssetConfig]:
        if isinstance(config, ScannerConfig):
            enabled = config.enabled
            max_symbols = config.max_results
            symbols: list[str] = []
            allow_short = False
            risk_pct = 0.015
        else:
            enabled = bool(config.get("enabled", True))
            max_symbols = int(config.get("max_symbols") or 25)
            symbols = list(config.get("seed_symbols") or [])
            allow_short = bool(config.get("allow_short", False))
            risk_pct = float(config.get("default_risk_pct") or 0.015)

        if not enabled:
            return []

        clean_symbols = [symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()]
        clean_symbols = list(dict.fromkeys(clean_symbols))[:max_symbols]
        return [
            AssetConfig(
                symbol=symbol,
                asset_class="stock",
                broker="paper",
                enabled=True,
                primary_timeframe="D",
                confirmation_timeframe="W",
                intraday_timeframes=(),
                allow_long=True,
                allow_short=allow_short,
                fundamentals_required=True,
                max_risk_pct=risk_pct,
                tags=("stock_scan", "sec_fundamentals"),
            )
            for symbol in clean_symbols
        ]


class CryptoScanner:
    def __init__(self, bybit: BybitMarketData | None = None) -> None:
        self.bybit = bybit or BybitMarketData()

    def scan(self, config: dict) -> list[AssetConfig]:
        if not config.get("enabled", True):
            return []
        max_symbols = int(config.get("max_symbols") or 25)
        if config.get("scan_all_usdt", False):
            symbols = self.bybit.list_linear_usdt_symbols(max_symbols=max_symbols)
        else:
            symbols = list(config.get("seed_symbols") or [])
        symbols = [s.strip().upper() for s in symbols if s and s.strip()]
        symbols = list(dict.fromkeys(symbols))[:max_symbols]
        return [
            AssetConfig(
                symbol=symbol,
                asset_class="crypto",
                broker="bybit",
                enabled=True,
                primary_timeframe="D",
                confirmation_timeframe="W",
                intraday_timeframes=(),
                allow_long=True,
                allow_short=True,
                fundamentals_required=False,
                max_risk_pct=0.03,
                tags=("crypto_scan",),
            )
            for symbol in symbols
        ]
