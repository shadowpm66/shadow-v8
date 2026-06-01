from __future__ import annotations

from shadow_v8.data.market_data import MarketDataProvider
from shadow_v8.models import AssetConfig, MarketDataBundle


class IbkrMarketData(MarketDataProvider):
    """Placeholder for IBKR market data.

    Phase one keeps stocks in scan/alert mode until IB Gateway is configured.
    """

    def load(self, asset: AssetConfig) -> MarketDataBundle:
        return MarketDataBundle(
            symbol=asset.symbol,
            asset_class=asset.asset_class,
            metadata={"status": "IBKR market data adapter not configured yet"},
        )

