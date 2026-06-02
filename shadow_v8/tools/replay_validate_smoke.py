from __future__ import annotations

from pathlib import Path

from shadow_v8.tools.replay_validate import discover_csv_files, run_file, summary_row


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    files = discover_csv_files([FIXTURE_DIR])
    assert_true(files, "Replay validator should discover fixture CSV files")
    result = run_file(files[0], symbol="VALIDATE", asset_class="crypto", min_bars=10, allow_short=False)
    row = summary_row(result)
    assert_true(result["ok"] is True, "Replay validation result should be ok")
    assert_true(result["schema_version"] == "1.5.2", "Replay validation should use schema 1.5.2")
    assert_true("gate_analytics" in result, "Replay validation should include gate analytics")
    assert_true("allow_rate" in row, "Replay validation summary should include allow rate")
    assert_true("watch_rate" in row, "Replay validation summary should include watch rate")
    assert_true("allowed_entries" in row, "Replay validation summary should include allowed entry count")
    assert_true("allowed_non_entries" in row, "Replay validation summary should include allowed non-entry count")
    assert_true("top_blocker" in row, "Replay validation summary should include top blocker")

    print("Replay validate smoke complete")
    print("ok=True")
    print(f"files_discovered={len(files)}")
    print(f"symbol={row['symbol']}")
    print(f"allow_rate={row['allow_rate']}")
    print(f"watch_rate={row['watch_rate']}")
    print(f"allowed_entries={row['allowed_entries']}")
    print(f"allowed_non_entries={row['allowed_non_entries']}")
    print(f"top_blocker={row['top_blocker']}")


if __name__ == "__main__":
    main()
