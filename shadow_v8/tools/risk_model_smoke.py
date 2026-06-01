from __future__ import annotations

from pathlib import Path

from shadow_v8.execution.paper_order_manager import PaperOrderManager
from shadow_v8.models import AssetConfig, EntryDecision, SetupDecision
from shadow_v8.state_store import ClosedTradeStore, PositionStore
from shadow_v8.strategy.risk_manager import RiskManager


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def setup(symbol: str, grade: str, *, stop_distance_pct: float | None = None) -> SetupDecision:
    metadata = {}
    if stop_distance_pct is not None:
        metadata["base_confirmation"] = {"stop_distance_pct": stop_distance_pct}
    return SetupDecision(
        symbol=symbol,
        direction="LONG",
        setup_class="RISK_SMOKE",
        grade=grade,
        final_score=80.0,
        metadata=metadata,
    )


def asset(symbol: str, asset_class: str, max_risk_pct: float = 0.99) -> AssetConfig:
    return AssetConfig(
        symbol=symbol,
        asset_class=asset_class,
        broker="paper",
        allow_long=True,
        allow_short=True,
        max_risk_pct=max_risk_pct,
    )


def check_crypto_forex_tiers() -> None:
    manager = RiskManager()
    crypto = asset("ETHUSDT", "crypto")
    expected = {
        "B": 0.005,
        "B+": 0.01,
        "A": 0.015,
        "A+": 0.02,
        "S": 0.025,
        "S+": 0.03,
    }
    for grade, risk_pct in expected.items():
        decision = manager.evaluate(crypto, setup("ETHUSDT", grade))
        assert_true(decision.risk_pct == risk_pct, f"{grade} crypto risk should be {risk_pct}")
        assert_true(decision.risk_pct <= 0.03, f"{grade} crypto risk should never exceed 3%")

    forex = asset("EURUSD", "forex")
    decision = manager.evaluate(forex, setup("EURUSD", "S+"))
    assert_true(decision.risk_pct == 0.03, "S+ forex risk should cap at 3%")


def check_stock_allocation_model() -> None:
    manager = RiskManager()
    stock = asset("NVDA", "stock")

    b = manager.evaluate(stock, setup("NVDA", "B", stop_distance_pct=5.0))
    assert_true(b.metadata["sizing_model"] == "stock_allocation", "Stocks should use allocation sizing")
    assert_true(b.metadata["position_pct"] == 0.15, "B stock position should be 15%")
    assert_true(b.risk_pct == 0.0075, "15% position x 5% stop should risk 0.75% account")

    a = manager.evaluate(stock, setup("NVDA", "A", stop_distance_pct=5.0))
    assert_true(a.metadata["position_pct"] == 0.20, "A stock position should be 20%")
    assert_true(a.risk_pct == 0.01, "20% position x 5% stop should risk 1.0% account")

    s_plus = manager.evaluate(stock, setup("NVDA", "S+", stop_distance_pct=6.0))
    assert_true(s_plus.metadata["position_pct"] == 0.25, "S+ stock position should cap at 25%")
    assert_true(s_plus.risk_pct == 0.015, "25% position x 6% stop should risk 1.5% account")
    assert_true(s_plus.metadata["wide_structure_risk"] is True, "6% stock stop should flag wide structure risk")

    too_wide = manager.evaluate(stock, setup("NVDA", "S+", stop_distance_pct=10.0))
    assert_true(too_wide.metadata["wide_structure_risk"] is True, "10% stock stop should flag wide structure risk")
    assert_true(too_wide.metadata["reduced_for_account_risk"] is True, "10% stop should reduce position")
    assert_true(too_wide.metadata["position_pct"] == 0.15, "10% stop should reduce position to 15%")
    assert_true(too_wide.risk_pct == 0.015, "Reduced stock account risk should cap at 1.5%")


def check_paper_stock_allocation_size() -> None:
    tmp_dir = Path("runtime") / "risk_model_smoke"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    position_store = PositionStore(tmp_dir / "positions.json")
    closed_store = ClosedTradeStore(tmp_dir / "closed.json")
    position_store.save_all({})

    stock = asset("ALLOC", "stock")
    risk = RiskManager().evaluate(stock, setup("ALLOC", "S+", stop_distance_pct=6.0))
    decision = EntryDecision(
        action="ENTER",
        symbol="ALLOC",
        direction="LONG",
        reason="Risk model smoke",
        entry=100.0,
        stop=94.0,
        setup=setup("ALLOC", "S+", stop_distance_pct=6.0),
        metadata={
            "risk_pct": risk.risk_pct,
            "risk_state": risk.state,
            "risk_reason": risk.reason,
            **risk.metadata,
        },
    )
    result = PaperOrderManager(
        account_balance=10_000.0,
        store=position_store,
        closed_store=closed_store,
    ).enter(stock, decision)
    assert_true(result["ok"] is True, "Paper stock allocation entry should open")
    position = result["position"]
    assert_true(position["qty"] == 25.0, "25% stock allocation at $100 should buy 25 shares")
    assert_true(position["risk_pct"] == 0.015, "Paper stock account risk should be 1.5%")
    assert_true(position["risk_dollars"] == 150.0, "Paper stock account risk should be $150")
    assert_true(position["metadata"]["wide_structure_risk"] is True, "Paper position should preserve wide risk flag")


def main() -> None:
    check_crypto_forex_tiers()
    check_stock_allocation_model()
    check_paper_stock_allocation_size()
    print("Risk model smoke complete")
    print("ok=True")
    print("crypto_forex_cap=0.03")
    print("stock_position_tiers=B/B+:15%, A:20%, A+/S/S+:25%")
    print("wide_structure_risk=flagged above 5% stop distance")


if __name__ == "__main__":
    main()
