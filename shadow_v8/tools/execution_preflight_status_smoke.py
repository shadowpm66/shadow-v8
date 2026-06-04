from __future__ import annotations

import sys
import types

from shadow_v8.execution.execution_router import ExecutionRouter
from shadow_v8.execution.paper_order_manager import PaperOrderManager


if "requests" not in sys.modules:
    stub = types.ModuleType("requests")
    stub.get = lambda *args, **kwargs: None
    sys.modules["requests"] = stub

from shadow_v8.main import _execution_preflight_status


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    scan_router = ExecutionRouter({}, mode="scan_only")
    scan_status = _execution_preflight_status(scan_router, mode="scan_only")
    assert_true(scan_status["checked"] > 0, "Preflight status should check configured assets")
    assert_true(scan_status["ready"] is False, "Scan-only status should not be execution ready")
    assert_true(scan_status["blocked"] == scan_status["checked"], "Scan-only should block every route")
    assert_true(scan_status["top_block_reasons"], "Scan-only blocks should include reasons")

    paper = PaperOrderManager(account_balance=10_000.0)
    paper_router = ExecutionRouter({"paper": paper}, mode="paper")
    paper_status = _execution_preflight_status(paper_router, mode="paper")
    assert_true(paper_status["checked"] > 0, "Paper status should check configured assets")
    assert_true(paper_status["ready"] is True, "Paper status should be ready when paper executor exists")
    assert_true(paper_status["passed"] == paper_status["checked"], "Paper should pass every enabled asset route")
    assert_true(paper_status["blocked"] == 0, "Paper should not block converted paper routes")

    print("Execution preflight status smoke complete")
    print("ok=True")
    print(f"scan_only_checked={scan_status['checked']}")
    print(f"scan_only_top_blocks={scan_status['top_block_reasons']}")
    print(f"paper_passed={paper_status['passed']}")


if __name__ == "__main__":
    main()
