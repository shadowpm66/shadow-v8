from __future__ import annotations

import json
from pathlib import Path
import sys
import types


if "requests" not in sys.modules:
    stub = types.ModuleType("requests")
    stub.get = lambda *args, **kwargs: None
    stub.post = lambda *args, **kwargs: None
    sys.modules["requests"] = stub

from shadow_v8.telemetry import commands as command_module
from shadow_v8.telemetry.commands import CommandProcessor


class FakeBot:
    token = ""
    chat_id = ""

    def get_updates(self, *args, **kwargs) -> list[dict]:
        return []

    def is_authorized_chat(self, chat_id: object) -> bool:
        return True

    def send(self, text: str) -> None:
        self.last_text = text


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def main() -> None:
    root = Path("runtime") / "smoke" / "telegram_status_preflight"
    paths = {
        "dashboard_status": root / "status.json",
        "dashboard_latest": root / "latest.json",
        "dashboard_risk": root / "risk.json",
    }
    command_module.PATHS = paths
    write_json(
        paths["dashboard_status"],
        {
            "health": "OK",
            "mode": "scan-only",
            "live_trading_enabled": False,
            "scan_count": 3,
            "duration_sec": 1.25,
            "execution_preflight": {
                "ready": False,
                "checked": 2,
                "passed": 0,
                "blocked": 2,
                "top_block_reasons": [{"reason": "Execution mode scan_only blocks orders", "count": 2}],
            },
            "execution_readiness": {
                "ready": False,
                "brokers_checked": 2,
                "top_blockers": [{"reason": "adapter_placeholder", "count": 1}],
            },
            "errors": [],
        },
    )
    write_json(paths["dashboard_latest"], {"top": {"symbol": "ETHUSDT", "action": "MONITOR", "score": 72.5}})
    write_json(paths["dashboard_risk"], {"summary": {"open_positions": 1}})

    text = CommandProcessor(bot=FakeBot())._status_text({"entries_paused": False})
    assert_true("Execution: BLOCKED" in text, "Telegram status should report blocked preflight state")
    assert_true("Preflight: 0/2 pass" in text, "Telegram status should report preflight pass count")
    assert_true("Top block: Execution mode scan_only blocks orders" in text, "Telegram status should report top block reason")
    assert_true("Readiness: BLOCKED" in text, "Telegram status should report blocked readiness state")
    assert_true("Ready block: adapter_placeholder" in text, "Telegram status should report readiness blocker")

    print("Telegram status preflight smoke complete")
    print("ok=True")
    print(text)


if __name__ == "__main__":
    main()
