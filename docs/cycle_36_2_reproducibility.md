# دورة 36.2 — Full Reproducible Source Bundle

## الحكم النهائي

أُغلقت المشكلة التي منعت اعتماد دورة 36.1 من جهة **قابلية التثبيت وإعادة الإنتاج**. أُنشئ الأرشيف الرسمي من Git باستخدام `git archive` من HEAD، وليس من قائمة ملفات منتقاة. يحتوي الأرشيف على كامل الملفات المتتبعة في المستودع، بما فيها `src/` و`tests/` وملفات التشغيل و`scripts/` و`pyproject.toml` و`requirements.lock` و`configs/` و`docs/` وartifacts دورة 36.

> نوع التسليم: **Full reproducible source bundle**. ليس Patch-only bundle، ولا يعتمد على checkout خارجي أو `PYTHONPATH` خارجي.

| البند | النتيجة |
|---|---|
| HEAD المصدر للأرشيف | يحدده `SOURCE_COMMIT.txt` المستبدل تلقائيًا داخل Git archive |
| commit الإصلاحات المصدرية | `f5000b2` و`dc562aa` و`4e5ba45` و`f024d9d` حسب تسلسل packaging |
| عدد الملفات المتتبعة في Git | 268 |
| عدد الملفات المفكوكة في الأرشيف | 268 |
| ملف الأرشيف | `football-prediction-lab-cycle36.2-full-source.zip` |
| بيانات محلية أو secrets داخل الأرشيف | غير مضمّنة |
| `commercial_release` | `false` |

## 1. إصلاح packaging والتثبيت

يحتوي `pyproject.toml` على تعريف setuptools واكتشاف الحزم من `src/`، مع Python `>=3.11`، وdependencies للمشروع، وdev extras لـpytest وRuff. ثُبّت build backend إلى `setuptools==68.1.2`، وأضيف `requirements.lock` يتضمن الإصدارات المثبتة للحزم المباشرة والانتقالية في بيئة التحقق.

