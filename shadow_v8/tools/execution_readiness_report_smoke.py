from __future__ import annotations

import json

from shadow_v8.tools.execution_readiness_report import build_execution_readiness_report, compact_lines


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    fake_env = {"BYBIT_API_KEY": "fake-key-value", "BYBIT_API_SECRET": "fake-secret-value"}
    scan_report = build_execution_readiness_report(mode="scan_only", env=fake_env)
    assert_true(scan_report["ready"] is False, "Scan-only report should not be ready")
    assert_true(scan_report["assets_checked"] > 0, "Report should include enabled assets")

    paper_report = build_execution_readiness_report(mode="paper", env=fake_env)
    assert_true(paper_report["ready"] is True, "Paper report should be ready with paper executor")

    live_report = build_execution_readiness_report(mode="live_guarded", env=fake_env)
    live_text = json.dumps(live_report, sort_keys=True)
    assert_true(live_report["ready"] is False, "Live report should remain blocked while adapters are placeholders")
    assert_true("fake-key-value" not in live_text, "Readiness report must not echo API key values")
    assert_true("fake-secret-value" not in live_text, "Readiness report must not echo API secret values")
    assert_true(any("adapter_placeholder" == item["reason"] for item in live_report["top_blockers"]), "Placeholder adapter should be reported")

    compact = "\n".join(compact_lines(live_report))
    assert_true("Shadow v8 execution readiness" in compact, "Compact report should include title")
    assert_true("missing_env=" in compact, "Compact report should show missing env field")
    assert_true("fake-key-value" not in compact, "Compact report must not echo API key values")

    print("Execution readiness report smoke complete")
    print("ok=True")
    print(f"scan_ready={scan_report['ready']}")
    print(f"paper_ready={paper_report['ready']}")
    print(f"live_top_blockers={live_report['top_blockers']}")


if __name__ == "__main__":
    main()
