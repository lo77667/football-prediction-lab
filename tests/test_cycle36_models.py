import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from football_prediction_lab.evaluation.cycle36_model_selection import (
    candidate_names,
    paired_bootstrap,
    select_inner_candidate,
)
from football_prediction_lab.features.cards import CARD_FEATURE_COLUMNS, build_card_features
from football_prediction_lab.features.pre_match import FEATURE_COLUMNS, build_pre_match_features
from football_prediction_lab.models.poisson_btts import PoissonGoalsBtts
from football_prediction_lab.models.poisson_cards import PoissonCardsRate

ROOT = Path(__file__).parents[1]
REPORT_PATH = ROOT / "reports/generated/cycle_36_candidate_evaluation.json"
POLICY_PATH = ROOT / "configs/cycle36_future_holdout_policy.json"


def _btts_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "home_avg_scored_10": [1.0, 1.2, 0.8],
            "away_avg_conceded_10": [1.1, 0.9, 1.0],
            "away_avg_scored_10": [1.3, 0.7, 1.1],
            "home_avg_conceded_10": [0.8, 1.0, 1.2],
            "home_matches_before": [0, 5, 10],
            "away_matches_before": [0, 5, 10],
            "league_avg_goals_before": [2.4, 2.5, 2.3],
        }
    )


def _cards_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "home_avg_yellows_10": [1.0, 2.0, 1.5],
            "away_avg_yellows_10": [1.1, 1.8, 1.7],
            "referee_avg_yellows_10": [3.0, 4.5, 2.5],
            "home_card_matches_before": [0, 5, 10],
            "away_card_matches_before": [0, 5, 10],
        }
    )


def test_poisson_candidates_have_valid_positive_rates_and_probabilities() -> None:
    btts = PoissonGoalsBtts().fit(_btts_frame())
    btts_lambdas = btts.predict_lambdas(_btts_frame())
    btts_probability = btts.predict_probability(_btts_frame())
    assert (btts_lambdas > 0).all().all()
    assert btts_probability.between(0, 1).all()

    cards = PoissonCardsRate().fit(_cards_frame())
    cards_lambda = cards.predict_lambda(_cards_frame())
    cards_probability = cards.predict_probability(_cards_frame())
    assert (cards_lambda > 0).all()
    assert cards_probability.between(0, 1).all()


def test_current_target_mutation_does_not_change_pre_match_features() -> None:
    rows = []
    for index in range(6):
        rows.append(
            {
                "match_id": f"m{index}",
                "kickoff_utc": f"2024-01-{index + 1:02d}T15:00:00Z",
                "home_team": "A" if index % 2 == 0 else "B",
                "away_team": "B" if index % 2 == 0 else "A",
                "home_goals": index % 3,
                "away_goals": (index + 1) % 3,
                "btts": int(index % 2 == 0),
            }
        )
    original = pd.DataFrame(rows)
    mutated = original.copy()
    mutated.loc[3, "btts"] = 1 - mutated.loc[3, "btts"]
    first = build_pre_match_features(original)
    second = build_pre_match_features(mutated)
    assert first.loc[3, list(FEATURE_COLUMNS)].equals(second.loc[3, list(FEATURE_COLUMNS)])
    model = PoissonGoalsBtts().fit(first)
    original_probability = model.predict_probability(first.iloc[[3]])
    mutated_probability = model.predict_probability(second.iloc[[3]])
    assert original_probability.equals(mutated_probability)


def test_later_match_mutation_does_not_change_earlier_prediction_inputs() -> None:
    rows = []
    for index in range(6):
        rows.append(
            {
                "match_id": f"m{index}",
                "kickoff_utc": f"2024-01-{index + 1:02d}T15:00:00Z",
                "home_team": "A" if index % 2 == 0 else "B",
                "away_team": "B" if index % 2 == 0 else "A",
                "home_goals": index % 3,
                "away_goals": (index + 1) % 3,
                "btts": int(index % 2 == 0),
            }
        )
    original = pd.DataFrame(rows)
    mutated = original.copy()
    mutated.loc[5, ["home_goals", "away_goals", "btts"]] = [9, 0, 1]
    first = build_pre_match_features(original)
    second = build_pre_match_features(mutated)
    assert first.loc[0:4, list(FEATURE_COLUMNS)].equals(second.loc[0:4, list(FEATURE_COLUMNS)])


def test_cards_current_match_labels_are_not_in_feature_columns() -> None:
    raw = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "kickoff_utc": pd.to_datetime(["2024-01-01T15:00:00Z", "2024-01-02T15:00:00Z"]),
            "home_team": ["A", "B"],
            "away_team": ["B", "A"],
            "home_yellows": [5, 0],
            "away_yellows": [0, 5],
            "home_reds": [0, 0],
            "away_reds": [0, 0],
            "home_fouls": [10, 11],
            "away_fouls": [11, 10],
            "home_corners": [4, 5],
            "away_corners": [5, 4],
        }
    )
    features = build_card_features(raw)
    assert not {
        "total_yellows",
        "total_yellows_over_3_5",
        "home_yellows",
        "away_yellows",
    }.intersection(CARD_FEATURE_COLUMNS)
    assert set(CARD_FEATURE_COLUMNS).issubset(features.columns)


def test_cycle36_development_rejects_2526() -> None:
    frame = pd.DataFrame(
        {
            "season": ["2425", "2526", "2526"],
            "kickoff_utc": pd.to_datetime(
                ["2025-05-01T15:00:00Z", "2025-08-01T15:00:00Z", "2025-08-02T15:00:00Z"]
            ),
        }
    )
    from football_prediction_lab.evaluation.cycle36_model_selection import market_folds

    with pytest.raises(ValueError, match="2526"):
        market_folds(frame, "btts")


def test_selection_has_no_outer_test_parameter_and_uses_inner_metrics_only() -> None:
    assert "outer_test" not in inspect.signature(select_inner_candidate).parameters
    selected = select_inner_candidate(
        {
            "constant_train_rate": {"brier_score": 0.25, "log_loss": 0.69, "ece_10": 0.03},
            "poisson_goals_btts": {"brier_score": 0.24, "log_loss": 0.68, "ece_10": 0.04},
        }
    )
    assert selected["selected_variant"] == "poisson_goals_btts"
    assert selected["outer_test_used"] is False
    assert selected["selection_used_2526"] is False


def test_bootstrap_is_deterministic_and_grouped_by_match_id() -> None:
    actual = np.array([0, 1, 0, 1, 1, 0])
    candidate = np.array([0.2, 0.8, 0.4, 0.6, 0.7, 0.3])
    baseline = np.full(6, 0.5)
    match_ids = np.array(["m1", "m1", "m2", "m2", "m3", "m3"])
    first = paired_bootstrap(actual, candidate, baseline, match_ids, replicates=50)
    second = paired_bootstrap(actual, candidate, baseline, match_ids, replicates=50)
    assert first == second
    assert first["unit"] == "match_id"


def test_cycle36_artifacts_exclude_2526_and_2627_evaluation() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert "2526" not in report["development_seasons"]
    assert report["guards"]["selection_used_2526"] is False
    assert report["guards"]["2627_evaluated"] is False
    assert policy["future_holdout"] == ["2627"]
    assert policy["commercial_release"] is False


def test_candidate_names_reject_unknown_market() -> None:
    with pytest.raises(ValueError, match="unknown market"):
        candidate_names("unknown")
