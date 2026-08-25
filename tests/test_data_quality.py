import pandas as pd

from football_prediction_lab.evaluation.data_quality import profile_dataset


def test_profile_dataset_reports_temporal_and_duplicate_quality() -> None:
    frame = pd.DataFrame(
        {
            "match_id": ["m2", "m1", "m1"],
            "kickoff_utc": ["2024-01-02T15:00:00Z", "2024-01-01T15:00:00Z", "2024-01-01T15:00:00Z"],
            "season": ["2425", "2425", "2425"],
            "btts": [1, 0, 1],
        }
    )

    report = profile_dataset(
        frame,
        required_columns=["match_id", "kickoff_utc", "btts"],
        target_columns=["btts"],
    )

    assert report["duplicate_id_rows"] == 1
    assert report["time_parse_failures"] == 0
    assert report["time_monotonic_in_input"] is False
    assert report["target_rates"]["btts"]["mean"] == 2 / 3


def test_profile_dataset_reports_missing_columns_and_group_rates() -> None:
    frame = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "kickoff_utc": ["bad", "2024-01-01T15:00:00Z"],
            "season": ["2425", "2425"],
            "btts": [1, 0],
        }
    )

    report = profile_dataset(
        frame,
        required_columns=["match_id", "kickoff_utc", "missing_metric"],
        target_columns=["btts", "missing_target"],
    )

    assert report["missing_required_columns"] == ["missing_metric"]
    assert report["time_parse_failures"] == 1
    assert report["target_rates"]["missing_target"]["missing"] is True
    assert report["groups"][0]["btts_rate"] == 0.5
