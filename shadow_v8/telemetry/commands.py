from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shadow_v8.config import PATHS, TELEGRAM_CONFIG
from shadow_v8.state_store import StateStore
from shadow_v8.telemetry.telegram_bot import TelegramBot


class CommandProcessor:
    def __init__(self, bot: TelegramBot | None = None, state: StateStore | None = None) -> None:
        self.bot = bot or TelegramBot()
        self.state = state or StateStore()
        self.enabled = bool(TELEGRAM_CONFIG["alerts_enabled"])

    def process_once(self) -> dict[str, Any]:
        if not self.enabled or not self.bot.token or not self.bot.chat_id:
            return {"ok": True, "commands": 0, "enabled": False}

        state = self.state.load()
        offset = state.get("telegram_command_offset")
        updates = self.bot.get_updates(offset=int(offset) if offset is not None else None, timeout=1)
        processed = 0

        for update in updates:
            update_id = update.get("update_id")
            if update_id is not None:
                state["telegram_command_offset"] = int(update_id) + 1

            message = update.get("message") or update.get("edited_message") or {}
            chat = message.get("chat") or {}
            if not self.bot.is_authorized_chat(chat.get("id")):
                continue

            text = str(message.get("text") or "").strip()
            if not text.startswith("/"):
                continue

            processed += 1
            self._handle(text, state)

        if updates:
            self.state.save(state)
        return {"ok": True, "commands": processed, "enabled": True}

    def entries_paused(self) -> bool:
        return bool(self.state.load().get("entries_paused", False))

    def _handle(self, text: str, state: dict[str, Any]) -> None:
        command = text.split()[0].split("@")[0].lower()
        if command in ("/help", "/start"):
            self.bot.send(self._help_text())
        elif command == "/status":
            self.bot.send(self._status_text(state))
        elif command == "/top":
            self.bot.send(self._top_text())
        elif command == "/positions":
            self.bot.send(self._positions_text())
        elif command == "/risk":
            self.bot.send(self._risk_text())
        elif command == "/pause":
            state["entries_paused"] = True
            self.bot.send("Shadow v8 entries paused. Scanner and dashboard remain active.")
        elif command == "/resume":
            state["entries_paused"] = False
            self.bot.send("Shadow v8 entries resumed. Paper/live mode still follows .env safety settings.")
        else:
            self.bot.send("Unknown command.\n\n" + self._help_text())

    def _help_text(self) -> str:
        return (
            "Shadow v8 commands\n"
            "/status - engine, mode, scan health\n"
            "/top - current best setup\n"
            "/positions - tracked paper/live positions\n"
            "/risk - risk limits and state counts\n"
            "/pause - block new entries, keep scanner running\n"
            "/resume - allow entries again"
        )

    def _status_text(self, state: dict[str, Any]) -> str:
        status = self._read_json(PATHS["dashboard_status"], {})
        latest = self._read_json(PATHS["dashboard_latest"], {})
        risk = self._read_json(PATHS["dashboard_risk"], {})
        top = latest.get("top") or {}
        summary = risk.get("summary") or {}
        errors = status.get("errors") or []
        preflight = status.get("execution_preflight") or {}
        readiness = status.get("execution_readiness") or {}
        bybit_private = status.get("bybit_private_validation") or {}
        bybit_live = status.get("bybit_live_unlock_review") or {}
        ec2_rehearsal = status.get("ec2_prelive_rehearsal") or {}
        top_blocks = preflight.get("top_block_reasons") or []
        top_block = top_blocks[0].get("reason") if top_blocks else "none"
        readiness_blocks = readiness.get("top_blockers") or []
        readiness_block = readiness_blocks[0].get("reason") if readiness_blocks else "none"
        private_next = bybit_private.get("next_action") or bybit_private.get("top_blocker") or "none"
        live_review_next = bybit_live.get("next_action") or bybit_live.get("top_blocker") or "none"
        rehearsal_next = ec2_rehearsal.get("next_action") or ec2_rehearsal.get("top_blocker") or "none"
        execution_state = "READY" if preflight.get("ready") else "BLOCKED" if preflight.get("checked") else "UNKNOWN"
        readiness_state = "READY" if readiness.get("ready") else "BLOCKED" if readiness.get("brokers_checked") else "UNKNOWN"
        return (
            "Shadow v8 status\n"
            f"Health: {status.get('health', 'UNKNOWN')}\n"
            f"Mode: {status.get('mode', '-')}\n"
            f"Live trading: {'ON' if status.get('live_trading_enabled') else 'OFF'}\n"
            f"Entries paused: {'YES' if state.get('entries_paused') else 'NO'}\n"
            f"Execution: {execution_state}\n"
            f"Preflight: {preflight.get('passed', '-')}/{preflight.get('checked', '-')} pass\n"
            f"Top block: {top_block}\n"
            f"Readiness: {readiness_state}\n"
            f"Ready block: {readiness_block}\n"
            f"Bybit private: {bybit_private.get('status', '-')}\n"
            f"Private next: {private_next}\n"
            f"Live review: {bybit_live.get('status', '-')}\n"
            f"Live next: {live_review_next}\n"
            f"EC2 rehearsal: {ec2_rehearsal.get('rehearsal_status', '-')}\n"
            f"Rehearsal next: {rehearsal_next}\n"
            f"Scan count: {status.get('scan_count', '-')}\n"
            f"Cycle sec: {status.get('duration_sec', '-')}\n"
            f"Open positions: {summary.get('open_positions', 0)}\n"
            f"Top: {top.get('symbol', '-')} {top.get('action', '-')} score={top.get('score', '-')}\n"
            f"Errors: {('; '.join(errors[:3]) if errors else 'none')}"
        )

    def _top_text(self) -> str:
        latest = self._read_json(PATHS["dashboard_latest"], {})
        top = latest.get("top") or {}
        if not top:
            return "No scanner snapshot yet."
        reasons = top.get("reasons") or []
        reason_text = "; ".join(str(x) for x in reasons[:5]) if reasons else top.get("entry_reason", "-")
        return (
            "Shadow v8 top setup\n"
            f"Symbol: {top.get('symbol')}\n"
            f"Action: {top.get('action')} | Grade: {top.get('grade')} | Score: {top.get('score')}\n"
            f"Direction: {top.get('direction')} | Risk: {top.get('risk_state')}\n"
            f"Weekly/Daily: {top.get('weekly_stage')} / {top.get('daily_stage')}\n"
            f"Base: {top.get('base_quality')} | VCP: {top.get('vcp_score')} | Structure: {top.get('structure_type')}/{top.get('structure_score')}\n"
            f"Pivot confirmed: {top.get('pivot_confirmed')}\n"
            f"Reason: {reason_text}"
        )

    def _positions_text(self) -> str:
        risk = self._read_json(PATHS["dashboard_risk"], {})
        positions = risk.get("positions") or []
        if not positions:
            return "No open positions tracked by Shadow v8."
        lines = ["Shadow v8 positions"]
        for item in positions[:10]:
            lines.append(
                f"{item.get('symbol')} {item.get('direction')} qty={item.get('qty')} "
                f"entry={item.get('entry')} stop={item.get('stop')} "
                f"R={item.get('unrealized_r')} PnL={item.get('unrealized_pnl')}"
            )
        return "\n".join(lines)

    def _risk_text(self) -> str:
        risk = self._read_json(PATHS["dashboard_risk"], {})
        limits = risk.get("limits") or {}
        summary = risk.get("summary") or {}
        return (
            "Shadow v8 risk\n"
            f"Open positions: {summary.get('open_positions', 0)}\n"
            f"Full/Reduced/Defensive/Off: {summary.get('full', 0)}/{summary.get('reduced', 0)}/{summary.get('defensive', 0)}/{summary.get('off', 0)}\n"
            f"Max total: {limits.get('max_open_positions_total', '-')}\n"
            f"Max crypto: {limits.get('max_open_crypto_positions', '-')}\n"
            f"Max stocks: {limits.get('max_open_stock_positions', '-')}\n"
            f"Daily R limit: {limits.get('daily_r_limit', '-')}"
        )

    def _read_json(self, path: Path, fallback: Any) -> Any:
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return fallback
