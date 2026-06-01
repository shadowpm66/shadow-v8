from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from shadow_v8.models import AssetConfig, Candle
from shadow_v8.research.replay import Replay


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "replay_sample.json"


def load_fixture(path: Path = FIXTURE_PATH) -> tuple[AssetConfig, list[Candle], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candles = [
        Candle(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        for row in payload["candles"]
    ]
    asset = AssetConfig(
        symbol=payload.get("symbol", "FIXTUREUSDT"),
        asset_class=payload.get("asset_class", "crypto"),
        broker="paper",
        allow_long=True,
        allow_short=False,
        max_risk_pct=0.01,
    )
    return asset, candles, int(payload.get("min_bars", 10))


def synthetic_candles() -> list[Candle]:
    start = datetime(2026, 1, 1)
    closes = [100 + idx * 0.55 for idx in range(50)]
    closes += [
        128,
        124,
        118,
        113,
        118,
        123,
        127,
        124,
        119,
        114,
        119,
        124,
        130,
        128.5,
        129,
        136,
        129,
        133,
        136,
        138,
        140,
        137,
        136,
        137,
        135,
        136,
        137,
        136,
        138,
        137,
        139,
        138,
        140,
        139,
        141,
        140,
        142,
        141,
        143,
        146,
        149,
    ]
    candles: list[Candle] = []
    previous = closes[0]
    for idx, close in enumerate(closes):
        open_price = previous
        high = max(open_price, close) + 1.2
        low = min(open_price, close) - 1.2
        if idx in (53, 59):
            low -= 2.0
        volume = max(250_000, 1_000_000 - idx * 9_000)
        candles.append(
            Candle(
                timestamp=start + timedelta(days=idx),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
        previous = close
    return candles


def synthetic_asset() -> AssetConfig:
    return AssetConfig(
        symbol="TESTUSDT",
        asset_class="crypto",
        broker="paper",
        allow_long=True,
        allow_short=False,
        max_risk_pct=0.01,
    )


def print_result(label: str, result: dict) -> None:
    metrics = result["metrics"]
    breakdowns = result["breakdowns"]
    gate_analytics = result.get("gate_analytics", {})
    print(f"Replay smoke complete ({label})")
    print(f"schema_version={result['schema_version']}")
    print(f"ok={result['ok']}")
    print(f"symbol={result['symbol']}")
    print(f"bars_processed={result['bars_processed']}")
    print(f"trades={metrics['total_trades']}")
    print(f"skipped_setups={metrics['skipped_setup_count']}")
    print(f"win_rate={metrics['win_rate']}")
    print(f"net_r={metrics['net_r']}")
    print(f"average_r={metrics['average_r']}")
    print(f"best_r={metrics['best_r']}")
    print(f"worst_r={metrics['worst_r']}")
    print(f"max_drawdown_r={metrics['max_drawdown_r']}")
    print(f"profit_factor={metrics['profit_factor']}")
    print(f"expectancy={metrics['expectancy']}")
    print(f"average_trade_duration_bars={metrics['average_trade_duration_bars']}")
    print(f"action_counts={breakdowns['action_counts']}")
    print(f"grade_breakdown={breakdowns['grade_breakdown']}")
    print(f"risk_state_breakdown={breakdowns['risk_state_breakdown']}")
    print(f"gate_status_counts={gate_analytics.get('status_counts')}")
    print(f"gate_allow_rate={gate_analytics.get('allow_rate')}")
    print(f"gate_watch_rate={gate_analytics.get('watch_rate')}")
    print(f"gate_top_blockers={gate_analytics.get('top_blockers')}")
    print(f"gate_top_watch_reasons={gate_analytics.get('top_watch_reasons')}")
    print(f"gate_top_warnings={gate_analytics.get('top_warnings')}")
    print(f"gate_validation_notes={gate_analytics.get('validation_notes')}")
    if result["skipped_setups"]:
        confirmation = result["skipped_setups"][0]["confirmation"]
        vcp = confirmation.get("vcp", {})
        context = confirmation.get("context", {})
        gate = confirmation.get("trade_gate", {})
        nearest = context.get("nearest_zones", [{}])
        print(
            "sample_confirmation: base_confirmed={base_confirmed} pivot_confirmed={pivot_confirmed} "
            "nested_pattern={nested_pattern} stop_distance_quality={stop_distance_quality} "
            "vcp_tightness={vcp_tightness} contractions={contractions} volume_dry={volume_dry} "
            "breakout_volume={breakout_volume} context_score={context_score} nearest_zone={nearest_zone} "
            "gate_status={gate_status} gate_blockers={gate_blockers} gate_watch_reasons={gate_watch_reasons}".format(
                base_confirmed=confirmation["base"].get("confirmed"),
                pivot_confirmed=confirmation["pivot"].get("confirmed"),
                nested_pattern=confirmation["nested"].get("pattern"),
                stop_distance_quality=confirmation.get("stop_distance_quality"),
                vcp_tightness=vcp.get("tightness_score"),
                contractions=vcp.get("contraction_count"),
                volume_dry=vcp.get("volume_dry_up"),
                breakout_volume=vcp.get("breakout_volume"),
                context_score=context.get("quality_score"),
                nearest_zone=nearest[0].get("name") if nearest else None,
                gate_status=gate.get("status"),
                gate_blockers=gate.get("blockers"),
                gate_watch_reasons=gate.get("watch_reasons"),
            )
        )
    for idx, trade in enumerate(result["trades"], start=1):
        confirmation = trade.get("confirmation", {})
        vcp = confirmation.get("vcp", {})
        context = confirmation.get("context", {})
        gate = confirmation.get("trade_gate", {})
        nearest = context.get("nearest_zones", [{}])
        print(
            "trade_{idx}: direction={direction} entry={entry} exit={exit} "
            "duration_bars={duration_bars} mae={mae} mfe={mfe} r_multiple={r_multiple} "
            "base_confirmed={base_confirmed} pivot_confirmed={pivot_confirmed} nested_pattern={nested_pattern} "
            "vcp_tightness={vcp_tightness} contractions={contractions} volume_dry={volume_dry} "
            "breakout_volume={breakout_volume} context_score={context_score} nearest_zone={nearest_zone} "
            "gate_status={gate_status}".format(
                idx=idx,
                base_confirmed=confirmation.get("base", {}).get("confirmed"),
                pivot_confirmed=confirmation.get("pivot", {}).get("confirmed"),
                nested_pattern=confirmation.get("nested", {}).get("pattern"),
                vcp_tightness=vcp.get("tightness_score"),
                contractions=vcp.get("contraction_count"),
                volume_dry=vcp.get("volume_dry_up"),
                breakout_volume=vcp.get("breakout_volume"),
                context_score=context.get("quality_score"),
                nearest_zone=nearest[0].get("name") if nearest else None,
                gate_status=gate.get("status"),
                **trade,
            )
        )


def main() -> None:
    fixture_asset, fixture_candles, fixture_min_bars = load_fixture()
    fixture_result = Replay(
        asset=fixture_asset,
        candles=fixture_candles,
        min_bars=fixture_min_bars,
        input_source={
            "type": "fixture_json",
            "path": str(FIXTURE_PATH),
        },
    ).run()
    print_result("fixture", fixture_result)

    synthetic_result = Replay(
        asset=synthetic_asset(),
        candles=synthetic_candles(),
        min_bars=35,
        input_source={
            "type": "synthetic",
            "description": "Hand-built smoke candles for replay plumbing validation",
        },
    ).run()
    print_result("synthetic", synthetic_result)


if __name__ == "__main__":
    main()
