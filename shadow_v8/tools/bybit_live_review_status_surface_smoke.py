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
    root = Path("runtime") / "smoke" / "bybit_live_review_status_surface"
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

    private_status = {
        "status": "EC2_PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY",
        "private_validation_status": "PRIVATE_VALIDATION_OK_VALIDATE_ONLY",
        "prelive_checklist_status": "VALIDATE_ONLY_READY",
        "credentials_present": True,
        "request_attempted": True,
        "live_orders_enabled": False,
        "symbols": ["ETHUSDT", "BTCUSDT"],
        "top_blocker": "live_orders_disabled_validate_only",
        "next_action": "review_live_unlock_status",
    }
    live_review_status = {
        "status": "BLOCKED_DASHBOARD_TOKEN_ROTATION_REQUIRED",
        "audit_status": "EC2_PRIVATE_VALIDATION_COMPLETE_VALIDATE_ONLY",
        "private_validation_status": "PRIVATE_VALIDATION_OK_VALIDATE_ONLY",
        "prelive_checklist_status": "VALIDATE_ONLY_READY",
        "dashboard_token_rotated": False,
        "private_validation_complete": True,
        "manual_live_unlock_required": True,
        "live_orders_enabled": False,
        "symbols": ["ETHUSDT", "BTCUSDT"],
        "top_blocker": "dashboard_token_rotation_required_before_live",
        "next_action": "rotate_dashboard_token_before_live_unlock_review",
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
        bybit_private_validation=private_status,
        bybit_live_unlock_review=live_review_status,
        errors=[],
    )
    _write_json(paths["dashboard_latest"], {"top": {"symbol": "ETHUSDT", "action": "MONITOR", "score": 70}})
    _write_json(paths["dashboard_risk"], {"summary": {"open_positions": 0}})

    status = json.loads(paths["dashboard_status"].read_text(encoding="utf-8"))
    assert_true(
        status["bybit_live_unlock_review"]["status"] == "BLOCKED_DASHBOARD_TOKEN_ROTATION_REQUIRED",
        "Status JSON should include live unlock review state",
    )

    text = CommandProcessor(bot=FakeBot())._status_text({"entries_paused": False})
    assert_true(
        "Live review: BLOCKED_DASHBOARD_TOKEN_ROTATION_REQUIRED" in text,
        "Telegram status should include live review state",
    )
    assert_true(
        "Live next: rotate_dashboard_token_before_live_unlock_review" in text,
        "Telegram status should include live review next action",
    )

    _install_dashboard_import_stubs()
    import shadow_v8.dashboard.app as dashboard_app

    dashboard_app.PATHS = paths
    html = dashboard_app._render_dashboard({"results": []}, {"top": None}, {}, {"decisions": []}, status)
    assert_true("Live review" in html, "Dashboard should include live review label")
    assert_true("BLOCKED_DASHBOARD_TOKEN_ROTATION_REQUIRED" in html, "Dashboard should render live review state")
    assert_true(
        "rotate_dashboard_token_before_live_unlock_review" in html,
        "Dashboard should render live review next action",
    )

    rendered = json.dumps(status, sort_keys=True) + text + html
    assert_true("fake-key" not in rendered, "Smoke output must not contain key-like test values")
    assert_true("secret" not in rendered.lower(), "Smoke output must not contain secret text")

    print("Bybit live review status surface smoke complete")
    print("ok=True")
    print(text)


if __name__ == "__main__":
    main()
