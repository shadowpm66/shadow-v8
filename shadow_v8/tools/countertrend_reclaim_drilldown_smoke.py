from __future__ import annotations

from shadow_v8.tools.countertrend_reclaim_drilldown import extract_candidate_records, summarize_candidates


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fake_gate() -> dict:
    return {
        "status": "WATCH",
        "blockers": [],
        "watch_reasons": ["countertrend_reclaim_calibration"],
        "warnings": [],
        "confirmations": [
            "constructive_base_or_vcp",
            "pivot_confirmed",
            "volume_quality",
            "reference_confluence",
            "countertrend_reclaim_candidate",
        ],
        "confirmed_count": 5,
        "stage": {
            "weekly_stage": "STAGE_4",
            "daily_stage": "STAGE_4",
            "direction": "LONG",
            "risk_bias": "RISK_ON",
            "reasons": ["daily_not_long_compatible"],
        },
        "countertrend_reclaim": {
            "enabled": True,
            "candidate": True,
            "stage_blocker": "stage_blocks_long",
            "direction": "LONG",
            "stage_pair": "STAGE_4/STAGE_4",
            "reason": "strict_reclaim_candidate",
        },
    }


def fake_confirmation(*, supportive: bool, tight_vcp: bool, shift_bucket: str) -> dict:
    favorable = 2 if supportive else 0
    obstacles = 0 if supportive else 3
    return {
        "pivot": {
            "confirmed": True,
            "reclaimed_or_lost": True,
            "retested": True,
            "retest_hold": True,
            "shift_away": True,
            "shift_progress_state": "ready" if supportive else "insufficient",
            "shift_progress_bucket": shift_bucket,
            "shift_progress": 1.2 if supportive else 0.25,
            "shift_strength": 0.8 if supportive else 0.2,
        },
        "vcp": {
            "is_tight": tight_vcp,
            "is_near_tight": tight_vcp,
            "development_stage": "ready" if tight_vcp else "loose",
            "contraction_count": 3 if tight_vcp else 1,
            "volume_dry": True,
            "breakout_volume": True,
            "directional_close_shift": supportive,
            "directional_evidence": ["higher_closes"] if supportive else [],
        },
        "context": {
            "quality_score": 70 if supportive else 40,
            "regime": "trend",
            "metadata": {
                "reference_confluence": {
                    "favorable_count": favorable,
                    "obstacle_count": obstacles,
                    "at_level_count": 1,
                    "nearest_reference": "daily_open",
                    "flags": ["at_reference_level"],
                }
            },
        },
        "trade_gate": fake_gate(),
    }


def main() -> None:
    result = {
        "trades": [
            {
                "symbol": "SOLUSDT",
                "direction": "LONG",
                "opened_at": "2026-06-01T00:00:00+00:00",
                "entry_score": 92.0,
                "grade": "S",
                "r_multiple": 3.5,
                "entry_reason": "Countertrend reclaim calibration",
                "setup_class": "W",
                "confirmation": fake_confirmation(supportive=True, tight_vcp=True, shift_bucket="near_confirmation"),
            },
            {
                "symbol": "ADAUSDT",
                "direction": "LONG",
                "opened_at": "2026-06-01T01:00:00+00:00",
                "entry_score": 88.0,
                "grade": "A+",
                "r_multiple": -1.0,
                "entry_reason": "Countertrend reclaim calibration",
                "setup_class": "W",
                "confirmation": fake_confirmation(supportive=False, tight_vcp=False, shift_bucket="early"),
            },
        ],
        "skipped_setups": [
            {
                "symbol": "LINKUSDT",
                "timestamp": "2026-06-01T02:00:00+00:00",
                "action": "MONITOR",
                "direction": "LONG",
                "score": 84.0,
                "grade": "A",
                "reason": "Watch only",
                "setup_class": "W",
                "confirmation": fake_confirmation(supportive=True, tight_vcp=False, shift_bucket="building"),
            }
        ],
    }
    records = extract_candidate_records(result)
    summary = summarize_candidates(records)

    assert_true(len(records) == 3, "Drilldown should extract trade and skipped countertrend candidates")
    assert_true(summary["candidate_count"] == 3, "Summary should count all candidates")
    assert_true(summary["entered_count"] == 2, "Summary should count entered candidates")
    assert_true(summary["winner_count"] == 1, "Summary should count winners")
    assert_true(summary["loser_count"] == 1, "Summary should count losers")
    assert_true(summary["net_r"] == 2.5, "Summary should aggregate countertrend candidate R")
    sol_record = next(record for record in records if record["symbol"] == "SOLUSDT")
    ada_record = next(record for record in records if record["symbol"] == "ADAUSDT")
    assert_true(
        "countertrend_into_obstacles" in ada_record["diagnostic_hints"],
        "Losing obstructed candidate should expose obstacle hint",
    )
    assert_true(
        "success_with_reference_and_shift" in sol_record["diagnostic_hints"],
        "Winning supported candidate should expose success pattern",
    )

    print("Countertrend reclaim drilldown smoke complete")
    print("ok=True")
    print(f"candidates={summary['candidate_count']}")
    print(f"entered={summary['entered_count']}")
    print(f"net_r={summary['net_r']}")
    print(f"top_hints={summary['top_diagnostic_hints']}")


if __name__ == "__main__":
    main()
