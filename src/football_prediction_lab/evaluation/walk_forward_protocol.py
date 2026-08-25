"""Strict chronological fold definitions for Cycle 33 evaluation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: str
    train_seasons: tuple[str, ...]
    calibration_seasons: tuple[str, ...]
    test_seasons: tuple[str, ...]
    train_cutoff: str
    prediction_start: str
    prediction_end: str
    train_rows: int
    calibration_rows: int
    test_rows: int
    feature_version: str
    model_version: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_season_folds(
    seasons: Iterable[str],
    *,
    row_counts: dict[str, int],
    prediction_ranges: dict[str, tuple[str, str]],
    feature_version: str,
    model_version: str,
    protected_seasons: set[str] | None = None,
    calibration_seasons: int = 1,
) -> list[WalkForwardFold]:
    """Build expanding-window folds: train, prior calibration season, next test season."""

    protected = protected_seasons or {"2526"}
    ordered = tuple(sorted({str(season) for season in seasons}))
    if any(season in protected for season in ordered):
        raise ValueError("protected seasons cannot appear in evaluation folds")
    if calibration_seasons < 1:
        raise ValueError("calibration_seasons must be positive")
    if len(ordered) <= calibration_seasons + 1:
        raise ValueError("at least one train, calibration, and test season are required")

    folds: list[WalkForwardFold] = []
    for index in range(calibration_seasons + 1, len(ordered)):
        train = ordered[: index - calibration_seasons]
        calibration = ordered[index - calibration_seasons : index]
        test = (ordered[index],)
        if not train or not calibration or not test:
            raise ValueError("fold partitions must all be non-empty")
        train_max = max(train)
        calibration_min = min(calibration)
        test_min = min(test)
        if not train_max < calibration_min < test_min:
            raise ValueError("fold partitions must be strictly chronological")
        if set(train) & set(calibration) or set(train) & set(test) or set(calibration) & set(test):
            raise ValueError("fold partitions must not overlap")
        if any(season in protected for season in train + calibration + test):
            raise ValueError("protected season entered a fold")
        missing_counts = set(train + calibration + test).difference(row_counts)
        missing_ranges = set(test).difference(prediction_ranges)
        if missing_counts or missing_ranges:
            raise ValueError("fold metadata is incomplete")
        prediction_start, prediction_end = prediction_ranges[test[0]]
        folds.append(
            WalkForwardFold(
                fold_id=f"fold_{len(folds) + 1:02d}",
                train_seasons=train,
                calibration_seasons=calibration,
                test_seasons=test,
                train_cutoff=f"{train_max}-12-31T23:59:59Z",
                prediction_start=prediction_start,
                prediction_end=prediction_end,
                train_rows=sum(row_counts[season] for season in train),
                calibration_rows=sum(row_counts[season] for season in calibration),
                test_rows=sum(row_counts[season] for season in test),
                feature_version=feature_version,
                model_version=model_version,
            )
        )
    return folds
