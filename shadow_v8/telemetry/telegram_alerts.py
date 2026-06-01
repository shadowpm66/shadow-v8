from __future__ import annotations

import time
from typing import Any

from shadow_v8.config import TELEGRAM_CONFIG
from shadow_v8.state_store import StateStore
from shadow_v8.telemetry.telegram_bot import TelegramBot


class TelegramAlerts:
    def __init__(self, bot: TelegramBot | None = None, state: StateStore | None = None) -> None:
        self.bot = bot or TelegramBot()
        self.state = state or StateStore()
        self.enabled = bool(TELEGRAM_CONFIG["alerts_enabled"])

    def scan_summary(self, scan_results: list[dict[str, Any]]) -> None:
        if not self.enabled or not scan_results:
            return
        top = scan_results[0]
        setup = top["setup"]
        entry = top["entry"]
        risk = top["risk"]
        market = top["market"]
        min_score = float(TELEGRAM_CONFIG["top_setup_min_score"])
        if setup.final_score >= min_score or entry.action in ("ENTER", "MONITOR"):
            key = f"top:{setup.symbol}:{entry.action}:{setup.grade}:{round(setup.final_score)}"
            if self._should_send(key, int(TELEGRAM_CONFIG["top_setup_cooldown_sec"])):
                self.bot.send(
                    "Shadow v8 top setup\n"
                    f"Symbol: {setup.symbol}\n"
                    f"Action: {entry.action} | Grade: {setup.grade} | Score: {setup.final_score:.1f}\n"
                    f"Direction: {setup.direction} | Risk: {risk.state}\n"
                    f"Last: {market.last_price}\n"
                    f"Reason: {entry.reason}"
                )

        for result in scan_results:
            self.monitor_setup(result)

    def monitor_setup(self, result: dict[str, Any]) -> None:
        if not self.enabled:
            return
        setup = result["setup"]
        entry = result["entry"]
        risk = result["risk"]
        if entry.action != "MONITOR":
            return
        key = f"monitor:{setup.symbol}:{setup.grade}:{round(setup.final_score)}"
        if not self._should_send(key, int(TELEGRAM_CONFIG["monitor_cooldown_sec"])):
            return
        self.bot.send(
            "Shadow v8 monitor setup\n"
            f"Symbol: {setup.symbol}\n"
            f"Grade: {setup.grade} | Score: {setup.final_score:.1f}\n"
            f"Direction: {setup.direction} | Risk: {risk.state}\n"
            f"Reason: {entry.reason}"
        )

    def paper_execution(self, execution_result: dict[str, Any]) -> None:
        if not self.enabled or not TELEGRAM_CONFIG["paper_entry_alerts"]:
            return
        if not execution_result.get("ok"):
            return
        position = execution_result.get("position") or {}
        symbol = execution_result.get("symbol") or position.get("symbol")
        opened_at = position.get("opened_at") or int(time.time())
        key = f"paper_enter:{symbol}:{opened_at}"
        if not self._should_send(key, 86_400):
            return
        self.bot.send(
            "Shadow v8 paper entry\n"
            f"Symbol: {symbol}\n"
            f"Direction: {position.get('direction')} | Grade: {position.get('grade')}\n"
            f"Entry: {position.get('entry')} | Stop: {position.get('stop')} | Target: {position.get('target')}\n"
            f"Qty: {position.get('qty')} | Risk: {position.get('risk_dollars')} paper dollars\n"
            f"Reason: {position.get('metadata', {}).get('reason')}"
        )

    def paper_lifecycle(self, event: dict[str, Any]) -> None:
        if not self.enabled or not TELEGRAM_CONFIG["paper_entry_alerts"] or not event.get("ok"):
            return
        event_type = event.get("type")
        symbol = event.get("symbol")
        if event_type == "PARTIAL":
            key = f"paper_partial:{symbol}:{event.get('price')}:{event.get('qty')}"
            if not self._should_send(key, 86_400):
                return
            self.bot.send(
                "Shadow v8 paper partial\n"
                f"Symbol: {symbol}\n"
                f"Qty: {event.get('qty')} @ {event.get('price')}\n"
                f"R gained: {event.get('r_gain')}\n"
                f"Reason: {event.get('reason')}"
            )
            return
        if event_type == "MOVE_STOP":
            key = f"paper_stop:{symbol}:{event.get('new_stop')}:{event.get('reason')}"
            if not self._should_send(key, 3_600):
                return
            self.bot.send(
                "Shadow v8 paper stop update\n"
                f"Symbol: {symbol}\n"
                f"New stop: {event.get('new_stop')}\n"
                f"Reason: {event.get('reason')}"
            )
            return
        if event_type == "EXIT":
            trade = event.get("trade") or {}
            key = f"paper_exit:{symbol}:{trade.get('closed_at')}:{trade.get('exit_reason')}"
            if not self._should_send(key, 86_400):
                return
            self.bot.send(
                "Shadow v8 paper exit\n"
                f"Symbol: {symbol}\n"
                f"Direction: {trade.get('direction')} | Grade: {trade.get('grade')}\n"
                f"Entry: {trade.get('entry')} | Exit: {trade.get('exit')}\n"
                f"Result: {trade.get('realized_pnl')} paper dollars | {trade.get('r_multiple')}R\n"
                f"MFE/MAE: {trade.get('mfe_r')}R / -{trade.get('mae_r')}R\n"
                f"Reason: {trade.get('exit_reason')}"
            )

    def engine_warning(self, errors: list[str]) -> None:
        if not self.enabled or not TELEGRAM_CONFIG["engine_warning_alerts"] or not errors:
            return
        key = "engine_warning:" + "|".join(errors)[:120]
        if not self._should_send(key, 900):
            return
        self.bot.send("Shadow v8 engine warning\n" + "\n".join(errors[:5]))

    def _should_send(self, key: str, cooldown_sec: int) -> bool:
        now = int(time.time())
        state = self.state.load()
        alerts = state.setdefault("telegram_alerts", {})
        last_sent = int(alerts.get(key) or 0)
        if now - last_sent < cooldown_sec:
            return False
        alerts[key] = now
        self.state.save(state)
        return True
