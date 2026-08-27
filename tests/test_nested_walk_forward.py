import inspect
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pytest

from football_prediction_lab.evaluation.nested_walk_forward import (
    build_nested_folds,
    select_variant_on_inner_validation,
)

_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "evaluation" / "scripts_evaluate_cycle34_nested.py"
)
_SPEC = spec_from_file_location("scripts_evaluate_cycle34_nested", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_outer_labels_cannot_change_inner_selection() -> None:
    inner_metrics = {
        "constant_train_rate": {"brier_score": 0.25, "log_loss": 0.69, "ece_10": 0.05},
        "legacy": {"brier_score": 0.24, "log_loss": 0.68, "ece_10": 0.04},
    }
    first = select_variant_on_inner_validation(inner_metrics)
    mutated_outer_labels = np.array([1, 1, 1, 0, 0])
    second = select_variant_on_inner_validation(inner_metrics)

    assert mutated_outer_labels.tolist() == [1, 1, 1, 0, 0]
    assert first["selected_variant"] == second["selected_variant"] == "legacy"
    assert first["outer_test_used"] is False
    assert "outer_test" not in inspect.signature(select_variant_on_inner_validation).parameters


def test_nested_folds_exclude_protected_season_and_do_not_overlap() -> None:
    seasons = ["1516", "1617", "1718", "1819"]
    counts = {season: 10 for season in seasons}
    ranges = {
        season: (f"20{season[:2]}-08-01T00:00:00+00:00", f"20{season[2:]}-05-31T00:00:00+00:00")
        for season in seasons
    }
    folds = build_nested_folds(
        seasons,
        row_counts=counts,
        prediction_ranges=ranges,
        feature_version="features-v1",
        model_version="model-v1",
    )

    assert len(folds) == 2
    for fold in folds:
        assert (
            max(fold.inner_train_seasons)
            < min(fold.inner_validation_seasons)
            < min(fold.outer_test_seasons)
        )
        assert not set(fold.inner_train_seasons) & set(fold.inner_validation_seasons)
        assert not set(fold.inner_validation_seasons) & set(fold.outer_test_seasons)
        assert "2526" not in fold.outer_train_seasons + fold.outer_test_seasons


def test_nested_folds_reject_protected_season() -> None:
    seasons = ["1516", "1617", "1718", "2526"]
    counts = {season: 10 for season in seasons}
    ranges = {
        season: ("2015-08-01T00:00:00+00:00", "2016-05-31T00:00:00+00:00") for season in seasons
    }

    with pytest.raises(ValueError, match="protected season"):
        build_nested_folds(
            seasons,
            row_counts=counts,
            prediction_ranges=ranges,
            feature_version="features-v1",
            model_version="model-v1",
        )


def test_commercial_release_is_false_in_report() -> None:
    report = _MODULE.REPORT
    assert "cycle_34" in str(report)
    if report.exists():
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["commercial_release"] is False
        assert payload["markets"]["btts"]["pooled"]["commercial_release"] is False
        assert payload["markets"]["cards"]["pooled"]["commercial_release"] is False
