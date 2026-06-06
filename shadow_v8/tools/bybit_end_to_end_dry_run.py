from __future__ import annotations

import argparse
import json
from typing import Mapping

from shadow_v8.models import (
    AssetConfig,
    BaseState,
    ContextState,
    EntryDecision,
    NestedStructureState,
    PivotConfirmation,
    RiskDecision,
    SetupDecision,
    Stage,
    StageState,
    StructureSignal,
    VcpState,
)
from shadow_v8.tools.bybit_order_intent_smoke import sample_instrument
from shadow_v8.tools.bybit_router_preview_report import build_bybit_router_preview_report


def _asset(symbol: str) -> AssetConfig:
    return AssetConfig(symbol=symbol.upper(), asset_class="crypto", broker="bybit", allow_long=True, allow_short=True)


def _setup(symbol: str, direction: str) -> SetupDecision:
    return SetupDecision(
        symbol=symbol.upper(),
        direction=direction.upper(),
        setup_class="W_PIVOT" if direction.upper() == "LONG" else "M_PIVOT",
        grade="A+",
        technical_score=88.0,
        final_score=88.0,
        reasons=["dry_run_structure_ready", "dry_run_context_supportive"],
        metadata={
            "trade_gate": {
                "status": "ALLOW",
                "blockers": [],
                "watch_reasons": [],
                "confirmations": ["stage_permission_confirmed", "pivot_confirmed", "vcp_confirmed"],
            }
        },
    )


def _stage(direction: str) -> StageState:
    is_long = direction.upper() == "LONG"
    return StageState(
        weekly_stage=Stage.STAGE_2 if is_long else Stage.STAGE_4,
        daily_stage=Stage.STAGE_2 if is_long else Stage.STAGE_4,
        long_permission=is_long,
        short_permission=not is_long,
        risk_bias="RISK_ON",
    )


def _entry_decision(symbol: str, direction: str, entry: float, stop: float, setup: SetupDecision) -> EntryDecision:
    return EntryDecision(
        action="ENTER",
        symbol=symbol.upper(),
        direction=direction.upper(),
        reason="bybit_end_to_end_dry_run",
        entry=entry,
        stop=stop,
        setup=setup,
    )


def _scanner_snapshot(
    *,
    asset: AssetConfig,
    setup: SetupDecision,
    entry: EntryDecision,
    risk_pct: float,
    router_report: dict,
) -> dict:
    preview = {
        "payload_ok": router_report.get("payload_ok"),
        "safety_block": router_report.get("safety_block"),
        "live_orders_enabled": router_report.get("live_orders_enabled"),
        "blockers": router_report.get("blockers") or [],
        "payload": router_report.get("payload") or {},
        "signed_preview": router_report.get("signed_preview") or {},
        "router_preflight": router_report.get("router_preflight") or {},
        "entry_result": router_report.get("entry_result") or {},
    }
    return {
        "asset": asset,
        "stage": _stage(entry.direction),
        "base": BaseState(found=True, pivot=entry.entry, quality_score=82.0, metadata={"confirmed": True}),
        "vcp": VcpState(
            is_tight=True,
            tightness_score=78.0,
            contraction_count=3,
            volume_dry=True,
            stop_distance_quality="GOOD",
            metadata={"near_pivot": True, "directional_close_shift": True},
        ),
        "structure": StructureSignal(
            type="W" if entry.direction == "LONG" else "M",
            direction=entry.direction,
            entry=entry.entry,
            quality_score=84.0,
        ),
        "nested": NestedStructureState(
            pattern="W_WITHIN_W" if entry.direction == "LONG" else "M_WITHIN_M",
            confirmed=True,
            quality_score=72.0,
        ),
        "pivot": PivotConfirmation(
            pivot=entry.entry,
            reclaimed_or_lost=True,
            retested=True,
            retest_hold=True,
            shift_away=True,
            confirmed=True,
        ),
        "context": ContextState(
            quality_score=70.0,
            metadata={
                "reference_confluence": {
                    "favorable_count": 2,
                    "obstacle_count": 0,
                    "flags": ["at_reference_level", "stacked_directional_support"],
                }
            },
        ),
        "setup": setup,
        "risk": RiskDecision(state="FULL", risk_pct=risk_pct, reason="dry_run_risk_ok"),
        "entry": EntryDecision(
            action=entry.action,
            symbol=entry.symbol,
            direction=entry.direction,
            reason=entry.reason,
            entry=entry.entry,
            stop=entry.stop,
            setup=setup,
            metadata={"execution_preview": preview},
        ),
    }


