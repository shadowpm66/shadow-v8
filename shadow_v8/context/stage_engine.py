from __future__ import annotations

from shadow_v8.models import Candle, Stage, StageState
from shadow_v8.structure.indicators import closes, highs, lows, sma


class StageEngine:
    def __init__(
        self,
        weekly_ma: int = 30,
        daily_ma: int = 50,
        long_weekly_stages: tuple[Stage, ...] | None = None,
        short_weekly_stages: tuple[Stage, ...] | None = None,
        long_daily_stages: tuple[Stage, ...] | None = None,
        short_daily_stages: tuple[Stage, ...] | None = None,
    ) -> None:
        self.weekly_ma = weekly_ma
        self.daily_ma = daily_ma
        self.long_weekly_stages = long_weekly_stages or (Stage.STAGE_2,)
        self.short_weekly_stages = short_weekly_stages or (Stage.STAGE_4,)
        self.long_daily_stages = long_daily_stages or (Stage.STAGE_2, Stage.STAGE_1, Stage.UNKNOWN)
        self.short_daily_stages = short_daily_stages or (Stage.STAGE_4, Stage.STAGE_3, Stage.UNKNOWN)

    def evaluate(self, weekly: list[Candle], daily: list[Candle] | None = None) -> StageState:
        weekly_stage, weekly_reasons = self._stage_for(weekly, period=self.weekly_ma, label="Weekly")
        daily_stage, daily_reasons = self._stage_for(daily or [], period=self.daily_ma, label="Daily")
        long_weekly_compatible = weekly_stage in self.long_weekly_stages
        short_weekly_compatible = weekly_stage in self.short_weekly_stages
        long_daily_compatible = daily_stage in self.long_daily_stages
        short_daily_compatible = daily_stage in self.short_daily_stages
        long_permission = long_weekly_compatible and long_daily_compatible
        short_permission = short_weekly_compatible and short_daily_compatible
        if weekly_stage == Stage.STAGE_2 and daily_stage == Stage.STAGE_2:
            risk_bias = "RISK_ON"
        elif weekly_stage == Stage.STAGE_4:
            risk_bias = "OFF" if daily_stage == Stage.STAGE_4 else "DEFENSIVE"
        elif weekly_stage in (Stage.STAGE_1, Stage.STAGE_3):
            risk_bias = "DEFENSIVE"
        else:
            risk_bias = "NEUTRAL"
        return StageState(
            weekly_stage=weekly_stage,
            daily_stage=daily_stage,
            long_weekly_compatible=long_weekly_compatible,
            short_weekly_compatible=short_weekly_compatible,
            long_daily_compatible=long_daily_compatible,
            short_daily_compatible=short_daily_compatible,
            long_permission=long_permission,
            short_permission=short_permission,
            risk_bias=risk_bias,
            reasons=[
                *weekly_reasons,
                *daily_reasons,
                "Long permission" if long_permission else "No long permission",
                "Short permission" if short_permission else "No short permission",
                f"Risk bias {risk_bias}",
            ],
        )

    def _stage_for(self, candles: list[Candle], period: int, label: str) -> tuple[Stage, list[str]]:
        if len(candles) < period + 5:
            return Stage.UNKNOWN, [f"{label} stage unknown: not enough candles"]
        values = closes(candles)
        ma_now = sma(values, period)
        ma_prev = sum(values[-period - 5 : -5]) / period
        price = values[-1]
        if ma_now is None:
            return Stage.UNKNOWN, [f"{label} stage unknown: no moving average"]
        slope_up = ma_now > ma_prev
        slope_down = ma_now < ma_prev
        high_lookback = max(highs(candles[-period:]))
        low_lookback = min(lows(candles[-period:]))
        near_high = price >= high_lookback * 0.85
        near_low = price <= low_lookback * 1.15
        stage = Stage.STAGE_1
        if price > ma_now and slope_up and near_high:
            stage = Stage.STAGE_2
        elif price < ma_now and slope_down and near_low:
            stage = Stage.STAGE_4
        elif price > ma_now and slope_down:
            stage = Stage.STAGE_3
        elif price < ma_now and slope_up:
            stage = Stage.STAGE_1
        return stage, [
            f"{label} {stage.value}",
            f"{label} price {'above' if price > ma_now else 'below'} MA{period}",
            f"{label} MA slope {'up' if slope_up else 'down' if slope_down else 'flat'}",
        ]
