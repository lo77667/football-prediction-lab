from pathlib import Path

import pandas as pd

from football_prediction_lab.learning.error_log import classify_errors, write_learning_cycle


def test_classify_errors_is_deterministic() -> None:
    evaluation = pd.DataFrame(
        {
            "prediction_id": ["p1", "p2", "p3"],
            "match_id": ["m1", "m2", "m3"],
            "probability_yes": [0.8, 0.2, 0.5],
            "actual_yes": [0, 1, 0],
            "decision": [1, 0, 0],
            "correct_decision": [0, 0, 1],
            "absolute_error": [0.8, 0.8, 0.5],
        }
    )

    result = classify_errors(evaluation)

    assert result["error_type"].tolist() == ["false_positive", "false_negative", "correct"]
    assert result["confidence_band"].tolist() == ["high", "low", "medium"]


def test_write_learning_cycle_appends_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "learning.jsonl"
    write_learning_cycle(
        path,
        source_evaluation="reports/eval.json",
        parent_model_version="v0",
        candidate_model_version="v1",
        accepted=False,
        reason="candidate not tested on an untouched future window",
    )
    assert path.read_text(encoding="utf-8").count("candidate_model_version") == 1
