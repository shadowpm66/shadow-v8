from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shadow_v8.config import PATHS, RISK_CONFIG, ensure_runtime_dirs
from shadow_v8.execution.paper_order_manager import PaperOrderManager
from shadow_v8.models import AssetConfig, EntryDecision, SetupDecision
from shadow_v8.state_store import ClosedTradeStore, PositionStore
from shadow_v8.telemetry.dashboard_writer import DashboardWriter


def run_test(symbol: str = "TESTUSDT", notify: bool = True) -> dict[str, Any]:
    """Run a deterministic paper-only lifecycle test.

    The test uses a fake paper symbol, opens one long, advances it through
    partial TP + break-even, then closes at target. It never calls a live broker.
    """
    ensure_runtime_dirs()
    _clear_symbol(symbol)

    asset = AssetConfig(
        symbol=symbol,
        asset_class="crypto",
        broker="paper",
        enabled=True,
        allow_long=True,
        allow_short=False,
        fundamentals_required=False,
        max_risk_pct=0.01,
        tags=("paper_lifecycle_test",),
    )
    setup = SetupDecision(
        symbol=symbol,
        direction="LONG",
        setup_class="PAPER_TEST_W_STAGE2",
        grade="A",
        technical_score=88.0,
        fundamental_score=0.0,
        final_score=88.0,
        reasons=[
            "Controlled paper lifecycle test",
            "Fake W reclaim",
            "Fake pivot retest and shift-away",
        ],
    )
    decision = EntryDecision(
        action="ENTER",
        symbol=symbol,
        direction="LONG",
        reason="Controlled paper lifecycle test",
        entry=100.0,
        stop=90.0,
        target=120.0,
        setup=setup,
        metadata={
            "risk_pct": 0.01,
            "risk_state": "FULL",
            "risk_reason": "Controlled paper test",
        },
    )

    paper = PaperOrderManager(account_balance=10_000.0)
    alerts = _alerts() if notify else None

    entry_result = paper.enter(asset, decision)
    events: list[dict[str, Any]] = []
    if entry_result.get("ok") and alerts:
        alerts.paper_execution(entry_result)

    if not entry_result.get("ok"):
        _refresh_dashboard_state()
        return {"ok": False, "entry": entry_result, "events": events}

    # Step 1: high reaches +1.25R, so partial TP and BE should trigger.
    events.extend(paper.manage_positions({symbol: {"high": 112.5, "low": 99.0, "last": 112.5}}))

    # Step 2: high reaches +2R target, so the remaining paper position closes.
    events.extend(paper.manage_positions({symbol: {"high": 121.0, "low": 112.0, "last": 120.0}}))

    if alerts:
        for event in events:
            alerts.paper_lifecycle(event)

    _refresh_dashboard_state()
    return {
        "ok": True,
        "entry": entry_result,
        "events": events,
        "closed_trade": _latest_closed(symbol),
    }


def _clear_symbol(symbol: str) -> None:
    store = PositionStore()
    positions = store.load_all()
    if symbol in positions:
        positions.pop(symbol, None)
        store.save_all(positions)


def _latest_closed(symbol: str) -> dict[str, Any] | None:
    for trade in ClosedTradeStore().load_all():
        if trade.get("symbol") == symbol:
            return trade
    return None


def _alerts() -> Any:
    from shadow_v8.telemetry.telegram_alerts import TelegramAlerts

    return TelegramAlerts()


def _refresh_dashboard_state() -> None:
    writer = DashboardWriter()
    risk_path = PATHS["dashboard_risk"]
    payload = _read_json(risk_path, {})
    positions = writer._position_rows()
    closed_trades = writer._closed_trade_rows()
    scan_risk = payload.get("scan_risk") or []
    payload.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "limits": payload.get("limits") or RISK_CONFIG,
            "positions": positions,
            "closed_trades": closed_trades,
            "scan_risk": scan_risk,
            "summary": writer._risk_summary(scan_risk, positions, closed_trades),
        }
    )
    _write_json(risk_path, payload)


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a controlled Shadow v8 paper lifecycle test")
    parser.add_argument("--symbol", default="TESTUSDT", help="Fake paper symbol to use")
    parser.add_argument("--no-telegram", action="store_true", help="Do not send Telegram alerts")
    args = parser.parse_args()

    result = run_test(symbol=args.symbol.upper(), notify=not args.no_telegram)
    print(json.dumps(result, indent=2, default=str))
    if result.get("ok"):
        print("Paper lifecycle test complete. Refresh the dashboard and check Closed Paper Trades.")
    else:
        print("Paper lifecycle test failed before completion.")


if __name__ == "__main__":
    main()
