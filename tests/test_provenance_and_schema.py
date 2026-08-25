from datetime import UTC

import pandas as pd
import pytest

from football_prediction_lab.data.football_data import normalize_football_data_csv
from football_prediction_lab.data.provenance import (
    assert_identity_columns_match,
    build_manifest,
)
from football_prediction_lab.evaluation.data_quality import profile_dataset
from football_prediction_lab.models.btts import BttsLogisticBaseline
from football_prediction_lab.models.cards import TotalYellowCardsBaseline


def test_normalization_round_trip_preserves_timezone_and_time(tmp_path) -> None:
    source = tmp_path / "E0.csv"
    pd.DataFrame(
        {
            "Date": ["01/01/25", "01/01/25"],
            "Time": ["15:00", "12:30"],
            "HomeTeam": ["Home B", "Home A"],
            "AwayTeam": ["Away B", "Away A"],
            "FTHG": [1, 0],
            "FTAG": [0, 2],
        }
    ).to_csv(source, index=False)

    normalized = normalize_football_data_csv(
        source,
        competition="Test League",
        season="2425",
    )
    output = tmp_path / "normalized.csv"
    normalized.to_csv(output, index=False)
    reloaded = pd.read_csv(output, parse_dates=["kickoff_utc"])

    assert str(reloaded["kickoff_utc"].dtype).startswith("datetime64[ns, UTC]")
    assert list(reloaded["kickoff_utc"].dt.hour) == [12, 15]
    assert list(reloaded["kickoff_utc"].dt.minute) == [30, 0]
    assert reloaded["match_id"].is_unique


def test_identity_columns_match_sorted_input() -> None:
    input_frame = pd.DataFrame(
        {
            "match_id": ["late", "early"],
            "kickoff_utc": [
                pd.Timestamp("2025-01-01 15:00:00", tz=UTC),
                pd.Timestamp("2025-01-01 12:00:00", tz=UTC),
            ],
        }
    )
    output_frame = input_frame.sort_values("kickoff_utc").reset_index(drop=True)

    assert_identity_columns_match(input_frame, output_frame)


def test_identity_columns_match_rejects_timestamp_change() -> None:
    input_frame = pd.DataFrame(
        {
            "match_id": ["m1"],
            "kickoff_utc": [pd.Timestamp("2025-01-01 15:00:00", tz=UTC)],
        }
    )
    output_frame = input_frame.copy()
    output_frame.loc[0, "kickoff_utc"] = pd.Timestamp("2025-01-01 00:00:00", tz=UTC)

    with pytest.raises(ValueError, match="does not match"):
        assert_identity_columns_match(input_frame, output_frame)


def test_manifest_contains_auditable_generation_metadata() -> None:
    frame = pd.DataFrame(
        {
            "match_id": ["m1"],
            "kickoff_utc": [pd.Timestamp("2025-01-01 15:00:00", tz=UTC)],
        }
    )
    manifest = build_manifest(
        input_path="data/raw/E0.csv",
        input_sha256="a" * 64,
        output_path="data/processed/2425_E0.csv",
        rows_before=1,
        rows_after=1,
        frame=frame,
        feature_version="test-v1",
    )

    assert manifest["input_sha256"] == "a" * 64
    assert manifest["rows_before"] == 1
    assert manifest["rows_after"] == 1
    assert manifest["timezone"] == "UTC"
    assert manifest["feature_version"] == "test-v1"
    assert manifest["generated_at_utc"]


def test_quality_profile_detects_invalid_provenance_fields() -> None:
    frame = pd.DataFrame(
        {
            "match_id": ["m1", "m1", "m2"],
            "kickoff_utc": [
                pd.Timestamp("2025-01-01 15:00:00", tz=UTC),
                pd.Timestamp("2025-01-01 15:00:00", tz=UTC),
                pd.Timestamp("2025-01-01 16:00:00", tz=UTC),
            ],
            "home_team": ["Home", "Home", ""],
            "away_team": ["Away", "Away", "Away 2"],
            "home_goals": [1, 1, -1],
            "away_goals": [0, 0, 0],
        }
    )

    result = profile_dataset(
        frame,
        required_columns=["match_id", "kickoff_utc", "home_team", "away_team"],
    )

    assert result["duplicate_id_rows"] == 1
    assert result["duplicate_match_context_rows"] == 1
    assert result["blank_team_rows"] == 1
    assert result["negative_value_rows"]["home_goals"] == 1
    assert result["timezone_aware"] is True


@pytest.mark.parametrize(
    "model_class, target_column",
    [
        (BttsLogisticBaseline, "btts"),
        (TotalYellowCardsBaseline, "total_yellows_over_3_5"),
    ],
)
def test_models_reject_post_match_feature_columns(model_class, target_column) -> None:
    del target_column
    with pytest.raises(ValueError, match="post-match"):
        model_class(feature_columns=["home_goals"])
