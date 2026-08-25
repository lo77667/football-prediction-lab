import pandas as pd

from football_prediction_lab.features.cards import CARD_FEATURE_COLUMNS, build_card_features


def test_card_features_use_only_previous_matches() -> None:
    matches = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "kickoff_utc": ["2024-01-01T12:00:00Z", "2024-01-08T12:00:00Z"],
            "home_team": ["A", "B"],
            "away_team": ["B", "A"],
            "home_yellows": [5, 1],
            "away_yellows": [4, 2],
            "home_reds": [0, 0],
            "away_reds": [0, 0],
        }
    )
    result = build_card_features(matches)
    first = result.iloc[0]
    second = result.iloc[1]
    assert first["home_card_matches_before"] == 0
    assert first["away_card_matches_before"] == 0
    assert second["home_avg_yellows"] == 4.0
    assert second["away_avg_yellows"] == 5.0
    assert set(CARD_FEATURE_COLUMNS).issubset(result.columns)


def test_card_market_target_is_over_three_point_five() -> None:
    matches = pd.DataFrame(
        {
            "match_id": ["m1"],
            "kickoff_utc": ["2024-01-01T12:00:00Z"],
            "home_team": ["A"],
            "away_team": ["B"],
            "home_yellows": [2],
            "away_yellows": [2],
            "home_reds": [0],
            "away_reds": [0],
        }
    )
    result = build_card_features(matches)
    assert result.loc[0, "total_yellows_over_3_5"] == 1