طريقة التثبيت الموثقة من جذر الأرشيف هي:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install -e '.[dev]'
```

نجح هذا التسلسل داخل venv جديدة تمامًا، دون الاعتماد على الحزم المثبتة في البيئة الأم. كما نجح الأمر `pip install -e '.[dev]'` بعد تثبيت lock.

## 2. تحقق imports والمسارات

نجحت probes التالية داخل الأرشيف المفكوك والـvenv النظيفة:

```text
package_path=/tmp/cycle362_final_bundle2/football-prediction-lab/src/football_prediction_lab/__init__.py
selection_path=/tmp/cycle362_final_bundle2/football-prediction-lab/src/football_prediction_lab/evaluation/cycle36_model_selection.py
```

يتبع كل مسار جذر الأرشيف الحالي `/tmp/cycle362_final_bundle2/football-prediction-lab`. لا يشير أي import إلى checkout قديم أو site-package خارجي. يتحقق `scripts/verify_cycle36_reproducibility.py` من هذا الشرط ويفشل إذا خرج مسار الحزمة عن جذر المشروع.

أُضيف `SOURCE_COMMIT.txt` مع Git `export-subst`، لذلك يحتوي الأرشيف على commit الحقيقي `3d10d0b8a9b399698dbb60ec223ee3cd38392694` رغم عدم وجود مجلد `.git` داخله. ويدعم `scripts_test_summary.py` fallback إلى هذا marker عند التشغيل من archive.

## 3. التشغيل في venv نظيفة

شُغّل التحقق على نسخة مفكوكة من الأرشيف نفسه، لا على checkout العمل. النتائج:

| الفحص | النتيجة الفعلية |
|---|---|
| Python | 3.12.3 |
| pytest | 174 passed |
| Ruff | `All checks passed!` |
| compileall `src scripts` | ناجح |
| compileall `src scripts_*.py` | ناجح في checkout المصدر |
| `git diff --check` | ناجح في checkout المصدر |
| `scripts/verify_cycle36_reproducibility.py` | `cycle36_reproducibility=passed` |
| test summary داخل الأرشيف | 174 collected / 174 passed |
| pytest داخل verifier | 174 passed |
| Ruff داخل verifier | ناجح |

سجل test summary داخل الأرشيف الإصدارات التالية: Python `3.12.3`، pytest `8.4.2`، وRuff `0.16.4`، مع commit marker الصحيح للأرشيف.

## 4. smoke fixtures

أضيفت fixtures صغيرة في `tests/fixtures/cycle36_smoke/` لاختبار candidates Poisson واحتمالاتها دون الحاجة إلى البيانات التاريخية المحلية. لا تُستخدم هذه fixtures لإعادة إنتاج metrics دورة 36. التقييم التاريخي الكامل ما زال يتطلب ملفات `data/processed/` المحلية المصرح بها وmanifest/hash خارج Git، ولذلك لم تُضمّن بيانات أو أسرار في الأرشيف.

## 5. مقارنة artifacts بعد الإصلاح

قورنت artifacts دورة 36 قبل وبعد تغييرات packaging بعد التطبيع الذي يحذف timestamp المتغير فقط. كانت النتائج:

| المقارنة | النتيجة |
|---|---|
| evaluation JSON normalized comparison | `cmp exit=0` |
| future holdout policy comparison | `cmp exit=0` |
| selected candidates لكل fold | مطابق |
| inner metrics | مطابق |
| outer metrics | مطابق |
| pooled metrics | مطابق |
| stability summary | مطابق |
| `2526` guards | مطابقة |
| `2627` reserved status | مطابق |
| `commercial_release` | `false` في النسختين |

تحققت manifests داخل الأرشيف من SHA-256، وكانت hashes المحسوبة مطابقة للقيم المسجلة للملفات التالية:

| الملف | حالة hash |
|---|---|
| `reports/generated/cycle_36_candidate_evaluation.json` | verified |
| `reports/generated/cycle_36_fold_metrics.csv` | verified |
| `configs/cycle36_future_holdout_policy.json` | verified |

لم تُعدّل نماذج Cycle 36 أو metrics أو policy. التغيرات محصورة في packaging، lock، verifier، smoke fixtures، وtest summary tooling.

## 6. الحواجز الزمنية والقرار التجاري

ظل موسم `2526` خارج development وselection وtuning وcalibration، وظل `2627` محجوزًا بحالة `reserved_not_available_and_not_evaluated`. لا توجد أي نتائج لـ2627 في هذه الدورة. كما لم تُستخدم odds أو ROI أو EV أو stake sizing أو أي تنفيذ مالي.

| الحاجز | الحالة |
|---|---|
| `2526_in_development` | false |
| `2526_in_selection` | false |
| `2526_in_tuning` | false |
| `2526_in_calibration` | false |
| `2627_evaluated` | false |
| `selection_used_2526` | false |
| `commercial_release` | false |

## 7. provenance وحالة CI

الأرشيف مبني من Git، وcommit marker داخله يثبت مصدره. أما حالة GitHub Actions فتُسجّل من run الفعلي فقط ولا تُستنتج من الاختبارات المحلية. أحدث run موثق بعد نشر التقرير هو `32915470279` على commit `ea5f28faaa48496a3ff1fc431ac4242814c8d90e`، وقد فشل مع jobَي `Test and lint (3.11)` و`Test and lint (3.12)` وكلاهما `steps: []`. لذلك لا يُستخدم CI لإثبات نجاح أو فشل الكود؛ تبقى نتائج venv النظيفة هي دليل التحقق المحلي القابل لإعادة الإنتاج.

## 8. الخلاصة

استوفى التسليم معايير دورة 36.2: الأرشيف كامل من Git، قابل للتثبيت في venv نظيفة، imports تشير إلى المشروع الحالي، pytest وRuff وcompileall وverifier ناجحة، manifests قابلة للتحقق، وartifacts Cycle 36 مطابقة بعد التطبيع. بناءً على ذلك، لا توجد علة packaging تمنع إغلاق دورة 36.2. يبقى القرار المنهجي كما هو: `commercial_release=false`، و`2627` ينتظر holdout مستقلًا عند توفره.

## المراجع الداخلية

[1]: ../pyproject.toml "Project packaging and tool configuration"
[2]: ../requirements.lock "Pinned dependency lock"
[3]: ../scripts/verify_cycle36_reproducibility.py "Reproducibility verifier"
[4]: ../scripts_test_summary.py "Generated test summary"
[5]: ../reports/generated/cycle_36_candidate_evaluation.json "Cycle 36 evaluation artifact"
[6]: ../configs/cycle36_future_holdout_policy.json "Future holdout policy for 2627"
[7]: cycle_36_1_operability.md "Cycle 36.1 operability report"
