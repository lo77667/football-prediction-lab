from pathlib import Path

import pandas as pd

from football_prediction_lab.data.football_data import normalize_football_data_csv


def test_normalize_football_data_csv(tmp_path: Path) -> None:
    source = tmp_path / "E0.csv"
    pd.DataFrame(
        {
            "Date": ["16/08/24", "17/08/24"],
            "HomeTeam": [" Home A ", "Home B"],
            "AwayTeam": ["Away A", "Away B"],
            "FTHG": [2, 0],
            "FTAG": [1, 0],
        }
    ).to_csv(source, index=False)

    result = normalize_football_data_csv(
        source,
        competition="Test League",
        season="2425",
    )

    assert list(result["home_team"]) == ["Home A", "Home B"]
    assert list(result["btts"]) == [1, 0]
    assert result["match_id"].is_unique
    assert str(result["kickoff_utc"].dtype).startswith("datetime64[ns, UTC]")
