from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shadow_v8.config import PATHS, RISK_CONFIG, ensure_runtime_dirs
from shadow_v8.state_store import ClosedTradeStore, PositionStore


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "value"):
        return value.value
    return str(value)


class DashboardWriter:
    def write_scan(self, scan_results: list[dict[str, Any]]) -> None:
        rows = [self._scan_row(rank, result) for rank, result in enumerate(scan_results, start=1)]
        self._write_json(
            PATHS["dashboard_scan"],
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "count": len(rows),
                "results": rows,
            },
        )
        if rows:
            self._write_json(PATHS["dashboard_latest"], {"generated_at": datetime.now(timezone.utc).isoformat(), "top": rows[0]})
        self.write_decisions(scan_results)

    def write_risk(self, scan_results: list[dict[str, Any]]) -> None:
        risk_rows = []
        for result in scan_results:
            asset = result["asset"]
            market = result["market"]
            setup = result["setup"]
            risk = result["risk"]
            fundamentals = result.get("fundamentals")
            earnings = result.get("earnings")
            risk_metadata = risk.metadata or {}
            risk_rows.append(
                {
                    "symbol": setup.symbol,
                    "asset_class": asset.asset_class,
                    "data_source": market.metadata.get("source"),
                    "direction": setup.direction,
                    "grade": setup.grade,
                    "score": round(setup.final_score, 2),
                    "fundamental_grade": getattr(fundamentals, "fundamental_grade", None),
                    "earnings_blocked": getattr(earnings, "blocked_for_earnings", None),
                    "earnings_days": getattr(earnings, "days_until_earnings", None),
                    "risk_state": risk.state,
                    "risk_pct": risk.risk_pct,
                    "sizing_model": risk_metadata.get("sizing_model"),
                    "position_pct": risk_metadata.get("position_pct"),
                    "stop_distance_pct": risk_metadata.get("stop_distance_pct"),
                    "wide_structure_risk": risk_metadata.get("wide_structure_risk"),
                    "reason": risk.reason,
                }
            )
        positions = self._position_rows()
        closed_trades = self._closed_trade_rows()
        self._write_json(
            PATHS["dashboard_risk"],
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "limits": RISK_CONFIG,
                "positions": positions,
                "closed_trades": closed_trades,
                "scan_risk": risk_rows,
                "summary": self._risk_summary(risk_rows, positions, closed_trades),
            },
        )

    def write_status(
        self,
        *,
        cycle_started_at: datetime,
        cycle_finished_at: datetime,
        duration_sec: float,
        scan_count: int,
        mode: str,
        live_trading_enabled: bool,
        entries_paused: bool = False,
        execution_preflight: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self._write_json(
            PATHS["dashboard_status"],
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "cycle_started_at": cycle_started_at.isoformat(),
                "cycle_finished_at": cycle_finished_at.isoformat(),
                "duration_sec": round(duration_sec, 3),
                "scan_count": scan_count,
                "mode": mode,
                "live_trading_enabled": live_trading_enabled,
                "entries_paused": entries_paused,
                "execution_preflight": execution_preflight or {},
                "health": "OK" if not errors else "WARN",
                "errors": errors or [],
            },
        )

    def write_decisions(self, scan_results: list[dict[str, Any]], max_rows: int = 50) -> None:
        existing = self._read_json(PATHS["dashboard_decisions"], {"decisions": []})
        rows = existing.get("decisions") or []
        now = datetime.now(timezone.utc).isoformat()
        new_rows = [self._decision_row(now, result) for result in scan_results]
        rows = (new_rows + rows)[:max_rows]
        self._write_json(
            PATHS["dashboard_decisions"],
            {"generated_at": now, "count": len(rows), "decisions": rows},
        )

    def _scan_row(self, rank: int, result: dict[str, Any]) -> dict[str, Any]:
        setup = result["setup"]
        stage = result["stage"]
        base = result["base"]
        vcp = result["vcp"]
        structure = result["structure"]
        context = result.get("context")
        nested = result["nested"]
        pivot = result["pivot"]
        entry = result["entry"]
        risk = result["risk"]
        risk_metadata = risk.metadata or {}
        trade_gate = setup.metadata.get("trade_gate") or {}
        market = result["market"]
        fundamentals = result.get("fundamentals")
        earnings = result.get("earnings")
        reference_confluence = (context.metadata or {}).get("reference_confluence", {}) if context else {}
        return {
            "rank": rank,
            "symbol": setup.symbol,
            "asset_class": result["asset"].asset_class,
            "last_price": market.last_price,
            "data_source": market.metadata.get("source"),
            "action": entry.action,
            "entry_reason": entry.reason,
            "direction": setup.direction,
            "setup_class": setup.setup_class,
            "grade": setup.grade,
            "score": round(setup.final_score, 2),
            "technical_score": round(setup.technical_score, 2),
            "weekly_stage": stage.weekly_stage.value,
            "daily_stage": stage.daily_stage.value,
            "risk_bias": stage.risk_bias,
            "base_found": base.found,
            "base_quality": round(base.quality_score, 2),
            "base_depth_pct": round(base.depth_pct, 2) if base.depth_pct is not None else None,
            "vcp_tight": vcp.is_tight,
            "vcp_score": round(vcp.tightness_score, 2),
            "vcp_contractions": vcp.contraction_count,
            "structure_type": structure.type,
            "structure_score": round(structure.quality_score, 2),
            "context_score": round(context.quality_score, 2) if context else None,
            "nearest_reference": (reference_confluence.get("nearest_reference") or {}).get("name"),
            "reference_flags": reference_confluence.get("flags", []),
            "nested_pattern": nested.pattern,
            "nested_confirmed": nested.confirmed,
            "pivot_confirmed": pivot.confirmed,
            "pivot_retested": pivot.retested,
            "pivot_shift_away": pivot.shift_away,
            "fundamental_grade": getattr(fundamentals, "fundamental_grade", None),
            "revenue_accelerating": getattr(fundamentals, "revenue_accelerating", None),
            "eps_accelerating": getattr(fundamentals, "eps_accelerating", None),
            "earnings_blocked": getattr(earnings, "blocked_for_earnings", None),
            "earnings_days": getattr(earnings, "days_until_earnings", None),
            "risk_state": risk.state,
            "risk_pct": risk.risk_pct,
            "position_pct": risk_metadata.get("position_pct"),
            "stop_distance_pct": risk_metadata.get("stop_distance_pct"),
            "wide_structure_risk": risk_metadata.get("wide_structure_risk"),
            "gate_status": trade_gate.get("status"),
            "gate_blockers": trade_gate.get("blockers", []),
            "gate_warnings": trade_gate.get("warnings", []),
            "reasons": setup.reasons,
        }

    def _decision_row(self, timestamp: str, result: dict[str, Any]) -> dict[str, Any]:
        asset = result["asset"]
        setup = result["setup"]
        entry = result["entry"]
        risk = result["risk"]
        trade_gate = setup.metadata.get("trade_gate") or {}
        pivot = result["pivot"]
        vcp = result["vcp"]
        context = result.get("context")
        reference_confluence = (context.metadata or {}).get("reference_confluence", {}) if context else {}
        fundamentals = result.get("fundamentals")
        earnings = result.get("earnings")
        return {
            "timestamp": timestamp,
            "symbol": setup.symbol,
            "asset_class": asset.asset_class,
            "action": entry.action,
            "grade": setup.grade,
            "score": round(setup.final_score, 2),
            "direction": setup.direction,
            "risk_state": risk.state,
            "gate_status": trade_gate.get("status"),
            "gate_blockers": trade_gate.get("blockers", []),
            "reason": entry.reason,
            "fundamental_grade": getattr(fundamentals, "fundamental_grade", None),
            "earnings_blocked": getattr(earnings, "blocked_for_earnings", None),
            "earnings_days": getattr(earnings, "days_until_earnings", None),
            "pivot_confirmed": pivot.confirmed,
            "vcp_score": round(vcp.tightness_score, 2),
            "context_score": round(context.quality_score, 2) if context else None,
            "nearest_reference": (reference_confluence.get("nearest_reference") or {}).get("name"),
            "reference_flags": reference_confluence.get("flags", []),
        }

    def _position_rows(self) -> list[dict[str, Any]]:
        raw = PositionStore().load_all()
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = list(raw.values())
        else:
            items = []
        rows = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "symbol": item.get("symbol"),
                    "asset_class": item.get("asset_class"),
                    "broker": item.get("broker"),
                    "direction": item.get("direction"),
                    "qty": item.get("qty"),
                    "entry": item.get("entry"),
                    "stop": item.get("stop"),
                    "grade": item.get("grade"),
                    "setup_class": item.get("setup_class"),
                    "opened_at": item.get("opened_at"),
                    "unrealized_r": item.get("unrealized_r"),
                    "unrealized_pnl": item.get("unrealized_pnl"),
                    "realized_r": item.get("realized_r"),
                    "realized_pnl": item.get("realized_pnl"),
                    "mfe_r": item.get("mfe_r"),
                    "mae_r": item.get("mae_r"),
                    "target": item.get("target"),
                    "risk_pct": item.get("risk_pct"),
                    "position_pct": item.get("position_pct"),
                    "stop_distance_pct": item.get("stop_distance_pct"),
                    "partial_taken": item.get("partial_taken"),
                    "break_even_moved": item.get("break_even_moved"),
                }
            )
        return rows

    def _closed_trade_rows(self) -> list[dict[str, Any]]:
        rows = []
        for item in ClosedTradeStore().load_all()[:50]:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "symbol": item.get("symbol"),
                    "direction": item.get("direction"),
                    "entry": item.get("entry"),
                    "exit": item.get("exit"),
                    "grade": item.get("grade"),
                    "exit_reason": item.get("exit_reason"),
                    "realized_pnl": item.get("realized_pnl"),
                    "r_multiple": item.get("r_multiple"),
                    "mfe_r": item.get("mfe_r"),
                    "mae_r": item.get("mae_r"),
                    "closed_at": item.get("closed_at"),
                    "partial_taken": item.get("partial_taken"),
                    "break_even_moved": item.get("break_even_moved"),
                }
            )
        return rows

    def _risk_summary(
        self,
        risk_rows: list[dict[str, Any]],
        positions: list[dict[str, Any]],
        closed_trades: list[dict[str, Any]],
    ) -> dict[str, Any]:
        states: dict[str, int] = {}
        for row in risk_rows:
            state = str(row.get("risk_state") or "UNKNOWN")
            states[state] = states.get(state, 0) + 1
        closed_r = sum(float(row.get("r_multiple") or 0.0) for row in closed_trades)
        closed_pnl = sum(float(row.get("realized_pnl") or 0.0) for row in closed_trades)
        return {
            "open_positions": len(positions),
            "closed_trades": len(closed_trades),
            "closed_r": round(closed_r, 3),
            "closed_pnl": round(closed_pnl, 2),
            "full": states.get("FULL", 0),
            "reduced": states.get("REDUCED", 0),
            "defensive": states.get("DEFENSIVE", 0),
            "off": states.get("OFF", 0),
        }

    def _read_json(self, path: Path, fallback: Any) -> Any:
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return fallback

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        ensure_runtime_dirs()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
        tmp.replace(path)
