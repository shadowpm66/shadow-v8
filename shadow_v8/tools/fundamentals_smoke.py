from __future__ import annotations

import argparse
import json

from shadow_v8.fundamentals.growth_engine import GrowthEngine
from shadow_v8.fundamentals.sec_company_facts import SecCompanyFactsClient


def run(symbol: str, periods: int = 12) -> dict:
    client = SecCompanyFactsClient()
    inputs = client.get_growth_inputs(symbol, periods=periods)
    state = GrowthEngine().evaluate(
        revenue=inputs.revenue,
        eps=inputs.eps,
        gross_margin=inputs.gross_margin,
        operating_margin=inputs.operating_margin,
        free_cash_flow=inputs.free_cash_flow,
    )
    return {
        "symbol": inputs.symbol,
        "cik": inputs.cik,
        "source": inputs.metadata.get("source"),
        "revenue_periods": len(inputs.revenue),
        "eps_periods": len(inputs.eps),
        "gross_margin_periods": len(inputs.gross_margin),
        "operating_margin_periods": len(inputs.operating_margin),
        "free_cash_flow_periods": len(inputs.free_cash_flow),
        "fundamental_grade": state.fundamental_grade,
        "revenue_accelerating": state.revenue_accelerating,
        "eps_accelerating": state.eps_accelerating,
        "reasons": state.reasons,
        "metadata": inputs.metadata,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch SEC fundamentals and run Shadow v8 growth scoring")
    parser.add_argument("symbol", help="US stock ticker, for example NVDA or MSFT")
    parser.add_argument("--periods", type=int, default=12, help="Quarterly periods to fetch")
    args = parser.parse_args()

    try:
        print(json.dumps(run(args.symbol, periods=args.periods), indent=2))
    except Exception as exc:
        print(json.dumps({"ok": False, "symbol": args.symbol.upper(), "error": str(exc)}, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
