import pandas as pd

from football_prediction_lab.features.pre_match import build_pre_match_features


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
    assert second["home_avg_scored_5"] == 4.0
    assert second["away_avg_scored_5"] == 4.0
    assert {
        "home_avg_scored_5",
        "away_avg_scored_5",
        "home_points_avg_5",
        "away_points_avg_5",
    }.issubset(result.columns)


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
    assert list(result["home_avg_scored_1"]) == [0.0, 1.0, 2.0]


def test_same_kickoff_time_uses_stable_match_id_order() -> None:
    matches = pd.DataFrame(
        {
            "match_id": ["m2", "m1"],
            "kickoff_utc": ["2024-01-01T15:00:00Z", "2024-01-01T15:00:00Z"],
            "home_team": ["A", "A"],
            "away_team": ["D", "C"],
            "home_goals": [0, 7],
            "away_goals": [0, 1],
            "btts": [0, 1],
        }
    )

    result = build_pre_match_features(matches, window=5)

    assert list(result["match_id"]) == ["m1", "m2"]
    assert list(result["home_matches_before"]) == [0, 1]
    assert list(result["home_avg_scored_5"]) == [0.0, 7.0]
