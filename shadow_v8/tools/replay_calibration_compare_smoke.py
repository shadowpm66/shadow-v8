from __future__ import annotations

from pathlib import Path

from shadow_v8.tools.replay_calibration_compare import compare_file, summarize_rows
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
    aggregate = summarize_rows([row])
    assert_true(aggregate["file_count"] == 1, "Aggregate should count compared files")
    assert_true(aggregate["overall_verdict"] == row["verdict"], "Aggregate should preserve single-file verdict")
    assert_true(aggregate["verdict_counts"][row["verdict"]] == 1, "Aggregate should count verdicts")

    print("Replay calibration compare smoke complete")
    print("ok=True")
    print(f"symbol={row['symbol']}")
    print(f"verdict={row['verdict']}")
    print(f"overall_verdict={aggregate['overall_verdict']}")
    print(f"baseline_trades={row['baseline']['trades']}")
    print(f"calibrated_trades={row['calibrated']['trades']}")
    print(f"net_r_delta={row['delta']['net_r']}")


if __name__ == "__main__":
    main()
