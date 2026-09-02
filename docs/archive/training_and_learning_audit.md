# تدقيق تدريب نموذج BTTS والتعلم من الأخطاء

## الحكم المختصر

الإصدار الحالي **لا يملك تعلمًا ذاتيًا مستمرًا بالمعنى الكامل**. الموجود فعليًا هو:

1. تدريب دفعي Batch للنموذج على نافذة تاريخية.
2. توقع على نافذة مستقبلية محجوزة.
3. كشف النتائج بعد تثبيت التوقعات.
4. اشتقاق سجل أخطاء من المقارنة.
5. تسجيل قرار إعادة تدريب.
6. بوابة ترفض المرشح ما لم يتحسن على اختبار مستقل كافٍ.

لا توجد حاليًا حلقة آلية تقوم بإنشاء مرشح جديد، وتدريبه، واختباره، ثم اعتماده تلقائيًا. لذلك فالعبارة الأدق هي: **النظام يسجل الأخطاء ويضع شروطًا لإعادة التدريب، لكنه لا يعيد تدريب نفسه تلقائيًا بعد كل خطأ.**

## 1. كود التدريب الفعلي

الملف: `scripts_run_btts_baseline.py`

```python
frame = pd.read_csv(input_path, parse_dates=["kickoff_utc"])
split = temporal_split(frame, train_fraction=0.7, validation_fraction=0.15)
model = BttsLogisticBaseline().fit(split.train)
holdout = pd.concat([split.validation, split.test], ignore_index=True)
holdout = holdout.assign(
    probability_yes=model.predict_probability(holdout).to_numpy(),
)
holdout["decision"] = (holdout["probability_yes"] >= 0.5).astype("int8")
holdout["correct_decision"] = (holdout["decision"] == holdout["btts"]).astype("int8")
holdout.to_csv(output_path, index=False)
```

هذا الكود يدرّب النموذج مرة واحدة على `split.train`، ثم يستخدمه للتنبؤ على نافذة الحجز. لا يوجد في هذا الملف استدعاء لإعادة التدريب بعد ظهور الخطأ.

الملف: `src/football_prediction_lab/models/btts.py`

```python
class BttsLogisticBaseline:
    model_version = "btts-logistic-v0.1"
    feature_version = "pre-match-rolling-v0.1"

    def fit(self, frame: pd.DataFrame) -> BttsLogisticBaseline:
        _validate_training_frame(frame)
        self.pipeline.fit(frame[FEATURE_COLUMNS], frame["btts"])
        self._fitted = True
        return self

    def predict_probability(self, frame: pd.DataFrame) -> pd.Series:
        if not self._fitted:
            raise RuntimeError("model must be fitted before prediction")
        _validate_feature_frame(frame)
        probabilities = self.pipeline.predict_proba(frame[FEATURE_COLUMNS])[:, 1]
        return pd.Series(probabilities, index=frame.index, name="probability_yes")
```

النموذج هو Logistic Regression داخل Pipeline مع StandardScaler. هو نموذج احتمالي ثابت الإصدار، وليس وكيلًا يغير أوزانه تلقائيًا أثناء التشغيل.

## 2. كيف تُكشف النتيجة ويُشتق الخطأ؟

الملف: `scripts_reveal_and_evaluate.py`

```python
for entry in ledger.records():
    if entry["record_type"] != "prediction":
        continue
    record = entry["record"]
    match = matches.loc[record["match_id"]]
    outcome = OutcomeRecord(
        prediction_id=record["prediction_id"],
        match_id=record["match_id"],
        market="btts",
        revealed_at_utc=match["kickoff_utc"].to_pydatetime() + timedelta(days=1),
        actual_yes=bool(match["btts"]),
        result_source=str(match["source"]),
    )
    if not any(
        item["record_type"] == "outcome" and item["record_id"] == outcome.prediction_id
        for item in ledger.records()
    ):
        ledger.append_outcome(outcome)
```

بعد كشف النتيجة، تُبنى صفوف التقييم من الاحتمال والنتيجة والقرار:

```python
joined.append(
    {
        "prediction_id": prediction_id,
        "match_id": prediction["match_id"],
        "probability_yes": probability,
        "actual_yes": actual,
        "decision": decision,
        "correct_decision": int(decision == actual),
        "absolute_error": abs(probability - actual),
    }
)
```

هذا يفصل زمنيًا بين لحظة التوقع ولحظة معرفة النتيجة. سجل الخطأ لا يخبر النموذج أثناء إصدار التوقع؛ بل يُنشأ بعد ذلك.

## 3. كود تصنيف الأخطاء

