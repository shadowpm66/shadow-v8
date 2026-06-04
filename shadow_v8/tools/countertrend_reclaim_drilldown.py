from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from shadow_v8.config import ROOT_DIR
from shadow_v8.tools.replay_validate import discover_csv_files, run_file, symbol_from_path


DEFAULT_OUTPUT_DIR = ROOT_DIR / "runtime" / "countertrend_reclaim_drilldown"


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _gate_from_record(record: dict[str, Any]) -> dict[str, Any]:
    confirmation = record.get("confirmation") or {}
    gate = confirmation.get("trade_gate") or {}
    if gate:
        return gate
    setup_metadata = record.get("setup_metadata") or {}
    return setup_metadata.get("trade_gate") or {}


def _confirmation_from_record(record: dict[str, Any]) -> dict[str, Any]:
    confirmation = record.get("confirmation") or {}
    if confirmation:
        return confirmation
    setup_metadata = record.get("setup_metadata") or {}
    return {
        "base": setup_metadata.get("base_confirmation", {}),
        "vcp": setup_metadata.get("vcp_confirmation", {}),
        "pivot": setup_metadata.get("pivot_confirmation", {}),
        "context": setup_metadata.get("context_confluence", {}),
        "trade_gate": setup_metadata.get("trade_gate", {}),
        "stop_distance_quality": setup_metadata.get("stop_distance_quality"),
    }


def _is_countertrend_candidate(record: dict[str, Any]) -> bool:
    gate = _gate_from_record(record)
    reclaim = gate.get("countertrend_reclaim") or {}
    watch_reasons = set(str(item) for item in _as_list(gate.get("watch_reasons")))
    confirmations = set(str(item) for item in _as_list(gate.get("confirmations")))
    return bool(reclaim.get("candidate")) or "countertrend_reclaim_calibration" in watch_reasons or (
        "countertrend_reclaim_candidate" in confirmations
    )


def _reference_bias(reference: dict[str, Any]) -> str:
    favorable = int(reference.get("favorable_count") or 0)
    obstacles = int(reference.get("obstacle_count") or 0)
    if favorable > obstacles:
        return "supportive"
    if obstacles > favorable:
        return "obstructed"
    if favorable or obstacles:
        return "mixed"
    return "unknown"


def _outcome_bucket(record_type: str, r_multiple: Any) -> str:
    if record_type != "trade" or r_multiple is None:
        return "not_entered"
    value = float(r_multiple)
    if value > 0:
        return "winner"
    if value < 0:
        return "loser"
    return "flat"


