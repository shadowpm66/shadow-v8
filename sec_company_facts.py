from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import os
from typing import Any

import requests


@dataclass(frozen=True)
class SecGrowthInputs:
    symbol: str
    cik: int
    revenue: list[float] = field(default_factory=list)
    eps: list[float] = field(default_factory=list)
    gross_margin: list[float] = field(default_factory=list)
    operating_margin: list[float] = field(default_factory=list)
    free_cash_flow: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class SecCompanyFactsClient:
    """Fetch quarterly stock fundamentals from official SEC Company Facts.

    The client converts a stock ticker to CIK, fetches SEC XBRL company facts,
    and extracts quarterly revenue, EPS, margin, and FCF inputs for GrowthEngine.
    """

    TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
    FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

    # Static fallback for our default growth-stock universe. Some cloud IP ranges
    # are intermittently denied by www.sec.gov for the ticker map endpoint, while
    # data.sec.gov company facts still works when called directly by CIK.
    FALLBACK_CIKS = {
        "NVDA": 1045810,
        "MSFT": 789019,
        "AMZN": 1018724,
        "META": 1326801,
        "AVGO": 1730168,
        "LLY": 59478,
        "TSLA": 1318605,
        "PLTR": 1321655,
        "CRWD": 1535527,
        "ANET": 1596532,
        "SMCI": 1375365,
        "AAPL": 320193,
        "GOOGL": 1652044,
        "GOOG": 1652044,
        "AMD": 2488,
        "NFLX": 1065280,
        "COST": 909832,
        "ORCL": 1341439,
        "ADBE": 796343,
        "CRM": 1108524,
        "NOW": 1373715,
        "PANW": 1327567,
        "SHOP": 1594805,
    }

    REVENUE_TAGS = (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
    )
    EPS_TAGS = ("EarningsPerShareDiluted", "EarningsPerShareBasic")
    GROSS_PROFIT_TAGS = ("GrossProfit",)
    OPERATING_INCOME_TAGS = ("OperatingIncomeLoss",)
    OPERATING_CASH_FLOW_TAGS = (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    )
    CAPEX_TAGS = ("PaymentsToAcquirePropertyPlantAndEquipment",)

    def __init__(
        self,
        user_agent: str | None = None,
        timeout: int = 20,
        session: requests.Session | None = None,
    ) -> None:
        self.user_agent = (
            user_agent
            or os.getenv("SEC_USER_AGENT")
            or "Shadow v8 research contact@example.com"
        )
        self.timeout = timeout
        self.session = session or requests.Session()
        self._ticker_map: dict[str, int] | None = None

    def get_growth_inputs(self, symbol: str, periods: int = 12) -> SecGrowthInputs:
        ticker = self._normalize_symbol(symbol)
        cik = self.ticker_to_cik(ticker)
        facts = self.company_facts(cik)

        revenue_points = self._quarterly_points(
            facts, self.REVENUE_TAGS, unit_hints=("USD",), periods=periods
        )
        eps_points = self._quarterly_points(
            facts, self.EPS_TAGS, unit_hints=("USD/shares", "USD / shares"), periods=periods
        )
        gross_points = self._quarterly_points(
            facts, self.GROSS_PROFIT_TAGS, unit_hints=("USD",), periods=periods
        )
        operating_points = self._quarterly_points(
            facts, self.OPERATING_INCOME_TAGS, unit_hints=("USD",), periods=periods
        )
        cfo_points = self._quarterly_points(
            facts, self.OPERATING_CASH_FLOW_TAGS, unit_hints=("USD",), periods=periods
        )
        capex_points = self._quarterly_points(
            facts, self.CAPEX_TAGS, unit_hints=("USD",), periods=periods
        )

        revenue = [p["val"] for p in revenue_points]
        eps = [p["val"] for p in eps_points]
        gross_margin = self._ratio_series(gross_points, revenue_points)
        operating_margin = self._ratio_series(operating_points, revenue_points)
        free_cash_flow = self._free_cash_flow(cfo_points, capex_points)

        return SecGrowthInputs(
            symbol=ticker,
            cik=cik,
            revenue=revenue,
            eps=eps,
            gross_margin=gross_margin,
            operating_margin=operating_margin,
            free_cash_flow=free_cash_flow,
            metadata={
                "source": "sec_company_facts",
                "revenue_periods": len(revenue),
                "eps_periods": len(eps),
                "last_revenue_period": revenue_points[-1]["end"] if revenue_points else None,
                "last_eps_period": eps_points[-1]["end"] if eps_points else None,
            },
        )

    def get_quarterly_revenue(self, symbol: str) -> list[float]:
        return self.get_growth_inputs(symbol).revenue

    def get_quarterly_eps(self, symbol: str) -> list[float]:
        return self.get_growth_inputs(symbol).eps

    def ticker_to_cik(self, symbol: str) -> int:
        ticker = self._normalize_symbol(symbol)
        if ticker in self.FALLBACK_CIKS:
            return self.FALLBACK_CIKS[ticker]
        ticker_map = self._load_ticker_map()
        if ticker not in ticker_map:
            raise ValueError(f"No SEC CIK mapping found for ticker {ticker}")
        return ticker_map[ticker]

    def company_facts(self, cik: int) -> dict[str, Any]:
        return self._get_json(self.FACTS_URL.format(cik=int(cik)))

    def _load_ticker_map(self) -> dict[str, int]:
        if self._ticker_map is not None:
            return self._ticker_map
        try:
            payload = self._get_json(self.TICKER_URL)
        except requests.RequestException:
            self._ticker_map = dict(self.FALLBACK_CIKS)
            return self._ticker_map
        ticker_map: dict[str, int] = {}
        for item in payload.values():
            ticker = self._normalize_symbol(str(item.get("ticker", "")))
            cik = item.get("cik_str")
            if ticker and cik is not None:
                ticker_map[ticker] = int(cik)
        ticker_map.update(self.FALLBACK_CIKS)
        self._ticker_map = ticker_map
        return ticker_map

    def _get_json(self, url: str) -> dict[str, Any]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close",
        }
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _quarterly_points(
        self,
        facts: dict[str, Any],
        tags: tuple[str, ...],
        unit_hints: tuple[str, ...],
        periods: int = 12,
    ) -> list[dict[str, Any]]:
        gaap = ((facts.get("facts") or {}).get("us-gaap") or {})
        points: list[dict[str, Any]] = []
        for tag in tags:
            fact = gaap.get(tag)
            if not fact:
                continue
            units = fact.get("units") or {}
            for unit_name, rows in self._preferred_units(units, unit_hints):
                for row in rows:
                    point = self._row_to_quarterly_point(row, tag, unit_name)
                    if point is not None:
                        points.append(point)
            if points:
                break
        return self._dedupe_and_tail(points, periods)

    def _preferred_units(
        self, units: dict[str, list[dict[str, Any]]], hints: tuple[str, ...]
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        preferred = [(name, units[name]) for name in hints if name in units]
        if preferred:
            return preferred
        return list(units.items())

    def _row_to_quarterly_point(
        self, row: dict[str, Any], tag: str, unit_name: str
    ) -> dict[str, Any] | None:
        value = row.get("val")
        end = row.get("end")
        if value is None or not end:
            return None
        form = str(row.get("form") or "")
        if form not in {"10-Q", "10-Q/A", "10-K", "10-K/A"}:
            return None
        if not self._looks_quarterly(row):
            return None
        if self._duration_days(row) > 140:
            return None
        try:
            return {
                "end": str(end),
                "filed": str(row.get("filed") or ""),
                "val": float(value),
                "tag": tag,
                "unit": unit_name,
                "form": form,
            }
        except (TypeError, ValueError):
            return None

    def _looks_quarterly(self, row: dict[str, Any]) -> bool:
        fp = str(row.get("fp") or "").upper()
        frame = str(row.get("frame") or "").upper()
        return fp in {"Q1", "Q2", "Q3", "Q4"} or "Q" in frame

    def _duration_days(self, row: dict[str, Any]) -> int:
        start = row.get("start")
        end = row.get("end")
        if not start or not end:
            return 0
        try:
            return (datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))).days
        except ValueError:
            return 0

    def _dedupe_and_tail(self, points: list[dict[str, Any]], periods: int) -> list[dict[str, Any]]:
        by_end: dict[str, dict[str, Any]] = {}
        for point in sorted(points, key=lambda p: (p["end"], p.get("filed") or "")):
            by_end[point["end"]] = point
        return list(by_end.values())[-periods:]

    def _ratio_series(
        self, numerator: list[dict[str, Any]], denominator: list[dict[str, Any]]
    ) -> list[float]:
        den_by_end = {p["end"]: p["val"] for p in denominator}
        out: list[float] = []
        for point in numerator:
            den = den_by_end.get(point["end"])
            if den:
                out.append((point["val"] / den) * 100.0)
        return out

    def _free_cash_flow(
        self, cfo: list[dict[str, Any]], capex: list[dict[str, Any]]
    ) -> list[float]:
        capex_by_end = {p["end"]: p["val"] for p in capex}
        out: list[float] = []
        for point in cfo:
            capex_val = capex_by_end.get(point["end"])
            if capex_val is not None:
                out.append(point["val"] - abs(capex_val))
        return out

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper().replace(".", "-")
