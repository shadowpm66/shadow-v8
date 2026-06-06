from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from shadow_v8.config import PATHS


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "").strip()

app = FastAPI(title="Shadow v8 Dashboard")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _require_token(request: Request, token: str | None = Query(default=None)) -> None:
    if not DASHBOARD_TOKEN:
        return
    header_token = request.headers.get("X-Shadow-Token")
    if token != DASHBOARD_TOKEN and header_token != DASHBOARD_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/", response_class=HTMLResponse)
def index(request: Request, token: str | None = Query(default=None)) -> HTMLResponse:
    _require_token(request, token)
    scan = _read_json(PATHS["dashboard_scan"], {"generated_at": None, "results": []})
    latest = _read_json(PATHS["dashboard_latest"], {"top": None})
    risk = _read_json(PATHS["dashboard_risk"], {"limits": {}, "positions": [], "scan_risk": []})
    decisions = _read_json(PATHS["dashboard_decisions"], {"decisions": []})
    status = _read_json(PATHS["dashboard_status"], {"health": "UNKNOWN"})
    return HTMLResponse(_render_dashboard(scan, latest, risk, decisions, status))


@app.get("/api/scanner")
def scanner_api(request: Request, token: str | None = Query(default=None)) -> JSONResponse:
    _require_token(request, token)
    return JSONResponse(_read_json(PATHS["dashboard_scan"], {"generated_at": None, "results": []}))


@app.get("/api/latest")
def latest_api(request: Request, token: str | None = Query(default=None)) -> JSONResponse:
    _require_token(request, token)
    return JSONResponse(_read_json(PATHS["dashboard_latest"], {"top": None}))


@app.get("/api/risk")
def risk_api(request: Request, token: str | None = Query(default=None)) -> JSONResponse:
    _require_token(request, token)
    return JSONResponse(_read_json(PATHS["dashboard_risk"], {"limits": {}, "positions": [], "scan_risk": []}))


@app.get("/api/decisions")
def decisions_api(request: Request, token: str | None = Query(default=None)) -> JSONResponse:
    _require_token(request, token)
    return JSONResponse(_read_json(PATHS["dashboard_decisions"], {"decisions": []}))


@app.get("/api/status")
def status_api(request: Request, token: str | None = Query(default=None)) -> JSONResponse:
    _require_token(request, token)
    return JSONResponse(_read_json(PATHS["dashboard_status"], {"health": "UNKNOWN"}))


