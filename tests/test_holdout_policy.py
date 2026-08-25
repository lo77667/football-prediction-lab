import json
from pathlib import Path

import pytest

from football_prediction_lab.evaluation.holdout_policy import (
    POLICY_SCHEMA_VERSION,
    assert_prediction_artifact_safe,
    assert_selection_history_excludes_holdout,
    choose_modal_variant,
    load_policy_lock,
)

ROOT = Path(__file__).parents[1]
LOCK_PATH = ROOT / "configs/cycle35_policy_lock.json"
PREDICTIONS_PATH = ROOT / "reports/generated/cycle_35_2526_predictions_prelabel.json"


def test_modal_variant_uses_fixed_simplicity_tiebreak() -> None:
    decision = choose_modal_variant(
        {
            "constant_train_rate": 3,
            "legacy": 3,
            "expanded": 1,
        }
    )
    assert decision["selected_variant"] == "constant_train_rate"
    assert decision["tied_variants"] == ["constant_train_rate", "legacy"]


def test_selection_history_rejects_protected_holdout() -> None:
    with pytest.raises(ValueError, match="2526.*selection or tuning"):
        assert_selection_history_excludes_holdout(["2425", "2526"])
    assert_selection_history_excludes_holdout(["2324", "2425"])


def test_policy_lock_is_multi_market_and_protects_2526() -> None:
    lock = load_policy_lock(LOCK_PATH)
    assert lock["schema_version"] == POLICY_SCHEMA_VERSION
    assert lock["protected_holdout"] == ["2526"]
    assert lock["commercial_release"] is False
    assert {market: details["selected_variant"] for market, details in lock["markets"].items()} == {
        "btts": "constant_train_rate",
        "cards": "constant_train_rate",
    }
    for details in lock["markets"].values():
        assert "2526" not in details["training_seasons"]
        assert "2526" not in details["calibration_seasons"]


def test_prelabel_artifact_excludes_targets_and_has_unique_matches_per_market() -> None:
    assert_prediction_artifact_safe(
        PREDICTIONS_PATH,
        expected_policy_version="cycle35-deployment-policy-v1",
    )
    payload = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))
    assert payload["stage"] == "prelabel"
    assert payload["evaluation_not_run"] is True
    assert all(
        not {"btts", "total_yellows_over_3_5", "home_goals", "away_goals", "total_yellows"}
        & set(record)
        for record in payload["predictions"]
    )


def test_mutating_2526_labels_does_not_change_policy_or_probabilities(tmp_path: Path) -> None:
    lock_before = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    predictions_before = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))
    mutated_labels = tmp_path / "mutated_2526_labels.json"
    mutated_labels.write_text(
        json.dumps(
            {"2526": {"btts": [1, 0, 1], "total_yellows_over_3_5": [0, 1, 0]}},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    assert mutated_labels.exists()
    lock_after = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    predictions_after = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))
    assert lock_after == lock_before
    assert [
        (row["market"], row["match_id"], row["probability"])
        for row in predictions_after["predictions"]
    ] == [
        (row["market"], row["match_id"], row["probability"])
        for row in predictions_before["predictions"]
    ]
