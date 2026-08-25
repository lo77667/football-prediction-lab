"""Grounded explanation layer for verified evaluation records.

This module intentionally does not call an external model. It provides a strict,
read-only explanation boundary that can later wrap an LLM without granting it
permission to change data, predictions, or model artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedEvaluation:
    market: str
    model_version: str
    rows: int
    accuracy: float
    brier_score: float
    log_loss: float
    actual_rate: float
    mean_probability: float

    def __post_init__(self) -> None:
        if self.market not in {"btts", "total_yellows_over_3_5"}:
            raise ValueError("unsupported market")
        if self.rows < 1:
            raise ValueError("rows must be positive")
        for name in (
            "accuracy",
            "brier_score",
            "log_loss",
            "actual_rate",
            "mean_probability",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1 and name != "log_loss":
                raise ValueError(f"{name} must be within [0, 1]")
        if self.log_loss < 0:
            raise ValueError("log_loss cannot be negative")


def render_verified_summary(evaluation: VerifiedEvaluation) -> str:
    """Render only facts present in a verified evaluation payload."""

    market_name = {
        "btts": "كلا الفريقين يسجلان",
        "total_yellows_over_3_5": "أكثر من 3.5 بطاقة صفراء",
    }[evaluation.market]
    return (
        f"السوق: {market_name}. "
        f"إصدار النموذج: {evaluation.model_version}. "
        f"عدد الحالات المقيمة: {evaluation.rows}. "
        f"الدقة عند العتبة المحددة: {evaluation.accuracy:.4f}. "
        f"Brier Score: {evaluation.brier_score:.4f}. "
        f"Log Loss: {evaluation.log_loss:.4f}. "
        f"معدل الحدث الفعلي: {evaluation.actual_rate:.4f}. "
        f"متوسط الاحتمال المتوقع: {evaluation.mean_probability:.4f}. "
        "هذا ملخص وصفي ولا يثبت ربحية أو ضمان النتيجة."
    )
