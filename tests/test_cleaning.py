import pandas as pd

from football_prediction_lab.data.cleaning import clean_matches


def test_clean_matches_removes_invalid_and_duplicate_rows() -> None:
    frame = pd.DataFrame(
        {
            "match_id": ["m1", "m1", "m2"],
            "kickoff_utc": ["2024-01-02T00:00:00Z", "2024-01-02T00:00:00Z", None],
            "competition": ["League", "League", "League"],
            "season": ["2023", "2023", "2023"],
            "home_team": [" Home A ", "Home A", "Home B"],
            "away_team": ["Away A", "Away A", "Away B"],
            "home_goals": [1, 1, -1],
            "away_goals": [1, 1, 0],
            "btts": [0, 0, 0],
            "source": ["test", "test", "test"],
        }
    )

    cleaned, report = clean_matches(frame)

    assert len(cleaned) == 1
    assert cleaned.loc[0, "home_team"] == "Home A"
    assert cleaned.loc[0, "btts"] == 1
    assert report == {
        "initial_rows": 3,
        "invalid_rows_removed": 1,
        "duplicate_rows_removed": 1,
        "final_rows": 1,
    }


def test_clean_matches_applies_team_aliases() -> None:
    frame = pd.DataFrame(
        {
            "match_id": ["m1"],
            "kickoff_utc": ["2024-01-02T00:00:00Z"],
            "competition": ["League"],
            "season": ["2023"],
            "home_team": ["Old Name"],
            "away_team": ["Away"],
            "home_goals": [0],
            "away_goals": [1],
            "btts": [1],
            "source": ["test"],
        }
    )

    cleaned, _ = clean_matches(frame, team_aliases={"Old Name": "New Name"})

    assert cleaned.loc[0, "home_team"] == "New Name"
    assert cleaned.loc[0, "btts"] == 0
