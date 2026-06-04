from __future__ import annotations

from pathlib import Path
import shutil
import sys
import types

from shadow_v8.execution.execution_router import ExecutionRouter
from shadow_v8.execution.paper_order_manager import PaperOrderManager
from shadow_v8.models import (
    AssetConfig,
    BaseState,
    EntryDecision,
    MarketDataBundle,
    RiskDecision,
    SetupDecision,
    StructureSignal,
)
from shadow_v8.state_store import ClosedTradeStore, PositionStore


if "requests" not in sys.modules:
    stub = types.ModuleType("requests")
    stub.get = lambda *args, **kwargs: None
    sys.modules["requests"] = stub

from shadow_v8.main import _paper_execution_asset, _process_paper_entries


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def scan_result() -> dict:
    symbol = "ROUTERUSDT"
    setup = SetupDecision(symbol=symbol, direction="LONG", setup_class="ROUTER_PAPER", grade="A", final_score=82.0)
    return {
        "asset": AssetConfig(
            symbol=symbol,
            asset_class="crypto",
            broker="bybit",
            allow_long=True,
            allow_short=True,
        ),
        "entry": EntryDecision(
            action="ENTER",
            symbol=symbol,
            direction="LONG",
            reason="Engine router paper smoke",
            setup=setup,
        ),
        "setup": setup,
        "risk": RiskDecision(state="FULL", risk_pct=0.01, reason="Engine router paper smoke"),
        "market": MarketDataBundle(symbol=symbol, asset_class="crypto", last_price=100.0),
        "base": BaseState(found=True, low=94.0, high=106.0, quality_score=75.0),
        "structure": StructureSignal(type="W", direction="LONG", entry=100.0, base=95.0, quality_score=80.0),
    }


def main() -> None:
    root = Path("runtime") / "smoke" / "engine_router_paper"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    paper = PaperOrderManager(
        account_balance=10_000.0,
        store=PositionStore(root / "positions.json"),
        closed_store=ClosedTradeStore(root / "closed.json"),
    )
    router = ExecutionRouter({"paper": paper}, mode="paper")
    result = scan_result()

    paper_asset = _paper_execution_asset(result["asset"])
    assert_true(paper_asset.broker == "paper", "Engine should convert scan assets into paper execution assets")
    assert_true(result["asset"].broker == "bybit", "Original scan asset should remain unchanged")

    executions = _process_paper_entries([result], paper, router)
    assert_true(len(executions) == 1, "One paper execution should be attempted")
    assert_true(executions[0]["ok"] is True, "Paper execution should pass through router")
    position = paper.store.load_all().get(result["asset"].symbol)
    assert_true(position is not None, "Paper position should be opened")
    assert_true(position["broker"] == "paper", "Paper position should store paper broker")

    print("Engine router paper smoke complete")
    print("ok=True")
    print(f"original_broker={result['asset'].broker}")
    print(f"execution_broker={paper_asset.broker}")
    print(f"position_broker={position['broker']}")


if __name__ == "__main__":
    main()
