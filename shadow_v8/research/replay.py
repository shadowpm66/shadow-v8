from __future__ import annotations

from collections import Counter
from datetime import timezone, datetime
from typing import Any

from shadow_v8.context.stage_engine import StageEngine
from shadow_v8.context.zones import ContextEngine
from shadow_v8.models import AssetConfig, Candle
from shadow_v8.research.simulator import Simulator
from shadow_v8.strategy.entry_policy import EntryPolicy
from shadow_v8.strategy.risk_manager import RiskManager
from shadow_v8.strategy.scorer import Scorer
from shadow_v8.structure.base_engine import BaseEngine
from shadow_v8.structure.nested_structure import NestedStructureDetector
from shadow_v8.structure.pivot_confirmation import PivotConfirmationEngine
from shadow_v8.structure.vcp_engine import VcpEngine
from shadow_v8.structure.wm_detector import WmDetector


REPLAY_SCHEMA_VERSION = "1.3.0"


class Replay:
    def __init__(
        self,
        asset: AssetConfig,
        candles: list[Candle],
        min_bars: int = 60,
        input_source: dict[str, Any] | None = None,
        stage_engine: StageEngine | None = None,
        context_engine: ContextEngine | None = None,
        base_engine: BaseEngine | None = None,
        vcp_engine: VcpEngine | None = None,
        wm_detector: WmDetector | None = None,
        nested_detector: NestedStructureDetector | None = None,
        pivot_engine: PivotConfirmationEngine | None = None,
        scorer: Scorer | None = None,
        risk_manager: RiskManager | None = None,
        entry_policy: EntryPolicy | None = None,
        simulator: Simulator | None = None,
    ) -> None:
        self.asset = asset
        self.candles = candles
        self.min_bars = min_bars
        self.input_source = input_source or {}
        self.stage_engine = stage_engine or StageEngine()
        self.context_engine = context_engine or ContextEngine()
        self.base_engine = base_engine or BaseEngine()
        self.vcp_engine = vcp_engine or VcpEngine()
        self.wm_detector = wm_detector or WmDetector()
        self.nested_detector = nested_detector or NestedStructureDetector()
        self.pivot_engine = pivot_engine or PivotConfirmationEngine()
        self.scorer = scorer or Scorer()
        self.risk_manager = risk_manager or RiskManager()
        self.entry_policy = entry_policy or EntryPolicy()
        self.simulator = simulator or Simulator()

    def run(self) -> dict[str, Any]:
        skipped_setups: list[dict[str, Any]] = []
        action_counts: Counter[str] = Counter()
        bars_processed = 0

        for idx, candle in enumerate(self.candles):
            bars_processed += 1
            closed_trade = self.simulator.on_bar(candle)
            if idx + 1 < self.min_bars or closed_trade is not None:
                continue

            visible = self.candles[: idx + 1]
            stage = self.stage_engine.evaluate(visible, visible)
            structure = self.wm_detector.detect(visible)
            context = self.context_engine.evaluate(visible, structure.direction)
            base = self.base_engine.evaluate(visible, structure.direction)
            vcp = self.vcp_engine.evaluate(
                visible,
                pivot=base.pivot,
                direction=structure.direction,
                stop_distance_quality=str(base.metadata.get("stop_distance_quality", "UNKNOWN")) if base.metadata else "UNKNOWN",
            )
            nested = self.nested_detector.detect(visible)
            pivot = self.pivot_engine.evaluate(visible, structure.neckline or base.pivot, structure.direction)
            setup = self.scorer.score(
                symbol=self.asset.symbol,
                stage=stage,
                base=base,
                vcp=vcp,
                structure=structure,
                nested=nested,
                pivot=pivot,
                context=context,
            )
            risk = self.risk_manager.evaluate(self.asset, setup)
            entry = self.entry_policy.decide(self.asset, setup, risk)
            action_counts[entry.action] += 1
            confirmation = self._confirmation_summary(setup)

            if entry.action == "ENTER" and not self.simulator.has_open_position():
                if entry.entry is None:
                    entry.entry = candle.close
                if entry.stop is None:
                    entry.stop = self._synthetic_stop(candle, structure.direction)
                self.simulator.open_position(self.asset, entry, candle)
            elif entry.action != "ENTER":
                skipped_setups.append(
                    {
                        "timestamp": candle.timestamp.isoformat(),
                        "symbol": self.asset.symbol,
                        "action": entry.action,
                        "direction": entry.direction,
                        "reason": entry.reason,
                        "setup_class": setup.setup_class,
                        "grade": setup.grade,
                        "score": round(setup.final_score, 4),
                        "confirmation": confirmation,
                        "risk_state": risk.state,
                        "risk_reason": risk.reason,
                    }
                )

        if self.candles:
            self.simulator.close_open_at_end(self.candles[-1])

        summary = self.simulator.summary()
        trades = summary["trades"]
        metrics = self._build_metrics(trades, skipped_setups)
        breakdowns = self._build_breakdowns(trades, skipped_setups, action_counts)
        input_source = self._build_input_source()
        return {
            "schema_version": REPLAY_SCHEMA_VERSION,
            "ok": True,
            "symbol": self.asset.symbol,
            "asset_class": self.asset.asset_class,
            "timeframe": self.asset.primary_timeframe,
            "bars_processed": bars_processed,
            "run_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "engine": "shadow_v8.research.replay",
                "schema_version": REPLAY_SCHEMA_VERSION,
                "min_bars": self.min_bars,
            },
            "input_source": input_source,
            "metrics": metrics,
            "breakdowns": breakdowns,
            "skipped_setups": skipped_setups,
            "skipped_setup_count": len(skipped_setups),
            "trades": trades,
            "trade_count": metrics["total_trades"],
            "win_rate": metrics["win_rate"],
            "net_r": metrics["net_r"],
        }

    def _synthetic_stop(self, candle: Candle, direction: str) -> float:
        if direction == "SHORT":
            return candle.high
        return candle.low

    def _build_input_source(self) -> dict[str, Any]:
        first_timestamp = self.candles[0].timestamp.isoformat() if self.candles else None
        last_timestamp = self.candles[-1].timestamp.isoformat() if self.candles else None
        source = {
            "type": "in_memory",
            "symbol": self.asset.symbol,
            "asset_class": self.asset.asset_class,
            "timeframe": self.asset.primary_timeframe,
            "candle_count": len(self.candles),
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "min_bars": self.min_bars,
        }
        source.update(self.input_source)
        return source

    def _build_metrics(self, trades: list[dict[str, Any]], skipped_setups: list[dict[str, Any]]) -> dict[str, Any]:
        r_values = [float(trade.get("r_multiple", 0.0)) for trade in trades]
        wins = [value for value in r_values if value > 0]
        losses = [value for value in r_values if value < 0]
        total_trades = len(r_values)
        win_rate = len(wins) / total_trades if total_trades else 0.0
        average_win = self._average(wins)
        average_loss = self._average(losses)
        gross_win_r = sum(wins)
        gross_loss_r = abs(sum(losses))
        expectancy = (win_rate * average_win) + ((1.0 - win_rate) * average_loss) if total_trades else 0.0

        return {
            "total_trades": total_trades,
            "win_rate": self._round(win_rate),
            "net_r": self._round(sum(r_values)),
            "average_r": self._round(self._average(r_values)),
            "best_r": self._round(max(r_values)) if r_values else 0.0,
            "worst_r": self._round(min(r_values)) if r_values else 0.0,
            "max_drawdown_r": self._round(self._max_drawdown(r_values)),
            "profit_factor": self._round(gross_win_r / gross_loss_r) if gross_loss_r > 0 else None,
            "expectancy": self._round(expectancy),
            "average_win": self._round(average_win),
            "average_loss": self._round(average_loss),
            "average_trade_duration_bars": self._round(
                self._average([float(trade.get("duration_bars", 0)) for trade in trades])
            ),
            "average_trade_duration_seconds": self._round(
                self._average([float(trade.get("duration_seconds", 0.0)) for trade in trades])
            ),
            "skipped_setup_count": len(skipped_setups),
        }

    def _build_breakdowns(
        self,
        trades: list[dict[str, Any]],
        skipped_setups: list[dict[str, Any]],
        action_counts: Counter[str],
    ) -> dict[str, Any]:
        setup_counter: Counter[str] = Counter()
        grade_counter: Counter[str] = Counter()
        risk_state_counter: Counter[str] = Counter()

        for skipped in skipped_setups:
            setup_counter[str(skipped.get("setup_class") or "UNKNOWN")] += 1
            grade_counter[str(skipped.get("grade") or "UNKNOWN")] += 1
            risk_state_counter[str(skipped.get("risk_state") or "UNKNOWN")] += 1

        for trade in trades:
            setup_counter[str(trade.get("setup_class") or "UNKNOWN")] += 1
            grade_counter[str(trade.get("grade") or "UNKNOWN")] += 1

        return {
            "action_counts": dict(sorted(action_counts.items())),
            "setup_breakdown": dict(sorted(setup_counter.items())),
            "grade_breakdown": dict(sorted(grade_counter.items())),
            "risk_state_breakdown": dict(sorted(risk_state_counter.items())),
        }

    def _average(self, values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _max_drawdown(self, r_values: list[float]) -> float:
        peak = 0.0
        equity = 0.0
        max_drawdown = 0.0
        for value in r_values:
            equity += value
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
        return max_drawdown

    def _round(self, value: float) -> float:
        return round(float(value), 6)

    def _confirmation_summary(self, setup) -> dict[str, Any]:
        return {
            "base": setup.metadata.get("base_confirmation", {}),
            "vcp": setup.metadata.get("vcp_confirmation", {}),
            "pivot": setup.metadata.get("pivot_confirmation", {}),
            "nested": setup.metadata.get("nested_confirmation", {}),
            "context": setup.metadata.get("context_confluence", {}),
            "stop_distance_quality": setup.metadata.get("stop_distance_quality", "UNKNOWN"),
        }