def _render_dashboard(
    scan: dict[str, Any],
    latest: dict[str, Any],
    risk: dict[str, Any],
    decisions: dict[str, Any],
    status: dict[str, Any],
) -> str:
    rows = scan.get("results") or []
    top = latest.get("top") or (rows[0] if rows else None)
    risk_limits = risk.get("limits") or {}
    positions = risk.get("positions") or []
    closed_trades = risk.get("closed_trades") or []
    risk_rows = risk.get("scan_risk") or []
    decision_rows = decisions.get("decisions") or []
    generated_at = scan.get("generated_at") or "No scan yet"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>Shadow v8 Dashboard</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="topbar">
    <div>
      <h1>Shadow v8</h1>
      <p>Scanner, setup quality, and risk monitor</p>
    </div>
    <div class="updated">
      <span>Last updated</span>
      <strong>{_e(generated_at)}</strong>
    </div>
  </header>

  <main>
    <section class="summary-grid">
      {_top_card(top)}
      {_risk_card(risk_limits)}
      {_status_card(rows)}
      {_engine_card(status)}
      {_position_summary_card(positions, closed_trades)}
      {_risk_state_card(risk.get("summary") or {})}
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>Market Scanner</h2>
        <span>{len(rows)} symbols</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Symbol</th>
              <th>Asset</th>
              <th>Source</th>
              <th>Action</th>
              <th>Grade</th>
              <th>Score</th>
              <th>Weekly</th>
              <th>Daily</th>
              <th>Base</th>
              <th>VCP</th>
              <th>Structure</th>
              <th>Context</th>
              <th>Gate</th>
              <th>Pivot</th>
              <th>Fund</th>
              <th>Earnings</th>
              <th>Risk</th>
              <th>Exec</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {''.join(_scanner_row(row) for row in rows)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="split-grid">
      <section class="panel">
        <div class="panel-head">
          <h2>Open Positions</h2>
          <span>{len(positions)} live/tracked</span>
        </div>
        <div class="table-wrap compact">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Direction</th>
                <th>Qty</th>
                <th>Entry</th>
                <th>Stop</th>
                <th>Target</th>
                <th>Grade</th>
                <th>Open PnL / R</th>
                <th>MFE / MAE</th>
              </tr>
            </thead>
            <tbody>
              {''.join(_position_row(row) for row in positions) or _empty_row(9, "No open positions tracked by v8 yet.")}
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Recent Decisions</h2>
          <span>{len(decision_rows)} logged</span>
        </div>
        <div class="table-wrap compact">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Asset</th>
                <th>Action</th>
                <th>Score</th>
                <th>Fund</th>
                <th>Earnings</th>
                <th>Risk</th>
                <th>Exec</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {''.join(_decision_row(row) for row in decision_rows[:12]) or _empty_row(10, "No decisions logged yet.")}
            </tbody>
          </table>
        </div>
      </section>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>Closed Paper Trades</h2>
        <span>{len(closed_trades)} logged</span>
      </div>
      <div class="table-wrap compact">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Direction</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>Grade</th>
              <th>Result</th>
              <th>MFE / MAE</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {''.join(_closed_trade_row(row) for row in closed_trades[:20]) or _empty_row(9, "No closed paper trades yet.")}
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>Risk Detail</h2>
        <span>{len(risk_rows)} scanned</span>
      </div>
      <div class="table-wrap compact">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Asset</th>
              <th>Direction</th>
              <th>Grade</th>
              <th>Score</th>
              <th>Fund</th>
              <th>Earnings</th>
              <th>Risk State</th>
              <th>Risk %</th>
              <th>Position %</th>
              <th>Stop %</th>
              <th>Flags</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {''.join(_risk_row(row) for row in risk_rows) or _empty_row(13, "No risk rows yet.")}
          </tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>"""


def _top_card(top: dict[str, Any] | None) -> str:
    if not top:
        return '<section class="card"><h2>Top Setup</h2><p class="muted">No scan data yet.</p></section>'
    return f"""
      <section class="card">
        <h2>Top Setup</h2>
        <div class="metric-row">
          <strong>{_e(top.get("symbol"))}</strong>
          <span class="badge {_class_for_action(top.get("action"))}">{_e(top.get("action"))}</span>
        </div>
        <div class="score">{_e(top.get("score"))}</div>
        <p>{_e(top.get("entry_reason"))}</p>
      </section>
    """


def _risk_card(limits: dict[str, Any]) -> str:
    return f"""
      <section class="card">
        <h2>Risk Limits</h2>
        <dl class="kv">
          <dt>Total positions</dt><dd>{_e(limits.get("max_open_positions_total", "-"))}</dd>
          <dt>Crypto positions</dt><dd>{_e(limits.get("max_open_crypto_positions", "-"))}</dd>
          <dt>Crypto risk cap</dt><dd>{_pct_text(limits.get("default_crypto_risk_pct"))}</dd>
          <dt>Stock account risk</dt><dd>{_pct_text(limits.get("stock_normal_max_account_risk_pct"))}</dd>
          <dt>Daily R limit</dt><dd>{_e(limits.get("daily_r_limit", "-"))}</dd>
        </dl>
      </section>
    """


def _engine_card(status: dict[str, Any]) -> str:
    health = status.get("health") or "UNKNOWN"
    mode = status.get("mode") or "-"
    duration = status.get("duration_sec")
    scan_count = status.get("scan_count", "-")
    live = "ON" if status.get("live_trading_enabled") else "OFF"
    entries = "PAUSED" if status.get("entries_paused") else "ACTIVE"
    preflight = status.get("execution_preflight") or {}
    preflight_ready = "READY" if preflight.get("ready") else "BLOCKED" if preflight.get("checked") else "UNKNOWN"
    top_blocks = preflight.get("top_block_reasons") or []
    top_block = top_blocks[0].get("reason") if top_blocks else "-"
    readiness = status.get("execution_readiness") or {}
    readiness_state = "READY" if readiness.get("ready") else "BLOCKED" if readiness.get("brokers_checked") else "UNKNOWN"
    readiness_blocks = readiness.get("top_blockers") or []
    readiness_block = readiness_blocks[0].get("reason") if readiness_blocks else "-"
    return f"""
      <section class="card">
        <h2>Engine</h2>
        <div class="metric-row">
          <strong>{_e(health)}</strong>
          <span class="badge {_class_for_health(health)}">{_e(mode)}</span>
        </div>
        <dl class="kv tight">
          <dt>Live trading</dt><dd>{live}</dd>
          <dt>Entries</dt><dd>{entries}</dd>
          <dt>Execution</dt><dd>{_e(preflight_ready)}</dd>
          <dt>Preflight</dt><dd>{_e(preflight.get("passed", "-"))}/{_e(preflight.get("checked", "-"))} pass</dd>
          <dt>Top block</dt><dd>{_e(top_block)}</dd>
          <dt>Readiness</dt><dd>{_e(readiness_state)}</dd>
          <dt>Ready block</dt><dd>{_e(readiness_block)}</dd>
          <dt>Scan count</dt><dd>{_e(scan_count)}</dd>
          <dt>Cycle sec</dt><dd>{_e(duration)}</dd>
        </dl>
      </section>
    """


def _position_summary_card(positions: list[dict[str, Any]], closed_trades: list[dict[str, Any]]) -> str:
    open_r = sum(float(row.get("unrealized_r") or 0.0) for row in positions)
    open_pnl = sum(float(row.get("unrealized_pnl") or 0.0) for row in positions)
    closed_r = sum(float(row.get("r_multiple") or 0.0) for row in closed_trades)
    closed_pnl = sum(float(row.get("realized_pnl") or 0.0) for row in closed_trades)
    return f"""
      <section class="card">
        <h2>Positions / PnL</h2>
        <dl class="kv">
          <dt>Open positions</dt><dd>{len(positions)}</dd>
          <dt>Open R</dt><dd>{open_r:+.2f}</dd>
          <dt>Open PnL</dt><dd>{open_pnl:+.2f}</dd>
          <dt>Closed R</dt><dd>{closed_r:+.2f}</dd>
          <dt>Closed PnL</dt><dd>{closed_pnl:+.2f}</dd>
        </dl>
      </section>
    """


def _risk_state_card(summary: dict[str, Any]) -> str:
    return f"""
      <section class="card">
        <h2>Risk State</h2>
        <div class="mini-stats four">
          <span><strong>{_e(summary.get("full", 0))}</strong> Full</span>
          <span><strong>{_e(summary.get("reduced", 0))}</strong> Reduced</span>
          <span><strong>{_e(summary.get("defensive", 0))}</strong> Defensive</span>
          <span><strong>{_e(summary.get("off", 0))}</strong> Off</span>
        </div>
      </section>
    """


def _status_card(rows: list[dict[str, Any]]) -> str:
    enter = sum(1 for row in rows if row.get("action") == "ENTER")
    monitor = sum(1 for row in rows if row.get("action") == "MONITOR")
    skip = sum(1 for row in rows if row.get("action") == "SKIP")
    return f"""
      <section class="card">
        <h2>Actions</h2>
        <div class="mini-stats">
          <span><strong>{enter}</strong> Enter</span>
          <span><strong>{monitor}</strong> Monitor</span>
          <span><strong>{skip}</strong> Skip</span>
        </div>
      </section>
    """


def _scanner_row(row: dict[str, Any]) -> str:
    reason = row.get("entry_reason") or "; ".join(row.get("reasons") or [])
    return f"""
      <tr>
        <td>{_e(row.get("rank"))}</td>
        <td><strong>{_e(row.get("symbol"))}</strong><span class="sub">{_e(row.get("last_price"))}</span></td>
        <td>{_e(row.get("asset_class"))}</td>
        <td>{_e(row.get("data_source"))}</td>
        <td><span class="badge {_class_for_action(row.get("action"))}">{_e(row.get("action"))}</span></td>
        <td>{_e(row.get("grade"))}</td>
        <td>{_e(row.get("score"))}</td>
        <td>{_e(row.get("weekly_stage"))}</td>
        <td>{_e(row.get("daily_stage"))}</td>
        <td>{_e(row.get("base_quality"))}</td>
        <td>{_e(row.get("vcp_score"))}</td>
        <td>{_e(row.get("structure_type"))}/{_e(row.get("structure_score"))}</td>
        <td>{_e(_context_text(row))}</td>
        <td>{_e(_gate_text(row))}</td>
        <td>{_yes_no(row.get("pivot_confirmed"))}</td>
        <td>{_e(row.get("fundamental_grade"))}</td>
        <td>{_e(_earnings_text(row))}</td>
        <td>{_e(row.get("risk_state"))}</td>
        <td>{_e(_execution_preview_text(row))}</td>
        <td class="reason">{_e(reason)}</td>
      </tr>
    """


def _position_row(row: dict[str, Any]) -> str:
    pnl = row.get("unrealized_pnl")
    r_mult = row.get("unrealized_r")
    pnl_text = "-" if pnl is None and r_mult is None else f"{float(pnl or 0):+.2f} / {float(r_mult or 0):+.2f}R"
    mfe_mae = f"{float(row.get('mfe_r') or 0):+.2f}R / -{float(row.get('mae_r') or 0):.2f}R"
    return f"""
      <tr>
        <td><strong>{_e(row.get("symbol"))}</strong><span class="sub">{_e(row.get("broker"))}</span></td>
        <td>{_e(row.get("direction"))}</td>
        <td>{_e(row.get("qty"))}</td>
        <td>{_e(row.get("entry"))}</td>
        <td>{_e(row.get("stop"))}</td>
        <td>{_e(row.get("target"))}</td>
        <td>{_e(row.get("grade"))}</td>
        <td>{_e(pnl_text)}</td>
        <td>{_e(mfe_mae)}</td>
      </tr>
    """


def _closed_trade_row(row: dict[str, Any]) -> str:
    result = f"{float(row.get('realized_pnl') or 0):+.2f} / {float(row.get('r_multiple') or 0):+.2f}R"
    mfe_mae = f"{float(row.get('mfe_r') or 0):+.2f}R / -{float(row.get('mae_r') or 0):.2f}R"
    return f"""
      <tr>
        <td>{_short_time(row.get("closed_at"))}</td>
        <td><strong>{_e(row.get("symbol"))}</strong></td>
        <td>{_e(row.get("direction"))}</td>
        <td>{_e(row.get("entry"))}</td>
        <td>{_e(row.get("exit"))}</td>
        <td>{_e(row.get("grade"))}</td>
        <td>{_e(result)}</td>
        <td>{_e(mfe_mae)}</td>
        <td class="reason">{_e(row.get("exit_reason"))}</td>
      </tr>
    """


def _decision_row(row: dict[str, Any]) -> str:
    return f"""
      <tr>
        <td>{_short_time(row.get("timestamp"))}</td>
        <td><strong>{_e(row.get("symbol"))}</strong><span class="sub">{_e(row.get("grade"))}</span></td>
        <td>{_e(row.get("asset_class"))}</td>
        <td><span class="badge {_class_for_action(row.get("action"))}">{_e(row.get("action"))}</span></td>
        <td>{_e(row.get("score"))}</td>
        <td>{_e(row.get("fundamental_grade"))}</td>
        <td>{_e(_earnings_text(row))}</td>
        <td>{_e(row.get("risk_state"))}</td>
        <td>{_e(_execution_preview_text(row))}</td>
        <td class="reason">{_e(row.get("reason"))}</td>
      </tr>
    """


def _risk_row(row: dict[str, Any]) -> str:
    return f"""
      <tr>
        <td><strong>{_e(row.get("symbol"))}</strong></td>
        <td>{_e(row.get("asset_class"))}</td>
        <td>{_e(row.get("direction"))}</td>
        <td>{_e(row.get("grade"))}</td>
        <td>{_e(row.get("score"))}</td>
        <td>{_e(row.get("fundamental_grade"))}</td>
        <td>{_e(_earnings_text(row))}</td>
        <td>{_e(row.get("risk_state"))}</td>
        <td>{_e(row.get("risk_pct"))}</td>
        <td>{_pct_text(row.get("position_pct"))}</td>
        <td>{_e(row.get("stop_distance_pct"))}</td>
        <td>{_e(_risk_flags(row))}</td>
        <td class="reason">{_e(row.get("reason"))}</td>
      </tr>
    """


def _empty_row(colspan: int, message: str) -> str:
    return f'<tr><td class="empty" colspan="{colspan}">{_e(message)}</td></tr>'


def _class_for_action(action: Any) -> str:
    action_text = str(action or "").lower()
    if action_text == "enter":
        return "good"
    if action_text == "monitor":
        return "watch"
    if action_text == "wait":
        return "wait"
    return "skip"


def _class_for_health(health: Any) -> str:
    health_text = str(health or "").lower()
    if health_text == "ok":
        return "good"
    if health_text == "warn":
        return "watch"
    return "skip"


def _yes_no(value: Any) -> str:
    return "Yes" if value else "No"


def _earnings_text(row: dict[str, Any]) -> str:
    if row.get("earnings_blocked") is True:
        return "Blocked"
    days = row.get("earnings_days")
    if days in (None, ""):
        return "-"
    return f"{days}d"


def _context_text(row: dict[str, Any]) -> str:
    score = row.get("context_score")
    nearest = row.get("nearest_reference") or "-"
    flags = row.get("reference_flags") or []
    suffix = f" {'/'.join(flags[:2])}" if flags else ""
    if score in (None, ""):
        return f"{nearest}{suffix}"
    return f"{score} {nearest}{suffix}"


def _gate_text(row: dict[str, Any]) -> str:
    status = row.get("gate_status") or "-"
    blockers = row.get("gate_blockers") or []
    if blockers:
        return f"{status}: {', '.join(str(item) for item in blockers[:2])}"
    warnings = row.get("gate_warnings") or []
    if warnings:
        return f"{status}: {', '.join(str(item) for item in warnings[:2])}"
    return str(status)


def _execution_preview_text(row: dict[str, Any]) -> str:
    status = row.get("execution_preview_status")
    if not status:
        return "-"
    parts = [str(status)]
    side = row.get("execution_side")
    qty = row.get("execution_qty")
    if side:
        parts.append(str(side))
    if qty not in (None, ""):
        parts.append(f"qty={qty}")
    blockers = row.get("execution_blockers") or []
    if blockers:
        parts.append(f"block={blockers[0]}")
    elif row.get("execution_payload_ok") is True:
        parts.append("payload_ok")
    signed_ok = row.get("execution_signed_ok")
    if signed_ok is not None:
        parts.append(f"signed={signed_ok}")
    return " | ".join(parts)


def _risk_flags(row: dict[str, Any]) -> str:
    flags = []
    if row.get("wide_structure_risk"):
        flags.append("wide_structure_risk")
    return ", ".join(flags) or "-"


def _pct_text(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _short_time(value: Any) -> str:
    if not value:
        return "-"
    text = str(value)
    return text[11:19] if len(text) >= 19 and "T" in text else text


def _e(value: Any) -> str:
    if value is None:
        return "-"
    return html.escape(str(value))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Shadow v8 dashboard")
    parser.add_argument("--host", default=os.getenv("DASHBOARD_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DASHBOARD_PORT", "8501")))
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("shadow_v8.dashboard.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
