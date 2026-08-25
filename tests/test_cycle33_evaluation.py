from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np

_SCRIPT = Path(__file__).parents[1] / "scripts_evaluate_cycle33.py"
_SPEC = spec_from_file_location("scripts_evaluate_cycle33", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_paired_bootstrap_is_deterministic_and_declares_match_unit() -> None:
    actual = np.array([0, 1, 0, 1, 1, 0])
    candidate = np.array([0.2, 0.8, 0.4, 0.7, 0.6, 0.3])
    baseline = np.full(6, 0.5)
    groups = np.array(["m1", "m1", "m2", "m2", "m3", "m3"])

    first = _MODULE._paired_bootstrap(actual, candidate, baseline, groups=groups, replicates=20)
    second = _MODULE._paired_bootstrap(actual, candidate, baseline, groups=groups, replicates=20)

    assert first == second
    assert first["unit"] == "match_id"
    assert first["seed"] == _MODULE.BOOTSTRAP_SEED


def test_gate_returns_no_release_when_candidate_deteriorates() -> None:
    rows = [
        {"market": "btts", "variant": "constant_train_rate", "status": "ok", "fold_id": "f1"},
        {"market": "btts", "variant": "candidate", "status": "ok", "fold_id": "f1"},
    ]
    pooled = {
        "constant_train_rate": {
            "valid_folds": 1,
            "brier_mean": 0.2,
            "log_loss_mean": 0.4,
            "ece_10_mean": 0.1,
        },
        "candidate": {
            "valid_folds": 1,
            "brier_mean": 0.3,
            "log_loss_mean": 0.5,
            "ece_10_mean": 0.2,
        },
    }

    decision = _MODULE._gate("btts", rows, pooled)["candidate"]

    assert decision["status"] == "no_release"
    assert "insufficient_valid_folds" in decision["reasons"]
    assert "mean_brier_not_better_or_equal" in decision["reasons"]
    assert decision["thresholds_frozen_before_evaluation"] is True
