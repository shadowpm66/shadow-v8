from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

if "requests" not in sys.modules:
    stub = types.ModuleType("requests")
    stub.get = lambda *args, **kwargs: None
    stub.post = lambda *args, **kwargs: None
    sys.modules["requests"] = stub

import shadow_v8.config as config_module
import shadow_v8.telemetry.commands as command_module
import shadow_v8.telemetry.dashboard_writer as writer_module
from shadow_v8.telemetry.commands import CommandProcessor
from shadow_v8.telemetry.dashboard_writer import DashboardWriter


class FakeBot:
    token = ""
    chat_id = ""

    def get_updates(self, *args: object, **kwargs: object) -> list[dict]:
        return []

    def is_authorized_chat(self, chat_id: object) -> bool:
        return True

    def send(self, text: str) -> None:
        self.last_text = text


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _smoke_paths() -> dict:
    root = Path("runtime") / "smoke" / "bybit_operator_packet_status_surface"
    return {
        **config_module.PATHS,
        "dashboard": root,
        "dashboard_scan": root / "scanner_results.json",
        "dashboard_latest": root / "latest_snapshot.json",
        "dashboard_risk": root / "risk_status.json",
        "dashboard_decisions": root / "recent_decisions.json",
        "dashboard_status": root / "engine_status.json",
    }


def _install_dashboard_import_stubs() -> None:
    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def mount(self, *args: object, **kwargs: object) -> None:
            pass

        def get(self, *args: object, **kwargs: object):
            def decorator(func):
                return func

            return decorator

    class HTTPException(Exception):
        pass

    class Request:
        headers: dict = {}

    def Query(default=None, **_: object):
        return default

    responses = types.ModuleType("fastapi.responses")

    class HTMLResponse(str):
        pass

    class JSONResponse(dict):
        pass

    staticfiles = types.ModuleType("fastapi.staticfiles")

    class StaticFiles:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

    fastapi.FastAPI = FastAPI
    fastapi.HTTPException = HTTPException
    fastapi.Query = Query
    fastapi.Request = Request
    responses.HTMLResponse = HTMLResponse
    responses.JSONResponse = JSONResponse
    staticfiles.StaticFiles = StaticFiles
    sys.modules.setdefault("fastapi", fastapi)
    sys.modules.setdefault("fastapi.responses", responses)
    sys.modules.setdefault("fastapi.staticfiles", staticfiles)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def main() -> None:
    paths = _smoke_paths()
    config_module.PATHS = paths
    writer_module.PATHS = paths
    command_module.PATHS = paths

    operator_packet_status = {
        "mode": "bybit_prelive_operator_packet_validate_only",
        "status": "PACKET_WAITING_FOR_READ_ONLY_PRIVATE_VALIDATION",
        "ok": False,
        "live_orders_enabled": False,
        "safe_to_enable_live": False,
        "manual_operator_approval_required": True,
        "manual_live_unlock_required": True,
        "symbols": ["ETHUSDT", "BTCUSDT"],
        "top_blocker": "read_only_private_validation_pending",
        "next_action": "run_read_only_private_validation",
        "manual_confirmations": ["run_read_only_private_validation"],
        "blocker_count": 1,
    }
    DashboardWriter().write_status(
        cycle_started_at=datetime.now(timezone.utc),
        cycle_finished_at=datetime.now(timezone.utc),
        duration_sec=0.25,
        scan_count=2,
        mode="scan-only",
        live_trading_enabled=False,
        execution_preflight={"ready": False, "checked": 1, "passed": 0},
        execution_readiness={"ready": False, "brokers_checked": 1},
        bybit_prelive_operator_packet=operator_packet_status,
        errors=[],
    )
    _write_json(paths["dashboard_scan"], {"generated_at": "smoke", "results": []})
    _write_json(paths["dashboard_latest"], {"top": {"symbol": "ETHUSDT", "action": "MONITOR", "score": 70}})
    _write_json(paths["dashboard_risk"], {"summary": {"open_positions": 0}})
    _write_json(paths["dashboard_decisions"], {"decisions": []})

    status = json.loads(paths["dashboard_status"].read_text(encoding="utf-8"))
    assert_true(
        status["bybit_prelive_operator_packet"]["status"] == "PACKET_WAITING_FOR_READ_ONLY_PRIVATE_VALIDATION",
        "Status JSON should include operator packet state",
    )

    text = CommandProcessor(bot=FakeBot())._status_text({"entries_paused": False})
    assert_true(
        "Operator packet: PACKET_WAITING_FOR_READ_ONLY_PRIVATE_VALIDATION" in text,
        "Telegram status should include operator packet state",
    )
    assert_true(
        "Operator next: run_read_only_private_validation" in text,
        "Telegram status should include operator packet next action",
    )

    _install_dashboard_import_stubs()
    import shadow_v8.dashboard.app as dashboard_app

    dashboard_app.PATHS = paths
    html = dashboard_app._render_dashboard({"results": []}, {"top": None}, {}, {"decisions": []}, status)
    assert_true("Operator packet" in html, "Dashboard should include operator packet label")
    assert_true(
        "PACKET_WAITING_FOR_READ_ONLY_PRIVATE_VALIDATION" in html,
        "Dashboard should render operator packet state",
    )
    assert_true("run_read_only_private_validation" in html, "Dashboard should render operator next action")

    rendered = json.dumps(status, sort_keys=True) + text + html
    assert_true("fake-key" not in rendered, "Smoke output must not contain key-like test values")
    assert_true("secret" not in rendered.lower(), "Smoke output must not contain secret text")

    print("Bybit operator packet status surface smoke complete")
    print("ok=True")
    print(text)


if __name__ == "__main__":
    main()