def diagnostic_hints(record: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    outcome = str(record.get("outcome_bucket") or "")
    reference = record.get("reference") or {}
    vcp = record.get("vcp") or {}
    pivot = record.get("pivot") or {}
    gate = record.get("gate") or {}

    if outcome == "winner":
        if record.get("reference_bias") == "supportive" and pivot.get("shift_progress_bucket") in (
            "near_confirmation",
            "confirmed",
            "ready",
        ):
            hints.append("success_with_reference_and_shift")
        if vcp.get("is_tight") or vcp.get("is_near_tight"):
            hints.append("success_with_tight_vcp")
    elif outcome == "loser":
        if int(reference.get("obstacle_count") or 0) > int(reference.get("favorable_count") or 0):
            hints.append("countertrend_into_obstacles")
        if not bool(vcp.get("is_tight")) and not bool(vcp.get("is_near_tight")):
            hints.append("loose_vcp_countertrend")
        if pivot.get("shift_progress_state") in ("adverse", "not_ready", "insufficient", "not_started"):
            hints.append("weak_or_adverse_shift")
        if "missing_volume_quality" in set(_as_list(gate.get("warnings"))):
            hints.append("missing_volume_quality")
    else:
        if str(gate.get("status") or "") == "WATCH":
            hints.append("watched_not_entered")
        if str(gate.get("status") or "") == "BLOCK":
            hints.append("blocked_candidate")

    if not hints:
        hints.append("needs_manual_review")
    return hints


def candidate_record(record_type: str, record: dict[str, Any]) -> dict[str, Any]:
    confirmation = _confirmation_from_record(record)
    gate = _gate_from_record(record)
    reclaim = gate.get("countertrend_reclaim") or {}
    stage = gate.get("stage") or {}
    pivot = confirmation.get("pivot") or {}
    vcp = confirmation.get("vcp") or {}
    context = confirmation.get("context") or {}
    reference = ((context.get("metadata") or {}).get("reference_confluence") or {})
    r_multiple = record.get("r_multiple") if record_type == "trade" else None
    outcome = _outcome_bucket(record_type, r_multiple)
    result = {
        "record_type": record_type,
        "symbol": record.get("symbol"),
        "timestamp": record.get("opened_at") or record.get("timestamp"),
        "action": "ENTER" if record_type == "trade" else record.get("action"),
        "direction": record.get("direction"),
        "grade": record.get("grade"),
        "score": record.get("entry_score") or record.get("score"),
        "r_multiple": r_multiple,
        "outcome_bucket": outcome,
        "reason": record.get("entry_reason") or record.get("reason"),
        "setup_class": record.get("setup_class"),
        "stage": {
            "stage_pair": reclaim.get("stage_pair"),
            "weekly_stage": stage.get("weekly_stage"),
            "daily_stage": stage.get("daily_stage"),
            "direction": stage.get("direction") or reclaim.get("direction"),
            "risk_bias": stage.get("risk_bias"),
            "reasons": stage.get("reasons", []),
            "countertrend_reason": reclaim.get("reason"),
        },
        "pivot": {
            "confirmed": pivot.get("confirmed"),
            "reclaimed_or_lost": pivot.get("reclaimed_or_lost"),
            "retested": pivot.get("retested"),
            "retest_hold": pivot.get("retest_hold"),
            "shift_away": pivot.get("shift_away"),
            "shift_progress_state": pivot.get("shift_progress_state"),
            "shift_progress_bucket": pivot.get("shift_progress_bucket"),
            "shift_progress": pivot.get("shift_progress"),
            "shift_strength": pivot.get("shift_strength"),
        },
        "vcp": {
            "is_tight": vcp.get("is_tight"),
            "is_near_tight": vcp.get("is_near_tight"),
            "development_stage": vcp.get("development_stage"),
            "contraction_count": vcp.get("contraction_count"),
            "volume_dry_up": vcp.get("volume_dry_up", vcp.get("volume_dry")),
            "breakout_volume": vcp.get("breakout_volume"),
            "directional_close_shift": vcp.get("directional_close_shift"),
            "directional_evidence": vcp.get("directional_evidence"),
        },
        "context": {
            "quality_score": context.get("quality_score"),
            "regime": context.get("regime"),
            "nearest_reference": reference.get("nearest_reference"),
            "flags": reference.get("flags", []),
        },
        "reference": {
            "favorable_count": reference.get("favorable_count", 0),
            "obstacle_count": reference.get("obstacle_count", 0),
            "at_level_count": reference.get("at_level_count", 0),
        },
        "reference_bias": _reference_bias(reference),
        "gate": {
            "status": gate.get("status"),
            "blockers": gate.get("blockers", []),
            "watch_reasons": gate.get("watch_reasons", []),
            "warnings": gate.get("warnings", []),
            "confirmations": gate.get("confirmations", []),
            "confirmed_count": gate.get("confirmed_count"),
        },
    }
    result["diagnostic_hints"] = diagnostic_hints(result)
    return result


def extract_candidate_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for skipped in result.get("skipped_setups") or []:
        if _is_countertrend_candidate(skipped):
            candidates.append(candidate_record("skipped", skipped))
    for trade in result.get("trades") or []:
        if _is_countertrend_candidate(trade):
            candidates.append(candidate_record("trade", trade))
    return candidates


def summarize_candidates(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_symbol: dict[str, dict[str, Any]] = defaultdict(lambda: {"candidates": 0, "entered": 0, "winners": 0, "losers": 0, "net_r": 0.0})
    stage_pairs: Counter[str] = Counter()
    vcp_stages: Counter[str] = Counter()
    reference_biases: Counter[str] = Counter()
    hints: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()

    for record in records:
        symbol = str(record.get("symbol") or "UNKNOWN")
        outcome = str(record.get("outcome_bucket") or "unknown")
        r_multiple = float(record.get("r_multiple") or 0.0)
        bucket = by_symbol[symbol]
        bucket["candidates"] += 1
        if record.get("record_type") == "trade":
            bucket["entered"] += 1
            bucket["net_r"] = round(float(bucket["net_r"]) + r_multiple, 6)
        if outcome == "winner":
            bucket["winners"] += 1
        elif outcome == "loser":
            bucket["losers"] += 1
        outcomes[outcome] += 1
        stage_pairs[str((record.get("stage") or {}).get("stage_pair") or "UNKNOWN")] += 1
        vcp_stages[str((record.get("vcp") or {}).get("development_stage") or "UNKNOWN")] += 1
        reference_biases[str(record.get("reference_bias") or "unknown")] += 1
        hints.update(str(item) for item in record.get("diagnostic_hints") or [])

    entered = sum(1 for record in records if record.get("record_type") == "trade")
    winners = outcomes.get("winner", 0)
    losers = outcomes.get("loser", 0)
    net_r = round(sum(float(record.get("r_multiple") or 0.0) for record in records), 6)
    return {
        "candidate_count": len(records),
        "entered_count": entered,
        "winner_count": winners,
        "loser_count": losers,
        "net_r": net_r,
        "outcomes": dict(sorted(outcomes.items())),
        "by_symbol": {symbol: values for symbol, values in sorted(by_symbol.items())},
        "by_stage_pair": dict(stage_pairs.most_common()),
        "by_vcp_development_stage": dict(vcp_stages.most_common()),
        "by_reference_bias": dict(reference_biases.most_common()),
        "top_diagnostic_hints": [{"name": name, "count": count} for name, count in hints.most_common(10)],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_report(
    paths: list[Path],
    *,
    symbol: str | None,
    asset_class: str,
    min_bars: int,
    allow_short: bool,
    allow_intraday_stage_calibration: bool,
    allow_intraday_weekly_stage_calibration: bool,
) -> dict[str, Any]:
    files = discover_csv_files(paths)
    if not files:
        raise SystemExit("No CSV files found")
    if symbol and len(files) != 1:
        raise SystemExit("--symbol can only be used with one CSV file")

    results: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for path in files:
        result = run_file(
            path,
            symbol=symbol,
            asset_class=asset_class,
            min_bars=min_bars,
            allow_short=allow_short,
            allow_intraday_stage_calibration=allow_intraday_stage_calibration,
            allow_intraday_weekly_stage_calibration=allow_intraday_weekly_stage_calibration,
            allow_countertrend_reclaim_calibration=True,
        )
        extracted = extract_candidate_records(result)
        results.append(
            {
                "path": str(path),
                "symbol": result.get("symbol") or symbol_from_path(path),
                "bars_processed": result.get("bars_processed"),
                "candidate_count": len(extracted),
                "trade_count": result.get("trade_count"),
                "net_r": result.get("net_r"),
            }
        )
        records.extend(extracted)

    return {
        "ok": True,
        "file_count": len(files),
        "calibration": {
            "allow_countertrend_reclaim_calibration": True,
            "allow_intraday_stage_calibration": allow_intraday_stage_calibration,
            "allow_intraday_weekly_stage_calibration": allow_intraday_weekly_stage_calibration,
        },
        "aggregate": summarize_candidates(records),
        "results": results,
        "candidates": records,
    }


def print_summary(report: dict[str, Any]) -> None:
    aggregate = report["aggregate"]
    print("Countertrend reclaim drilldown complete")
    print(f"ok={report['ok']}")
    print(f"files={report['file_count']}")
    print(
        "candidates={candidate_count} entered={entered_count} winners={winner_count} "
        "losers={loser_count} net_r={net_r} top_hints={top_diagnostic_hints}".format(**aggregate)
    )
    for symbol, row in aggregate.get("by_symbol", {}).items():
        symbol_hints = Counter()
        for record in report.get("candidates") or []:
            if record.get("symbol") == symbol:
                symbol_hints.update(record.get("diagnostic_hints") or [])
        top_hint = symbol_hints.most_common(1)[0][0] if symbol_hints else None
        print(
            "symbol={symbol} candidates={candidates} entered={entered} winners={winners} "
            "losers={losers} net_r={net_r} top_hint={top_hint}".format(symbol=symbol, top_hint=top_hint, **row)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drill into strict counter-trend reclaim replay candidates and outcomes."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="CSV files, directories containing CSV files, or glob patterns")
    parser.add_argument("--symbol", help="Optional symbol override. Use only with one CSV file.")
    parser.add_argument("--asset-class", default="crypto", choices=["crypto", "forex", "stock", "commodity", "tokenized_stock"])
    parser.add_argument("--min-bars", type=int, default=120)
    parser.add_argument("--allow-short", action="store_true")
    parser.add_argument("--allow-intraday-stage-calibration", action="store_true")
    parser.add_argument("--allow-intraday-weekly-stage-calibration", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-write", action="store_true", help="Print drilldown without writing JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        args.paths,
        symbol=args.symbol,
        asset_class=args.asset_class,
        min_bars=args.min_bars,
        allow_short=args.allow_short,
        allow_intraday_stage_calibration=args.allow_intraday_stage_calibration,
        allow_intraday_weekly_stage_calibration=args.allow_intraday_weekly_stage_calibration,
    )
    if not args.no_write:
        write_json(args.output_dir / "countertrend_reclaim_drilldown.json", report)
    print_summary(report)


if __name__ == "__main__":
    main()
