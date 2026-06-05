from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import shadow_v8.config as config_module
import shadow_v8.telemetry.dashboard_writer as writer_module
from shadow_v8.models import (
    AssetConfig,
    BaseState,
    ContextState,
    EntryDecision,
    MarketDataBundle,
    NestedStructureState,
    PivotConfirmation,
    RiskDecision,
    SetupDecision,
    Stage,
    StageState,
    StructureSignal,
    VcpState,
)
from shadow_v8.telemetry.dashboard_writer import DashboardWriter


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _smoke_paths() -> dict:
    root = Path("runtime") / "smoke" / "dashboard_execution_preview"
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


def _scan_result() -> dict:
    preview = {
        "payload_ok": True,
        "safety_block": True,
        "live_orders_enabled": False,
        "blockers": ["live_orders_disabled_validate_only"],
        "payload": {"side": "Buy", "qty": "2.49", "stopLoss": "1960"},
        "signed_preview": {"ok": True},
        "router_preflight": {"ok": True, "safety_block": False},
    }
    setup = SetupDecision(
        symbol="ETHUSDT",
        direction="LONG",
        setup_class="W_PIVOT",
        grade="A",
        technical_score=88.0,
        final_score=88.0,
        reasons=["smoke setup"],
        metadata={"trade_gate": {"status": "enter_ready", "blockers": [], "warnings": []}},
    )
    return {
        "asset": AssetConfig(symbol="ETHUSDT", asset_class="crypto", broker="bybit", allow_long=True, allow_short=True),
        "market": MarketDataBundle(symbol="ETHUSDT", asset_class="crypto", last_price=2000.0, metadata={"source": "smoke"}),
        "stage": StageState(weekly_stage=Stage.STAGE_2, daily_stage=Stage.STAGE_2, risk_bias="RISK_ON"),
        "base": BaseState(found=True, quality_score=72.0, depth_pct=4.5),
        "vcp": VcpState(is_tight=True, tightness_score=74.0, contraction_count=3),
        "structure": StructureSignal(type="W", direction="LONG", quality_score=76.0),
        "context": ContextState(
            quality_score=65.0,
            metadata={"reference_confluence": {"nearest_reference": {"name": "daily_open"}, "flags": ["near_reference"]}},
        ),
        "nested": NestedStructureState(pattern="W_WITHIN_W", confirmed=True),
        "pivot": PivotConfirmation(confirmed=True, retested=True, shift_away=True),
        "setup": setup,
        "risk": RiskDecision(state="FULL", risk_pct=0.02, reason="smoke risk", metadata={"position_pct": 0.2}),
        "entry": EntryDecision(
            action="ENTER",
            symbol="ETHUSDT",
            direction="LONG",
            reason="smoke entry",
            entry=2000.0,
            stop=1960.0,
            metadata={"execution_preview": preview},
        ),
    }


def main() -> None:
    _install_dashboard_import_stubs()
    import shadow_v8.dashboard.app as dashboard_app

    paths = _smoke_paths()
    config_module.PATHS = paths
    writer_module.PATHS = paths
    dashboard_app.PATHS = paths

    DashboardWriter().write_scan([_scan_result()])

    scan = json.loads(paths["dashboard_scan"].read_text(encoding="utf-8"))
    decisions = json.loads(paths["dashboard_decisions"].read_text(encoding="utf-8"))
    scanner_row = scan["results"][0]
    decision_row = decisions["decisions"][0]

    assert_true(scanner_row["execution_preview_status"] == "BLOCKED", "Scanner row should show blocked preview status")
    assert_true(scanner_row["execution_payload_ok"] is True, "Scanner row should preserve payload readiness")
    assert_true(scanner_row["execution_qty"] == "2.49", "Scanner row should show preview quantity")
    assert_true(decision_row["execution_side"] == "Buy", "Decision row should show preview side")
    assert_true(
        "live_orders_disabled_validate_only" in decision_row["execution_blockers"],
        "Decision row should preserve validate-only blocker",
    )

    html = dashboard_app._render_dashboard(scan, {"top": scanner_row}, {}, decisions, {})
    assert_true("BLOCKED | Buy | qty=2.49" in html, "Dashboard HTML should render execution preview summary")
    assert_true("live_orders_disabled_validate_only" in html, "Dashboard HTML should render first execution blocker")
    print("Dashboard execution preview smoke complete")


if __name__ == "__main__":
    main()
