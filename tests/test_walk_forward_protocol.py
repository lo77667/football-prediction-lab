import pytest

from football_prediction_lab.evaluation.walk_forward_protocol import build_season_folds


def metadata() -> tuple[dict[str, int], dict[str, tuple[str, str]]]:
    seasons = ["1516", "1617", "1718", "1819", "1920"]
    counts = {season: 10 for season in seasons}
    ranges = {
        season: (f"20{season[:2]}-08-01T00:00:00+00:00", f"20{season[2:]}-05-31T00:00:00+00:00")
        for season in seasons
    }
    return counts, ranges


def test_expanding_folds_are_strictly_chronological_and_disjoint() -> None:
    counts, ranges = metadata()

    folds = build_season_folds(
        counts,
        row_counts=counts,
        prediction_ranges=ranges,
        feature_version="features-v1",
        model_version="model-v1",
    )

    assert folds
    for fold in folds:
        assert max(fold.train_seasons) < min(fold.calibration_seasons) < min(fold.test_seasons)
        assert not set(fold.train_seasons) & set(fold.calibration_seasons)
        assert not set(fold.train_seasons) & set(fold.test_seasons)
        assert not set(fold.calibration_seasons) & set(fold.test_seasons)
        assert "2526" not in fold.train_seasons + fold.calibration_seasons + fold.test_seasons


def test_protected_season_is_rejected_before_fold_creation() -> None:
    counts, ranges = metadata()
    counts["2526"] = 10
    ranges["2526"] = ("2025-08-01T00:00:00+00:00", "2026-05-31T00:00:00+00:00")

    with pytest.raises(ValueError, match="protected seasons"):
        build_season_folds(
            counts,
            row_counts=counts,
            prediction_ranges=ranges,
            feature_version="features-v1",
            model_version="model-v1",
        )


def test_missing_fold_metadata_is_rejected() -> None:
    counts, ranges = metadata()
    del ranges["1819"]

    with pytest.raises(ValueError, match="metadata is incomplete"):
        build_season_folds(
            counts,
            row_counts=counts,
            prediction_ranges=ranges,
            feature_version="features-v1",
            model_version="model-v1",
        )


def test_insufficient_seasons_are_rejected() -> None:
    with pytest.raises(ValueError, match="at least one train"):
        build_season_folds(
            ["1516", "1617"],
            row_counts={"1516": 10, "1617": 10},
            prediction_ranges={
                "1516": ("2015-08-01T00:00:00+00:00", "2016-05-31T00:00:00+00:00"),
                "1617": ("2016-08-01T00:00:00+00:00", "2017-05-31T00:00:00+00:00"),
            },
            feature_version="features-v1",
            model_version="model-v1",
        )
