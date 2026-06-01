from __future__ import annotations

from datetime import datetime

from shadow_v8.models import AssetConfig, Candle, EntryDecision, SetupDecision
from shadow_v8.research.replay import Replay
from shadow_v8.research.simulator import Simulator
from shadow_v8.tools.replay_smoke import load_fixture


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def candle(timestamp: str, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp=datetime.fromisoformat(timestamp),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100_000,
    )


def asset(symbol: str = "UNITUSDT", allow_short: bool = True) -> AssetConfig:
    return AssetConfig(
        symbol=symbol,
        asset_class="crypto",
        broker="paper",
        allow_long=True,
        allow_short=allow_short,
        max_risk_pct=0.01,
    )


def entry_decision(symbol: str, direction: str, entry: float, stop: float) -> EntryDecision:
    return EntryDecision(
        action="ENTER",
        symbol=symbol,
        direction=direction,
        reason="Unit smoke synthetic entry",
        entry=entry,
        stop=stop,
        setup=SetupDecision(symbol=symbol, direction=direction, setup_class="UNIT", grade="A", final_score=80.0),
    )


def check_replay_fixture() -> dict:
    fixture_asset, fixture_candles, min_bars = load_fixture()
    result = Replay(asset=fixture_asset, candles=fixture_candles, min_bars=min_bars).run()
    assert_true(result["ok"] is True, "Replay fixture result should be ok=True")
    assert_true(result["schema_version"] == "1.4.0", "Replay result should include schema_version")
    assert_true("metrics" in result, "Replay result should include metrics")
    assert_true("breakdowns" in result, "Replay result should include breakdowns")
    assert_true("gate_analytics" in result, "Replay result should include gate analytics")
    assert_true(result["bars_processed"] == len(fixture_candles), "Replay should return bars_processed")
    assert_true(result["skipped_setup_count"] > 0, "Replay should record skipped setups")
    assert_true("action_counts" in result["breakdowns"], "Replay result should include action counts")
    assert_true("confirmation" in result["skipped_setups"][0], "Skipped setups should include confirmation fields")
    assert_true("base" in result["skipped_setups"][0]["confirmation"], "Confirmation should include base fields")
    assert_true("vcp" in result["skipped_setups"][0]["confirmation"], "Confirmation should include VCP fields")
    assert_true("pivot" in result["skipped_setups"][0]["confirmation"], "Confirmation should include pivot fields")
    assert_true("nested" in result["skipped_setups"][0]["confirmation"], "Confirmation should include nested fields")
    assert_true("context" in result["skipped_setups"][0]["confirmation"], "Confirmation should include context fields")
    assert_true("trade_gate" in result["skipped_setups"][0]["confirmation"], "Confirmation should include trade gate fields")
    vcp = result["skipped_setups"][0]["confirmation"]["vcp"]
    assert_true("tightness_score" in vcp, "VCP confirmation should include tightness score")
    assert_true("contraction_count" in vcp, "VCP confirmation should include contraction count")
    assert_true("volume_dry_up" in vcp, "VCP confirmation should include volume dry-up")
    assert_true("breakout_volume" in vcp, "VCP confirmation should include breakout volume")
    context = result["skipped_setups"][0]["confirmation"]["context"]
    assert_true("quality_score" in context, "Context confirmation should include quality score")
    assert_true("nearest_zones" in context, "Context confirmation should include nearest zones")
    assert_true("regime" in context, "Context confirmation should include market regime")
    assert_true("reference_confluence" in context["metadata"], "Context metadata should include reference confluence")
    reference = context["metadata"]["reference_confluence"]
    assert_true("nearest_reference" in reference, "Reference confluence should include nearest reference")
    assert_true("flags" in reference, "Reference confluence should include flags")
    gate = result["skipped_setups"][0]["confirmation"]["trade_gate"]
    assert_true("status" in gate, "Trade gate should include status")
    assert_true("blockers" in gate, "Trade gate should include blockers")
    analytics = result["gate_analytics"]
    assert_true(analytics["evaluated_setups"] > 0, "Gate analytics should count evaluated setups")
    assert_true(analytics["blocked_setups"] > 0, "Gate analytics should count blocked setups")
    assert_true(analytics["top_blockers"], "Gate analytics should include top blockers")
    return result


def check_long_simulator() -> dict:
    unit_asset = asset("LONGUNIT")
    simulator = Simulator()
    opened = candle("2026-02-01T00:00:00", 100.0, 101.0, 99.0, 100.0)
    simulator.open_position(unit_asset, entry_decision("LONGUNIT", "LONG", entry=100.0, stop=95.0), opened)
    simulator.on_bar(candle("2026-02-02T00:00:00", 100.0, 106.0, 98.0, 104.0))
    trade = simulator.close_position(candle("2026-02-03T00:00:00", 104.0, 111.0, 103.0, 110.0), "Unit close")
    assert_true(trade["r_multiple"] == 2.0, "LONG R-multiple should be 2.0")
    assert_true("mae" in trade and "mfe" in trade, "LONG trade should include MAE/MFE")
    return trade


def check_short_simulator() -> dict:
    unit_asset = asset("SHORTUNIT", allow_short=True)
    simulator = Simulator()
    opened = candle("2026-03-01T00:00:00", 100.0, 101.0, 99.0, 100.0)
    simulator.open_position(unit_asset, entry_decision("SHORTUNIT", "SHORT", entry=100.0, stop=105.0), opened)
    simulator.on_bar(candle("2026-03-02T00:00:00", 100.0, 102.0, 94.0, 96.0))
    trade = simulator.close_position(candle("2026-03-03T00:00:00", 96.0, 97.0, 89.0, 90.0), "Unit close")
    assert_true(trade["r_multiple"] == 2.0, "SHORT R-multiple should be 2.0")
    assert_true("mae" in trade and "mfe" in trade, "SHORT trade should include MAE/MFE")
    return trade


def main() -> None:
    replay_result = check_replay_fixture()
    long_trade = check_long_simulator()
    short_trade = check_short_simulator()

    print("Replay unit smoke complete")
    print("ok=True")
    print(f"fixture_bars_processed={replay_result['bars_processed']}")
    print(f"fixture_skipped_setups={replay_result['skipped_setup_count']}")
    print(f"fixture_schema_version={replay_result['schema_version']}")
    print(f"fixture_net_r={replay_result['metrics']['net_r']}")
    print(f"fixture_action_counts={replay_result['breakdowns']['action_counts']}")
    print(f"fixture_gate_analytics={replay_result['gate_analytics']}")
    print(f"fixture_confirmation_keys={list(replay_result['skipped_setups'][0]['confirmation'].keys())}")
    print(f"fixture_vcp_keys={list(replay_result['skipped_setups'][0]['confirmation']['vcp'].keys())}")
    print(f"fixture_context_keys={list(replay_result['skipped_setups'][0]['confirmation']['context'].keys())}")
    print(f"fixture_trade_gate={replay_result['skipped_setups'][0]['confirmation']['trade_gate']}")
    print(
        "long_trade: r_multiple={r_multiple} mae={mae} mfe={mfe}".format(
            r_multiple=long_trade["r_multiple"],
            mae=long_trade["mae"],
            mfe=long_trade["mfe"],
        )
    )
    print(
        "short_trade: r_multiple={r_multiple} mae={mae} mfe={mfe}".format(
            r_multiple=short_trade["r_multiple"],
            mae=short_trade["mae"],
            mfe=short_trade["mfe"],
        )
    )


if __name__ == "__main__":
    main()
