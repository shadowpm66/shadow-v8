from __future__ import annotations

from shadow_v8.config import STOCK_SCAN_CONFIG
from shadow_v8.data.bybit_market_data import BybitMarketData
from shadow_v8.data.scanner import StockScanner
from shadow_v8.main import _evaluate_stock_asset, _stock_market_provider


def main() -> None:
    assets = StockScanner().scan(STOCK_SCAN_CONFIG)
    print(f"Stock universe: {[asset.symbol for asset in assets]}")
    bybit = BybitMarketData()
    stock_provider = _stock_market_provider()
    for asset in assets:
        result = _evaluate_stock_asset(asset, bybit, stock_provider)
        setup = result["setup"]
        entry = result["entry"]
        risk = result["risk"]
        market = result["market"]
        fundamentals = result.get("fundamentals")
        earnings = result.get("earnings")
        print(
            f"{asset.symbol} action={entry.action} grade={setup.grade} "
            f"score={setup.final_score:.1f} "
            f"fund={getattr(fundamentals, 'fundamental_grade', '-')} "
            f"earnings_blocked={getattr(earnings, 'blocked_for_earnings', '-')} "
            f"risk={risk.state} source={market.metadata.get('source')} "
            f"reason={entry.reason}"
        )


if __name__ == "__main__":
    main()
