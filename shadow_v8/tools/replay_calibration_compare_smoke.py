from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from shadow_v8.tools.replay_calibration_compare import compare_file, evaluate_guard, guard_options_from_args, summarize_rows
from shadow_v8.tools.replay_validate import discover_csv_files


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    files = discover_csv_files([FIXTURE_DIR])
    assert_true(files, "Calibration compare should discover fixture CSV files")
    row = compare_file(files[0], symbol="CALIBRATE", asset_class="crypto", min_bars=10, allow_short=False)
    assert_true(row["baseline"]["symbol"] == "CALIBRATE", "Baseline should use symbol override")
    assert_true(row["calibrated"]["symbol"] == "CALIBRATE", "Calibrated replay should use symbol override")
    assert_true("delta" in row, "Comparison should include delta metrics")
    assert_true("net_r" in row["delta"], "Comparison delta should include net R")
    assert_true(row["verdict"] in ("improved", "unchanged", "worse"), "Comparison should classify verdict")
    stage_row = compare_file(
        files[0],
        symbol="CALIBRATE",
        asset_class="crypto",
        min_bars=10,
        allow_short=False,
        calibrate_intraday_stage=True,
    )
    assert_true(
        stage_row["calibration"]["allow_intraday_stage_calibration"] is True,
        "Comparison should expose intraday stage calibration mode",
    )
    aggregate = summarize_rows([row])
    assert_true(aggregate["file_count"] == 1, "Aggregate should count compared files")
    assert_true(aggregate["overall_verdict"] == row["verdict"], "Aggregate should preserve single-file verdict")
    assert_true(aggregate["verdict_counts"][row["verdict"]] == 1, "Aggregate should count verdicts")
    passing_guard = evaluate_guard([row], fail_on_worse=True, max_net_r_regression=0.0, max_added_trades=0)
    assert_true(passing_guard["ok"] is True, "Unchanged calibration should pass strict guard")
    strict_options = guard_options_from_args(
        SimpleNamespace(
            strict_guard=True,
            fail_on_worse=False,
            max_net_r_regression=None,
            max_added_trades=None,
        )
    )
    assert_true(strict_options["fail_on_worse"] is True, "Strict guard should fail on worse verdicts")
    assert_true(strict_options["max_net_r_regression"] == 0.0, "Strict guard should reject any net R regression")
    assert_true(strict_options["max_added_trades"] == 0, "Strict guard should reject added trades")
    worse_row = dict(row)
    worse_row["verdict"] = "worse"
    worse_row["delta"] = dict(row["delta"], net_r=-0.25, trades=2)
    failing_guard = evaluate_guard([worse_row], fail_on_worse=True, max_net_r_regression=0.1, max_added_trades=1)
    assert_true(failing_guard["ok"] is False, "Worse calibration should fail guard")
    assert_true(failing_guard["failure_count"] == 3, "Guard should report each failed threshold")

    print("Replay calibration compare smoke complete")
    print("ok=True")
    print(f"symbol={row['symbol']}")
    print(f"verdict={row['verdict']}")
    print(f"overall_verdict={aggregate['overall_verdict']}")
    print(f"guard_ok={passing_guard['ok']}")
    print("strict_guard=preset")
    print(f"guard_failure_count={failing_guard['failure_count']}")
    print(f"baseline_trades={row['baseline']['trades']}")
    print(f"calibrated_trades={row['calibrated']['trades']}")
    print(f"net_r_delta={row['delta']['net_r']}")
    print(f"intraday_stage_calibration={stage_row['calibration']['allow_intraday_stage_calibration']}")


if __name__ == "__main__":
    main()
