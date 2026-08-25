import pandas as pd

from football_prediction_lab.features.pre_match import FEATURE_COLUMNS, build_pre_match_features


def test_current_result_is_not_used_in_features() -> None:
    matches = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "kickoff_utc": ["2024-01-01T12:00:00Z", "2024-01-08T12:00:00Z"],
            "home_team": ["A", "B"],
            "away_team": ["B", "A"],
            "home_goals": [4, 0],
            "away_goals": [4, 0],
            "btts": [1, 0],
        }
    )

    result = build_pre_match_features(matches, window=5)

    first = result.iloc[0]
    second = result.iloc[1]
    assert first["home_matches_before"] == 0
    assert first["away_matches_before"] == 0
    assert second["home_matches_before"] == 1
    assert second["away_matches_before"] == 1
    assert second["home_avg_scored"] == 4.0
    assert second["away_avg_scored"] == 4.0
    assert set(FEATURE_COLUMNS).issubset(result.columns)


def test_features_are_sorted_and_windowed() -> None:
    matches = pd.DataFrame(
        {
            "match_id": ["m3", "m1", "m2"],
            "kickoff_utc": [
                "2024-01-03T12:00:00Z",
                "2024-01-01T12:00:00Z",
                "2024-01-02T12:00:00Z",
            ],
            "home_team": ["A", "A", "A"],
            "away_team": ["B", "B", "B"],
            "home_goals": [3, 1, 2],
            "away_goals": [0, 0, 0],
            "btts": [0, 0, 0],
        }
    )

    result = build_pre_match_features(matches, window=1)

    assert list(result["match_id"]) == ["m1", "m2", "m3"]
    assert list(result["home_matches_before"]) == [0, 1, 1]
    assert list(result["home_avg_scored"]) == [0.0, 1.0, 2.0]