def build_bybit_end_to_end_dry_run(
    *,
    symbol: str = "ETHUSDT",
    direction: str = "LONG",
    entry: float = 2000.123,
    stop: float = 1960.0,
    risk_pct: float = 0.01,
    account_balance: float = 10_000.0,
    qty: float | None = None,
    instrument_payload: Mapping | None = None,
    env: Mapping[str, str] | None = None,
) -> dict:
    symbol = symbol.upper()
    direction = direction.upper()
    instrument_payload = instrument_payload or sample_instrument()
    asset = _asset(symbol)
    setup = _setup(symbol, direction)
    entry_decision = _entry_decision(symbol, direction, entry, stop, setup)
    gate = setup.metadata.get("trade_gate") or {}

    router_report = build_bybit_router_preview_report(
        symbol=symbol,
        direction=direction,
        entry=entry,
        stop=stop,
        risk_pct=risk_pct,
        qty=qty,
        account_balance=account_balance,
        instrument_payload=instrument_payload,
        env=env,
    )
    scanner_snapshot = _scanner_snapshot(
        asset=asset,
        setup=setup,
        entry=entry_decision,
        risk_pct=risk_pct,
        router_report=router_report,
    )
    readiness = "PAYLOAD_READY_VALIDATE_ONLY_BLOCKED" if router_report.get("payload_ok") else "NOT_READY"
    if gate.get("status") != "ALLOW":
        readiness = "STRATEGY_GATE_BLOCKED"

    return {
        "ok": False,
        "mode": "dry_run_validate_only",
        "symbol": symbol,
        "direction": direction,
        "strategy_gate": gate,
        "strategy_entry": {
            "action": entry_decision.action,
            "reason": entry_decision.reason,
            "entry": entry_decision.entry,
            "stop": entry_decision.stop,
            "grade": setup.grade,
            "setup_class": setup.setup_class,
        },
        "execution_readiness": readiness,
        "router_preview": router_report,
        "dashboard_execution_preview": scanner_snapshot["entry"].metadata["execution_preview"],
        "live_orders_enabled": False,
        "safety_block": True,
        "blockers": sorted(set(router_report.get("blockers") or [])),
    }


def compact_lines(report: dict) -> list[str]:
    strategy = report.get("strategy_entry") or {}
    gate = report.get("strategy_gate") or {}
    router = report.get("router_preview") or {}
    payload = router.get("payload") or {}
    signed = router.get("signed_preview") or {}
    blockers = report.get("blockers") or []
    return [
        "Shadow v8 Bybit end-to-end dry run",
        f"Symbol: {report.get('symbol', '-')}",
        f"Direction: {report.get('direction', '-')}",
        f"Strategy gate: {gate.get('status', '-')}",
        f"Entry action: {strategy.get('action', '-')}",
        f"Setup: {strategy.get('setup_class', '-')} {strategy.get('grade', '-')}",
        f"Execution readiness: {report.get('execution_readiness', '-')}",
        f"Payload ready: {router.get('payload_ok')}",
        f"Safety block: {report.get('safety_block')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        f"Side: {payload.get('side', '-')}",
        f"Qty: {payload.get('qty', '-')}",
        f"Stop loss: {payload.get('stopLoss', '-')}",
        f"Signed preview ok: {signed.get('ok')}",
        "Blockers: " + (", ".join(str(item) for item in blockers) if blockers else "none"),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a sanitized Shadow v8 strategy-to-Bybit dry run.")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--direction", choices=("LONG", "SHORT"), default="LONG")
    parser.add_argument("--entry", type=float, default=2000.123)
    parser.add_argument("--stop", type=float, default=1960.0)
    parser.add_argument("--risk-pct", type=float, default=0.01)
    parser.add_argument("--account-balance", type=float, default=10_000.0)
    parser.add_argument("--qty", type=float)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_bybit_end_to_end_dry_run(
        symbol=args.symbol,
        direction=args.direction,
        entry=args.entry,
        stop=args.stop,
        risk_pct=args.risk_pct,
        account_balance=args.account_balance,
        qty=args.qty,
    )
    if args.compact:
        print("\n".join(compact_lines(report)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
