from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from shadow_v8.config import EXECUTION_CONFIG
from shadow_v8.models import AssetConfig, EntryDecision, ExitDecision
from shadow_v8.state_store import ClosedTradeStore, PositionStore
from shadow_v8.strategy.position_sizer import size_by_allocation, size_by_risk


class PaperOrderManager:
    """Paper execution adapter for validating v8 decisions without live orders."""

    def __init__(
        self,
        account_balance: float = 10_000.0,
        store: PositionStore | None = None,
        closed_store: ClosedTradeStore | None = None,
    ) -> None:
        self.account_balance = float(account_balance)
        self.store = store or PositionStore()
        self.closed_store = closed_store or ClosedTradeStore()

    def enter(self, asset: AssetConfig, decision: EntryDecision) -> dict[str, Any]:
        if decision.action != "ENTER":
            return {"ok": False, "reason": f"Paper enter ignored action {decision.action}", "symbol": asset.symbol}
        if decision.entry is None or decision.stop is None:
            return {"ok": False, "reason": "Paper enter requires entry and stop", "symbol": asset.symbol}

        entry = float(decision.entry)
        stop = float(decision.stop)
        if not self._valid_stop(decision.direction, entry, stop):
            return {"ok": False, "reason": "Invalid stop side for paper entry", "symbol": asset.symbol}

        positions = self.store.load_all()
        if asset.symbol in positions:
            return {"ok": False, "reason": "Paper position already open", "symbol": asset.symbol}

        sizing_model = str(decision.metadata.get("sizing_model") or "risk_pct")
        position_pct = decision.metadata.get("position_pct")
        if sizing_model == "stock_allocation":
            position_pct = float(position_pct or 0.0)
            qty = size_by_allocation(self.account_balance, position_pct, entry)
        else:
            risk_pct = float(decision.metadata.get("risk_pct") or asset.max_risk_pct)
            qty = size_by_risk(self.account_balance, risk_pct, entry, stop)
        if qty <= 0:
            return {"ok": False, "reason": "Paper size is zero", "symbol": asset.symbol}

        opened_at = datetime.now(timezone.utc).isoformat()
        initial_risk = abs(entry - stop)
        risk_dollars = qty * initial_risk
        risk_pct = risk_dollars / self.account_balance if self.account_balance > 0 else 0.0
        stop_distance_pct = initial_risk / entry * 100.0 if entry > 0 else None
        position = {
            "symbol": asset.symbol,
            "asset_class": asset.asset_class,
            "broker": "paper",
            "source_broker": asset.broker,
            "direction": decision.direction,
            "qty": round(qty, 8),
            "initial_qty": round(qty, 8),
            "closed_qty": 0.0,
            "entry": round(entry, 8),
            "stop": round(stop, 8),
            "initial_stop": round(stop, 8),
            "target": round(float(decision.target), 8) if decision.target is not None else None,
            "opened_at": opened_at,
            "setup_class": decision.setup.setup_class if decision.setup else "",
            "grade": decision.setup.grade if decision.setup else "",
            "setup_score": round(decision.setup.final_score, 2) if decision.setup else None,
            "risk_pct": round(risk_pct, 6),
            "position_pct": round(float(position_pct), 6) if position_pct is not None else None,
            "risk_dollars": round(risk_dollars, 2),
            "initial_risk_per_unit": round(initial_risk, 8),
            "stop_distance_pct": round(stop_distance_pct, 3) if stop_distance_pct is not None else None,
            "last_price": entry,
            "highest_price": entry,
            "lowest_price": entry,
            "unrealized_r": 0.0,
            "unrealized_pnl": 0.0,
            "realized_r": 0.0,
            "realized_pnl": 0.0,
            "mfe_r": 0.0,
            "mae_r": 0.0,
            "partial_taken": False,
            "break_even_moved": False,
            "status": "OPEN",
            "metadata": {
                "paper": True,
                "reason": decision.reason,
                "risk_state": decision.metadata.get("risk_state"),
                "risk_reason": decision.metadata.get("risk_reason"),
                "sizing_model": sizing_model,
                "wide_structure_risk": decision.metadata.get("wide_structure_risk"),
                "events": [],
            },
        }
        positions[asset.symbol] = position
        self.store.save_all(positions)
        return {"ok": True, "reason": "Paper position opened", "symbol": asset.symbol, "position": position}

    def apply_exit(self, asset: AssetConfig, decision: ExitDecision) -> dict[str, Any]:
        positions = self.store.load_all()
        position = positions.get(asset.symbol)
        if not position:
            return {"ok": False, "reason": "No paper position to exit", "symbol": asset.symbol}
        if decision.action not in ("EXIT", "FLATTEN"):
            return {"ok": False, "reason": f"Paper exit ignored action {decision.action}", "symbol": asset.symbol}

        exit_price = float(decision.metadata.get("exit_price") or position.get("last_price") or position.get("entry"))
        closed = self._close_position(position, exit_price, decision.reason)
        positions.pop(asset.symbol, None)
        self.store.save_all(positions)
        self.closed_store.append(closed)
        return {"ok": True, "reason": decision.reason, "symbol": asset.symbol, "closed_position": closed}

    def mark_to_market(self, prices: dict[str, float]) -> dict[str, Any]:
        positions = self.store.load_all()
        changed = False
        for symbol, position in positions.items():
            if not isinstance(position, dict) or position.get("status") != "OPEN":
                continue
            price = prices.get(symbol)
            if price is None:
                continue
            entry = float(position.get("entry") or 0.0)
            stop = float(position.get("stop") or entry)
            qty = float(position.get("qty") or 0.0)
            direction = position.get("direction")
            risk_per_unit = abs(entry - stop)
            if entry <= 0 or qty <= 0 or risk_per_unit <= 0:
                continue
            open_reward = (price - entry) if direction == "LONG" else (entry - price)
            pnl = open_reward * qty
            position["last_price"] = round(float(price), 8)
            position["unrealized_pnl"] = round(pnl, 2)
            position["unrealized_r"] = round(open_reward / risk_per_unit, 3)
            position["updated_at"] = datetime.now(timezone.utc).isoformat()
            changed = True
        if changed:
            self.store.save_all(positions)
        return {"ok": True, "count": len(positions)}

    def manage_positions(self, ranges: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
        """Advance open paper positions using the latest high/low/close range."""
        positions = self.store.load_all()
        events: list[dict[str, Any]] = []
        changed = False

        for symbol, position in list(positions.items()):
            if not isinstance(position, dict) or position.get("status") != "OPEN":
                continue
            price_range = ranges.get(symbol)
            if not price_range:
                continue

            high = float(price_range.get("high") or price_range.get("last") or position.get("last_price"))
            low = float(price_range.get("low") or price_range.get("last") or position.get("last_price"))
            last = float(price_range.get("last") or position.get("last_price") or position.get("entry"))
            self._update_open_metrics(position, high, low, last)

            if self._stop_hit(position, high, low):
                exit_price = float(position["stop"])
                closed = self._close_position(position, exit_price, "Paper hard stop")
                positions.pop(symbol, None)
                self.closed_store.append(closed)
                events.append({"ok": True, "type": "EXIT", "symbol": symbol, "reason": "Paper hard stop", "trade": closed})
                changed = True
                continue

            partial = self._maybe_partial(position, high, low)
            if partial:
                events.append(partial)
                changed = True

            stop_event = self._maybe_break_even(position)
            if stop_event:
                events.append(stop_event)
                changed = True

            trail_event = self._maybe_trail(position, last)
            if trail_event:
                events.append(trail_event)
                changed = True

            if self._target_hit(position, high, low):
                exit_price = float(position["target"])
                closed = self._close_position(position, exit_price, "Paper target")
                positions.pop(symbol, None)
                self.closed_store.append(closed)
                events.append({"ok": True, "type": "EXIT", "symbol": symbol, "reason": "Paper target", "trade": closed})
                changed = True

        if changed:
            self.store.save_all(positions)
        return events

    def _valid_stop(self, direction: str, entry: float, stop: float) -> bool:
        if direction == "LONG":
            return stop < entry
        if direction == "SHORT":
            return stop > entry
        return False

    def _update_open_metrics(self, position: dict[str, Any], high: float, low: float, last: float) -> None:
        entry = float(position.get("entry") or 0.0)
        stop = float(position.get("initial_stop") or position.get("stop") or entry)
        qty = float(position.get("qty") or 0.0)
        direction = position.get("direction")
        risk_per_unit = abs(entry - stop)
        if entry <= 0 or qty <= 0 or risk_per_unit <= 0:
            return

        position["highest_price"] = max(float(position.get("highest_price") or entry), high)
        position["lowest_price"] = min(float(position.get("lowest_price") or entry), low)
        favorable = (high - entry) if direction == "LONG" else (entry - low)
        adverse = (entry - low) if direction == "LONG" else (high - entry)
        position["mfe_r"] = round(max(float(position.get("mfe_r") or 0.0), favorable / risk_per_unit), 3)
        position["mae_r"] = round(max(float(position.get("mae_r") or 0.0), adverse / risk_per_unit), 3)

        open_reward = (last - entry) if direction == "LONG" else (entry - last)
        pnl = open_reward * qty
        position["last_price"] = round(last, 8)
        position["unrealized_pnl"] = round(pnl, 2)
        position["unrealized_r"] = round(open_reward / risk_per_unit, 3)
        position["updated_at"] = datetime.now(timezone.utc).isoformat()

    def _maybe_partial(self, position: dict[str, Any], high: float, low: float) -> dict[str, Any] | None:
        if position.get("partial_taken"):
            return None
        trigger_r = float(EXECUTION_CONFIG["paper_partial_r"])
        fraction = max(0.0, min(1.0, float(EXECUTION_CONFIG["paper_partial_fraction"])))
        if trigger_r <= 0 or fraction <= 0:
            return None

        entry = float(position["entry"])
        risk = float(position["initial_risk_per_unit"])
        direction = position["direction"]
        hit = (high - entry) / risk >= trigger_r if direction == "LONG" else (entry - low) / risk >= trigger_r
        if not hit:
            return None

        qty = float(position.get("qty") or 0.0)
        close_qty = round(qty * fraction, 8)
        if close_qty <= 0 or close_qty >= qty:
            return None
        exit_price = entry + risk * trigger_r if direction == "LONG" else entry - risk * trigger_r
        pnl = self._pnl(direction, entry, exit_price, close_qty)
        r_gain = pnl / max(self._base_risk(position), 1e-9)

        position["qty"] = round(qty - close_qty, 8)
        position["closed_qty"] = round(float(position.get("closed_qty") or 0.0) + close_qty, 8)
        position["realized_pnl"] = round(float(position.get("realized_pnl") or 0.0) + pnl, 2)
        position["realized_r"] = round(float(position.get("realized_r") or 0.0) + r_gain, 3)
        position["partial_taken"] = True
        self._append_event(position, f"Partial {close_qty} @ {exit_price:.4f} ({trigger_r:.2f}R)")
        return {
            "ok": True,
            "type": "PARTIAL",
            "symbol": position["symbol"],
            "reason": "Paper partial take profit",
            "qty": close_qty,
            "price": round(exit_price, 8),
            "r_gain": round(r_gain, 3),
        }

    def _maybe_break_even(self, position: dict[str, Any]) -> dict[str, Any] | None:
        if position.get("break_even_moved"):
            return None
        if float(position.get("mfe_r") or 0.0) < float(EXECUTION_CONFIG["paper_break_even_r"]):
            return None
        entry = float(position["entry"])
        stop = float(position["stop"])
        direction = position["direction"]
        better = (direction == "LONG" and entry > stop) or (direction == "SHORT" and entry < stop)
        if not better:
            return None
        position["stop"] = round(entry, 8)
        position["break_even_moved"] = True
        self._append_event(position, f"Stop moved to break-even @ {entry:.4f}")
        return {"ok": True, "type": "MOVE_STOP", "symbol": position["symbol"], "reason": "Paper stop to break-even", "new_stop": round(entry, 8)}

    def _maybe_trail(self, position: dict[str, Any], last: float) -> dict[str, Any] | None:
        mfe = float(position.get("mfe_r") or 0.0)
        start = float(EXECUTION_CONFIG["paper_trail_start_r"])
        giveback = float(EXECUTION_CONFIG["paper_trail_giveback_r"])
        if mfe < start or giveback <= 0:
            return None
        entry = float(position["entry"])
        risk = float(position["initial_risk_per_unit"])
        stop = float(position["stop"])
        direction = position["direction"]
        if direction == "LONG":
            new_stop = entry + max(0.0, mfe - giveback) * risk
            if new_stop <= stop or new_stop >= last:
                return None
        else:
            new_stop = entry - max(0.0, mfe - giveback) * risk
            if new_stop >= stop or new_stop <= last:
                return None
        position["stop"] = round(new_stop, 8)
        self._append_event(position, f"Trailing stop @ {new_stop:.4f}")
        return {"ok": True, "type": "MOVE_STOP", "symbol": position["symbol"], "reason": "Paper trailing stop", "new_stop": round(new_stop, 8)}

    def _stop_hit(self, position: dict[str, Any], high: float, low: float) -> bool:
        stop = float(position.get("stop") or 0.0)
        if position.get("direction") == "LONG":
            return low <= stop
        if position.get("direction") == "SHORT":
            return high >= stop
        return False

    def _target_hit(self, position: dict[str, Any], high: float, low: float) -> bool:
        target = position.get("target")
        if target is None:
            return False
        target = float(target)
        if position.get("direction") == "LONG":
            return high >= target
        if position.get("direction") == "SHORT":
            return low <= target
        return False

    def _close_position(self, position: dict[str, Any], exit_price: float, reason: str) -> dict[str, Any]:
        entry = float(position.get("entry") or 0.0)
        qty = float(position.get("qty") or 0.0)
        direction = position.get("direction")
        pnl = self._pnl(direction, entry, exit_price, qty)
        r_gain = pnl / max(self._base_risk(position), 1e-9)
        realized_pnl = float(position.get("realized_pnl") or 0.0) + pnl
        realized_r = float(position.get("realized_r") or 0.0) + r_gain
        closed_at = datetime.now(timezone.utc).isoformat()
        self._append_event(position, f"Closed @ {exit_price:.4f}: {reason}")
        return {
            "symbol": position.get("symbol"),
            "asset_class": position.get("asset_class"),
            "broker": position.get("broker"),
            "source_broker": position.get("source_broker"),
            "direction": direction,
            "entry": position.get("entry"),
            "exit": round(exit_price, 8),
            "initial_stop": position.get("initial_stop"),
            "final_stop": position.get("stop"),
            "target": position.get("target"),
            "initial_qty": position.get("initial_qty"),
            "closed_qty": round(float(position.get("closed_qty") or 0.0) + qty, 8),
            "opened_at": position.get("opened_at"),
            "closed_at": closed_at,
            "setup_class": position.get("setup_class"),
            "grade": position.get("grade"),
            "setup_score": position.get("setup_score"),
            "exit_reason": reason,
            "realized_pnl": round(realized_pnl, 2),
            "r_multiple": round(realized_r, 3),
            "mfe_r": position.get("mfe_r"),
            "mae_r": position.get("mae_r"),
            "partial_taken": bool(position.get("partial_taken")),
            "break_even_moved": bool(position.get("break_even_moved")),
            "metadata": position.get("metadata") or {},
        }

    def _pnl(self, direction: str | None, entry: float, exit_price: float, qty: float) -> float:
        if direction == "LONG":
            return (exit_price - entry) * qty
        if direction == "SHORT":
            return (entry - exit_price) * qty
        return 0.0

    def _base_risk(self, position: dict[str, Any]) -> float:
        initial_qty = float(position.get("initial_qty") or position.get("qty") or 0.0)
        risk = float(position.get("initial_risk_per_unit") or 0.0)
        return initial_qty * risk

    def _append_event(self, position: dict[str, Any], text: str) -> None:
        metadata = position.setdefault("metadata", {})
        events = metadata.setdefault("events", [])
        events.append({"ts": datetime.now(timezone.utc).isoformat(), "text": text})