الملف: `src/football_prediction_lab/learning/error_log.py`

```python
result = evaluation.copy()
result["error_type"] = "correct"
false_positive = (result["decision"] == 1) & (result["actual_yes"] == 0)
false_negative = (result["decision"] == 0) & (result["actual_yes"] == 1)
result.loc[false_positive, "error_type"] = "false_positive"
result.loc[false_negative, "error_type"] = "false_negative"
result["confidence_band"] = pd.cut(
    result["probability_yes"],
    bins=[-0.001, 0.4, 0.6, 1.001],
    labels=["low", "medium", "high"],
    include_lowest=True,
).astype("string")
return result[ERROR_COLUMNS]
```

التصنيف حتمي ولا يعدّل النموذج. في العينة الحالية صُنفت 57 مباراة، منها 16 خطأ false positive و12 خطأ false negative.

## 4. بوابة إعادة التدريب

الملف: `src/football_prediction_lab/learning/retraining.py`

```python
def decide_retraining(
    baseline: BinaryEvaluation,
    candidate: BinaryEvaluation,
    *,
    minimum_test_rows: int = 100,
    tolerance: float = 1e-9,
) -> RetrainingDecision:
    if candidate.rows < minimum_test_rows:
        return RetrainingDecision(
            accepted=False,
            reason=f"untouched test window has fewer than {minimum_test_rows} rows",
        )
    if candidate.brier_score > baseline.brier_score - tolerance:
        return RetrainingDecision(
            accepted=False,
            reason="candidate did not improve Brier Score beyond tolerance",
        )
    if candidate.log_loss > baseline.log_loss - tolerance:
        return RetrainingDecision(
            accepted=False,
            reason="candidate did not improve Log Loss beyond tolerance",
        )
    return RetrainingDecision(
        accepted=True,
        reason="candidate improved Brier Score and Log Loss on the untouched test window",
    )
```

هذه ليست عملية إعادة تدريب؛ إنها **بوابة قرار فقط**. وهي ترفض المرشح إذا كانت نافذة الاختبار أقل من 100 مباراة، أو إذا لم يتحسن كل من Brier Score وLog Loss.

## 5. ماذا حدث فعليًا في دورة التعلم؟

الملف: `scripts_record_learning_cycle.py` لا ينشئ نموذجًا مرشحًا. بل يصنف الأخطاء ويسجل رفضًا تحفظيًا:

```python
write_learning_cycle(
    learning_path,
    source_evaluation="reports/generated/btts_metrics.json",
    parent_model_version="btts-logistic-v0.1",
    candidate_model_version="not-created",
    accepted=False,
    reason="no candidate was accepted: the untouched test window has only 57 rows",
)
```

إذًا، لا يوجد في الإصدار الحالي تعلم ذاتي تلقائي. يوجد **سجل تعلم وقرار رفض موثق**، وهذا أفضل من ادعاء أن النموذج تحسن دون اختبار مستقل، لكنه لا يساوي نظامًا يعيد تدريب نفسه.

## 6. الاستنتاج النهائي

| السؤال | النتيجة الفعلية |
|---|---|
| هل يتوقع النموذج دون معرفة النتيجة؟ | نعم، ضمن الاختبار الزمني المصمم لذلك. |
| هل تُكشف النتيجة بعد تثبيت التوقع؟ | نعم. |
| هل يُسجل الخطأ؟ | نعم، في CSV منظم مع نوع الخطأ ونطاق الثقة. |
| هل يتعلم النموذج تلقائيًا من الخطأ؟ | لا، ليس بعد. |
| هل توجد شروط لاعتماد نموذج جديد؟ | نعم، عبر بوابة إعادة التدريب. |
| هل توجد حلقة تنشئ مرشحًا وتدربه وتختبره وتعتمده؟ | لا، تحتاج إلى تنفيذها في مرحلة لاحقة. |
| هل يمكن الوثوق بأن الأرقام لم تُعدّل بصمت؟ | سجل التوقعات متسلسل، وGit وCI يضيفان قابلية مراجعة، لكن لا توجد حماية مطلقة من صاحب صلاحية الكتابة. |

**الحكم الصريح:** النظام الحالي هو «تدريب + تقييم + توثيق أخطاء + بوابة اعتماد»، وليس «أستاذًا يتعلم ذاتيًا» حتى الآن. التشبيه التعليمي لم يُنفذ كاملًا بعد؛ مرحلة اكتساب الخبرة موجودة كسجل وتحليل، أما إعادة التدريب الدوري المؤتمت فما زالت مفقودة.
