from __future__ import annotations

import json

from shadow_v8.tools.bybit_preflight_report import build_bybit_preflight_report, compact_lines


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    report = build_bybit_preflight_report(
        symbol="ETHUSDT",
        fetch_public_instrument=False,
        include_signed_preview=True,
    )
    report_text = json.dumps(report, sort_keys=True)
    assert_true(report["ok"] is False, "Bybit preflight should remain blocked")
    assert_true(report["live_orders_enabled"] is False, "Bybit preflight should not enable live orders")
    assert_true("instrument_payload_missing" in report["blockers"], "Offline preflight should report missing instrument payload")
    assert_true(report["signed_preview"]["ok"] is False, "Signed preview should report missing credentials offline")
    assert_true("signed:credentials_missing" in report["blockers"], "Signed credential blocker should be surfaced")
    assert_true("BYBIT_API_KEY" in report_text, "Missing credential names may be reported")
    assert_true("fake-key-value" not in report_text, "Preflight report must not echo fake API keys")

    compact = "\n".join(compact_lines(report))
    assert_true("Shadow v8 Bybit preflight" in compact, "Compact report should include title")
    assert_true("Live orders enabled: False" in compact, "Compact report should show live order status")
    assert_true("Signed preview ok: False" in compact, "Compact report should show signed preview status")
    assert_true("instrument_payload_missing" in compact, "Compact report should show blockers")

    print("Bybit preflight report smoke complete")
    print("ok=True")
    print(f"blockers={report['blockers']}")


if __name__ == "__main__":
    main()
