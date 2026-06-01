from __future__ import annotations

from shadow_v8.models import AssetConfig, MarketDataBundle


class MarketDataProvider:
    def load(self, asset: AssetConfig) -> MarketDataBundle:
        raise NotImplementedError


class CompositeMarketData:
    def __init__(self, providers: dict[str, MarketDataProvider]) -> None:
        self.providers = providers

    def load(self, asset: AssetConfig) -> MarketDataBundle:
        provider = self.providers.get(asset.broker)
        if provider is None:
            return MarketDataBundle(symbol=asset.symbol, asset_class=asset.asset_class)
        return provider.load(asset)

