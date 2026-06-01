from __future__ import annotations

from shadow_v8.models import FundamentalState
from shadow_v8.utils import clamp, safe_mean


class GrowthEngine:
    def evaluate(
        self,
        revenue: list[float],
        eps: list[float],
        gross_margin: list[float] | None = None,
        operating_margin: list[float] | None = None,
        free_cash_flow: list[float] | None = None,
    ) -> FundamentalState:
        revenue_growth = self._growth_series(revenue)
        eps_growth = self._growth_series(eps)
        rev_accel = self._accelerating(revenue_growth)
        eps_accel = self._accelerating(eps_growth)
        gross_margin_expanding = self._margin_expanding(gross_margin or [])
        operating_margin_expanding = self._margin_expanding(operating_margin or [])
        fcf_positive = bool(free_cash_flow) and free_cash_flow[-1] > 0 and safe_mean(free_cash_flow[-4:]) > 0
        revenue_latest = (revenue_growth[-1:] or [0.0])[0]
        eps_latest = (eps_growth[-1:] or [0.0])[0]
        score = 0.0
        score += 28.0 if revenue_latest >= 25 else 20.0 if revenue_latest >= 15 else 10.0 if revenue_latest > 0 else 0.0
        score += 24.0 if rev_accel else 0.0
        score += 24.0 if eps_accel and eps_latest > 0 else 12.0 if eps_accel else 0.0
        score += 8.0 if gross_margin_expanding else 0.0
        score += 8.0 if operating_margin_expanding else 0.0
        score += 8.0 if fcf_positive else 0.0
        score = clamp(score, 0.0, 100.0)

        grade = "F"
        if score >= 90:
            grade = "S"
        elif score >= 75:
            grade = "A"
        elif score >= 60:
            grade = "B"
        elif score >= 40:
            grade = "C"
        return FundamentalState(
            revenue_growth_yoy=revenue_growth,
            eps_growth_yoy=eps_growth,
            revenue_accelerating=rev_accel,
            eps_accelerating=eps_accel,
            gross_margin_expanding=gross_margin_expanding,
            operating_margin_expanding=operating_margin_expanding,
            fcf_positive=fcf_positive,
            fundamental_grade=grade if revenue_growth or eps_growth else "UNKNOWN",
            reasons=[
                f"Latest revenue growth {revenue_latest:.1f}%",
                f"Latest EPS growth {eps_latest:.1f}%",
                "Revenue accelerating" if rev_accel else "Revenue not accelerating",
                "EPS accelerating" if eps_accel else "EPS not accelerating",
                "Gross margin expanding" if gross_margin_expanding else "Gross margin not expanding",
                "Operating margin expanding" if operating_margin_expanding else "Operating margin not expanding",
                "FCF positive" if fcf_positive else "FCF not positive",
            ],
        )

    def _growth_series(self, values: list[float]) -> list[float]:
        if len(values) < 5:
            return []
        growth: list[float] = []
        for idx in range(4, len(values)):
            old = values[idx - 4]
            new = values[idx]
            growth.append(((new - old) / abs(old)) * 100.0 if old else 0.0)
        return growth

    def _accelerating(self, growth: list[float]) -> bool:
        if len(growth) < 3:
            return False
        return growth[-1] > growth[-2] and growth[-2] >= growth[-3]

    def _margin_expanding(self, values: list[float]) -> bool:
        if len(values) < 4:
            return False
        return safe_mean(values[-2:]) > safe_mean(values[-4:-2])
