from __future__ import annotations

import argparse
import json
from typing import Any, Mapping, Sequence

from shadow_v8.tools.bybit_end_to_end_dry_run import build_bybit_end_to_end_dry_run
from shadow_v8.tools.bybit_order_intent_smoke import sample_instrument


DEFAULT_SYMBOLS = ("ETHUSDT", "BTCUSDT", "SOLUSDT")
DEFAULT_LONG_PRICES = {
    "BTCUSDT": (65_000.0, 63_700.0),
    "ETHUSDT": (2_000.0, 1_960.0),
    "SOLUSDT": (150.0, 145.0),
}


def parse_symbols(raw: str | Sequence[str] | None) -> list[str]:
    if raw is None:
        return list(DEFAULT_SYMBOLS)
    if isinstance(raw, str):
        items = raw.replace(";", ",").split(",")
    else:
        items = list(raw)
    symbols = [str(item).strip().upper() for item in items]
    return [symbol for symbol in symbols if symbol]


def default_entry_stop(symbol: str, direction: str) -> tuple[float, float]:
    entry, long_stop = DEFAULT_LONG_PRICES.get(symbol.upper(), (100.0, 98.0))
    if direction.upper() == "SHORT":
        stop_distance = entry - long_stop
        return entry, entry + stop_distance
    return entry, long_stop


def offline_sample_instrument(symbol: str) -> dict[str, Any]:
    instrument = sample_instrument()
    instrument["symbol"] = symbol.upper()
    return instrument


def summarize_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    blocker_counts: dict[str, int] = {}
    readiness_counts: dict[str, int] = {}
    for report in reports:
        readiness = str(report.get("execution_readiness") or "UNKNOWN")
        readiness_counts[readiness] = readiness_counts.get(readiness, 0) + 1
        for blocker in report.get("blockers") or []:
            blocker_name = str(blocker)
            blocker_counts[blocker_name] = blocker_counts.get(blocker_name, 0) + 1

    payload_ready = [report.get("symbol") for report in reports if (report.get("router_preview") or {}).get("payload_ok")]
    public_fetch_failed = [
        report.get("symbol")
        for report in reports
        if "public_instrument_fetch_failed" in (report.get("blockers") or [])
        or "public_instrument_missing" in (report.get("blockers") or [])
    ]
    return {
        "symbols_checked": len(reports),
        "payload_ready_count": len(payload_ready),
        "payload_ready_symbols": payload_ready,
        "public_fetch_failed_symbols": public_fetch_failed,
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "blocker_counts": dict(sorted(blocker_counts.items(), key=lambda item: (-item[1], item[0]))),
        "live_orders_enabled_any": any(bool(report.get("live_orders_enabled")) for report in reports),
    }


def build_bybit_public_dry_run_batch(
    *,
    symbols: str | Sequence[str] | None = None,
    direction: str = "LONG",
    risk_pct: float = 0.01,
    account_balance: float = 10_000.0,
    fetch_public_instrument: bool = True,
    base_url: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    parsed_symbols = parse_symbols(symbols)
    direction = direction.upper()
    reports: list[dict[str, Any]] = []
    for symbol in parsed_symbols:
        entry, stop = default_entry_stop(symbol, direction)
        instrument_payload = None if fetch_public_instrument else offline_sample_instrument(symbol)
        reports.append(
            build_bybit_end_to_end_dry_run(
                symbol=symbol,
                direction=direction,
                entry=entry,
                stop=stop,
                risk_pct=risk_pct,
                account_balance=account_balance,
                instrument_payload=instrument_payload,
                fetch_public_instrument=fetch_public_instrument,
                base_url=base_url,
                env=env,
            )
        )

    summary = summarize_reports(reports)
    ready_for_validate_only = (
        summary["symbols_checked"] > 0
        and summary["payload_ready_count"] == summary["symbols_checked"]
        and not summary["public_fetch_failed_symbols"]
        and not summary["live_orders_enabled_any"]
    )
    return {
        "ok": ready_for_validate_only,
        "mode": "public_dry_run_batch_validate_only",
        "direction": direction,
        "fetch_public_instrument": fetch_public_instrument,
        "ready_for_validate_only": ready_for_validate_only,
        "live_orders_enabled": False,
        "summary": summary,
        "reports": reports,
    }


def compact_lines(report: dict[str, Any]) -> list[str]:
    summary = report.get("summary") or {}
    lines = [
        "Shadow v8 Bybit public dry-run batch",
        f"Direction: {report.get('direction', '-')}",
        f"Fetch public instrument: {report.get('fetch_public_instrument')}",
        f"Ready for validate-only: {report.get('ready_for_validate_only')}",
        f"Live orders enabled: {report.get('live_orders_enabled')}",
        f"Payload ready: {summary.get('payload_ready_count', 0)}/{summary.get('symbols_checked', 0)}",
        "Payload-ready symbols: " + (", ".join(summary.get("payload_ready_symbols") or []) or "none"),
    ]
    failed = summary.get("public_fetch_failed_symbols") or []
    lines.append("Public fetch failures: " + (", ".join(str(item) for item in failed) if failed else "none"))
    blockers = summary.get("blocker_counts") or {}
    if blockers:
        lines.append("Top blockers:")
        lines.extend(f"- {name}: {count}" for name, count in list(blockers.items())[:8])
    else:
        lines.append("Top blockers: none")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a validate-only Bybit public dry-run batch probe.")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--direction", choices=("LONG", "SHORT"), default="LONG")
    parser.add_argument("--risk-pct", type=float, default=0.01)
    parser.add_argument("--account-balance", type=float, default=10_000.0)
    parser.add_argument("--base-url")
    parser.add_argument("--offline-sample", action="store_true", help="Use bundled sample instrument instead of public lookup")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_bybit_public_dry_run_batch(
        symbols=args.symbols,
        direction=args.direction,
        risk_pct=args.risk_pct,
        account_balance=args.account_balance,
        fetch_public_instrument=not args.offline_sample,
        base_url=args.base_url,
    )
    if args.compact:
        print("\n".join(compact_lines(report)))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
