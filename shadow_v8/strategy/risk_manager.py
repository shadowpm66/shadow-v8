from __future__ import annotations

from shadow_v8.models import AssetConfig, RiskDecision, SetupDecision


CRYPTO_FOREX_MAX_RISK_PCT = 0.03
CRYPTO_FOREX_RISK_TIERS = {
    "B": 0.005,
    "B+": 0.01,
    "A": 0.015,
    "A+": 0.02,
    "S": 0.025,
    "S+": 0.03,
}

STOCK_POSITION_TIERS = {
    "B": 0.15,
    "B+": 0.15,
    "A": 0.20,
    "A+": 0.25,
    "S": 0.25,
    "S+": 0.25,
}
STOCK_NORMAL_MAX_ACCOUNT_RISK_PCT = 0.015
STOCK_IDEAL_STOP_MIN_PCT = 2.5
STOCK_IDEAL_STOP_MAX_PCT = 5.0


class RiskManager:
    def evaluate(self, asset: AssetConfig, setup: SetupDecision) -> RiskDecision:
        if setup.grade == "REJECT":
            return RiskDecision(state="OFF", risk_pct=0.0, reason="Rejected setup")
        if asset.asset_class == "stock":
            return self._evaluate_stock(setup)
        if asset.asset_class in ("crypto", "forex", "commodity", "tokenized_stock"):
            return self._evaluate_risk_tier(asset, setup)
        return RiskDecision(state="OFF", risk_pct=0.0, reason="Low-grade setup")

    def _evaluate_risk_tier(self, asset: AssetConfig, setup: SetupDecision) -> RiskDecision:
        tier_risk = CRYPTO_FOREX_RISK_TIERS.get(setup.grade)
        if tier_risk is None:
            return RiskDecision(state="OFF", risk_pct=0.0, reason="Low-grade setup")
        risk_pct = min(tier_risk, CRYPTO_FOREX_MAX_RISK_PCT)
        state = "FULL" if setup.grade in ("A+", "S", "S+") else "REDUCED" if setup.grade == "A" else "DEFENSIVE"
        return RiskDecision(
            state=state,
            risk_pct=risk_pct,
            reason=f"{setup.grade} {asset.asset_class} risk tier",
            metadata={
                "sizing_model": "risk_pct",
                "risk_tier_pct": tier_risk,
                "max_asset_risk_pct": asset.max_risk_pct,
                "hard_cap_pct": CRYPTO_FOREX_MAX_RISK_PCT,
            },
        )

    def _evaluate_stock(self, setup: SetupDecision) -> RiskDecision:
        position_pct = STOCK_POSITION_TIERS.get(setup.grade)
        if position_pct is None:
            return RiskDecision(state="OFF", risk_pct=0.0, reason="Low-grade stock setup")

        stop_distance_pct = self._stop_distance_pct(setup)
        stop_fraction = (stop_distance_pct / 100.0) if stop_distance_pct is not None else None
        account_risk_pct = position_pct * stop_fraction if stop_fraction is not None else 0.0
        wide_structure_risk = stop_distance_pct is not None and stop_distance_pct > STOCK_IDEAL_STOP_MAX_PCT
        below_ideal_stop = stop_distance_pct is not None and stop_distance_pct < STOCK_IDEAL_STOP_MIN_PCT

        adjusted_position_pct = position_pct
        reduced_for_account_risk = False
        if stop_fraction and account_risk_pct > STOCK_NORMAL_MAX_ACCOUNT_RISK_PCT:
            adjusted_position_pct = STOCK_NORMAL_MAX_ACCOUNT_RISK_PCT / stop_fraction
            account_risk_pct = adjusted_position_pct * stop_fraction
            reduced_for_account_risk = True

        state = "FULL" if setup.grade in ("A+", "S", "S+") else "REDUCED" if setup.grade == "A" else "DEFENSIVE"
        reason_bits = [f"{setup.grade} stock allocation tier"]
        if wide_structure_risk:
            reason_bits.append("wide_structure_risk")
        if reduced_for_account_risk:
            reason_bits.append("reduced to 1.5% account risk cap")
        if below_ideal_stop:
            reason_bits.append("stop tighter than ideal stock structure range")

        return RiskDecision(
            state=state,
            risk_pct=round(account_risk_pct, 6),
            reason="; ".join(reason_bits),
            metadata={
                "sizing_model": "stock_allocation",
                "position_pct": round(adjusted_position_pct, 6),
                "base_position_pct": position_pct,
                "account_risk_pct": round(account_risk_pct, 6),
                "stop_distance_pct": stop_distance_pct,
                "ideal_stop_min_pct": STOCK_IDEAL_STOP_MIN_PCT,
                "ideal_stop_max_pct": STOCK_IDEAL_STOP_MAX_PCT,
                "wide_structure_risk": wide_structure_risk,
                "reduced_for_account_risk": reduced_for_account_risk,
            },
        )

    def _stop_distance_pct(self, setup: SetupDecision) -> float | None:
        candidates = [
            setup.metadata.get("stop_distance_pct"),
            (setup.metadata.get("base_confirmation") or {}).get("stop_distance_pct"),
            (setup.metadata.get("vcp_confirmation") or {}).get("stop_distance_pct"),
        ]
        for value in candidates:
            if value is None:
                continue
            try:
                return abs(float(value))
            except (TypeError, ValueError):
                continue
        return None
