# دورة 33: مقارنة النماذج عبر Walk-Forward زمني

**المستودع:** `football-prediction-lab`  
**الدورة:** 33  
**الحالة:** تقييم بحثي وصفي فقط؛ لا توجد odds حقيقية ولا تنفيذ مالي ولا أرقام edge/EV.  
**المرجع البرمجي:** `scripts_evaluate_cycle33.py` و`src/football_prediction_lab/evaluation/walk_forward_protocol.py`.

## الملخص التنفيذي

اختبرت الدورة قدرة تنبؤية واستقرارًا عبر **ثماني طيات مستقبلية** لكل من BTTS وcards. استُخدم expanding window: مواسم التدريب الأقدم، ثم موسم معايرة واحد، ثم الموسم التالي للاختبار. لم يُستخدم shuffle أو random K-fold، ولم يدخل موسم `2526` في الطيات أو التدريب أو اختيار variant أو المعايرة أو الـbootstrap.

النتيجة ليست حكمًا تجاريًا. في BTTS، اجتاز `platt_expanded` بوابة التقييم الداخلية المحددة مسبقًا، بينما رُفض `expanded` و`legacy` بسبب تدهور متوسط Brier/Log Loss، وتدهور ECE في `expanded`. في cards، اجتاز `legacy` و`platt_referee_enhanced` البوابة الداخلية، بينما رُفض `referee_enhanced` بسبب تدهور متوسط Brier/Log Loss. كلمة `release` هنا تعني اجتياز بوابة مقارنة بحثية محددة مسبقًا، ولا تعني صلاحية مراهنة أو اعتمادًا اقتصاديًا.

> **القرار التجاري:** economic benchmark مؤجل، ولا توجد أرقام edge/EV حقيقية أو توصيات أو stake sizing. نتائج دورة 33 لا تثبت الربحية ولا صلاحية استخدام مالي.

## بروتوكول الطيات

| العنصر | الإعداد |
|---|---|
| قاعدة التقسيم | expanding train، موسم معايرة سابق مباشرة، موسم اختبار تالٍ |
| عدد الطيات | 8 لكل سوق |
| الطيات المحمية | `2526` مستبعد بالكامل |
| المعايرة | Platt داخل calibration season الخاصة بالطية فقط |
| وحدة bootstrap | `match_id`، وليس selection أو صفًا مستقلًا |
| bootstrap | 400 تكرارًا، seed ثابت `3301`، فاصل 95% |
| shuffle | غير مستخدم |
| thresholds/gates | ثابتة قبل التقييم: `min_valid_folds=3` و`ECE tolerance=0.02` |

أُرفقت metadata لكل طية تتضمن `train_seasons` و`calibration_seasons` و`test_seasons` و`train_cutoff` و`prediction_start` و`prediction_end` وعدادات الصفوف ونسخ feature/model. يرفض البروتوكول الطيات غير المرتبة زمنيًا، أو المتداخلة، أو الناقصة metadata، أو التي تحتوي `2526`.

## variants المعلنة

| السوق | variants |
|---|---|
| BTTS | `constant_train_rate`, `legacy`, `expanded`, `platt_expanded` |
| cards | `constant_train_rate`, `legacy`, `referee_enhanced`, `platt_referee_enhanced` |

لم تُجرَ شبكة tuning واسعة، ولم تُستخدم نتائج موسم الاختبار لاختيار المعاملات. Platt دُرّب داخل calibration season لكل طية، ولم يرَ test.

## النتائج المجمعة عبر الطيات

الأرقام التالية هي متوسطات per-fold، مع 8 طيات و3040 صف اختبار لكل variant.

### BTTS

| variant | Brier mean | Log Loss mean | ROC-AUC mean | AP mean | ECE mean | gate |
|---|---:|---:|---:|---:|---:|---|
| constant_train_rate | 0.249859 | 0.692866 | 0.500000 | 0.525987 | 0.031322 | baseline |
| legacy | 0.250448 | 0.694056 | 0.509986 | 0.541011 | 0.045910 | no_release |
| expanded | 0.256722 | 0.707768 | 0.512040 | 0.543825 | 0.078851 | no_release |
| platt_expanded | 0.249480 | 0.692139 | 0.509407 | 0.540727 | 0.030761 | release داخلي |

أسباب رفض `legacy`: `mean_brier_not_better_or_equal` و`mean_log_loss_not_better_or_equal`. أسباب رفض `expanded`: السببان نفسيهما إضافة إلى `ece_deterioration`.

### cards

| variant | Brier mean | Log Loss mean | ROC-AUC mean | AP mean | ECE mean | gate |
|---|---:|---:|---:|---:|---:|---|
| constant_train_rate | 0.250384 | 0.693999 | 0.500000 | 0.457237 | 0.079020 | baseline |
| legacy | 0.249790 | 0.693000 | 0.509042 | 0.468864 | 0.087874 | release داخلي |
| referee_enhanced | 0.250649 | 0.695629 | 0.522277 | 0.477918 | 0.085868 | no_release |
| platt_referee_enhanced | 0.247948 | 0.689548 | 0.506560 | 0.468551 | 0.072139 | release داخلي |

سبب رفض `referee_enhanced`: `mean_brier_not_better_or_equal` و`mean_log_loss_not_better_or_equal`.

## عدم اليقين والاستقرار

استُخدم bootstrap مقترن على مستوى `match_id`، seed `3301`، و400 تكرار. فواصل Brier وLog Loss التي عبرت الصفر سُجلت `inconclusive`، ولم تُستخدم لتعديل المعاملات أو اختيار variant بعد رؤية test.

في BTTS، كان bootstrap لـ`platt_expanded` مقابل constant غير حاسم لـBrier وLog Loss، رغم أن AP وROC-AUC أظهرا اتجاهًا موجبًا. وفي cards، كان bootstrap لـ`platt_referee_enhanced` غير حاسم لـBrier وLog Loss، مع اتجاه موجب في ROC-AUC وAP. لذلك لا تُختزل النتيجة في مقياس discrimination واحد، ولا يُعتبر أي فرق غير حاسم دليل تفوق.

تُنتج كل طية أيضًا ranking diagnostic؛ ويُعاد `null` عندما لا تكفي العينة. في هذه الدورة كانت أحجام طيات الاختبار كافية لحساب top-decile precision وصفيًا، دون استخدامه كحارس إصدار منفرد.

## حارس الإصدار

قواعد الحارس ثابتة قبل التقييم:

1. وجود ثلاث طيات صالحة على الأقل.
2. عدم وجود فشل طية غير مفسر.
3. عدم تدهور متوسط Brier أو Log Loss مقابل constant baseline.
4. عدم تجاوز ECE baseline بأكثر من `0.02` عند توفر المقارنة.

النتيجة `no_release` هي نتيجة صحيحة عند فشل الشروط، ولا تُخفف الحدود بعد رؤية النتائج. وفي الوقت نفسه، `release داخلي` لا يفتح readiness التجاري ولا يغير قرار economic benchmark المؤجل.

## عزل 2526 ومنع التسرب

لم يدخل `2526` في الطيات، أو التدريب، أو calibration، أو اختيار variant، أو threshold، أو gate، أو bootstrap tuning. كما يعتمد البروتوكول على feature contracts الموجودة التي ترفض target وpost-match columns، ويستخدم features مبنية من التاريخ السابق فقط.

## الاختبارات والمخرجات

أُضيفت اختبارات تثبت الترتيب الزمني وعدم التداخل وعزل `2526` ونقص metadata، وحتمية bootstrap ووحدة `match_id` وظهور `no_release` عند فشل الشروط. نتيجة test summary الحالية هي **145 collected / 145 passed**، مع timestamp وcommit داخل `reports/generated/cycle_32_test_summary.json`.

| المخرج | الغرض |
|---|---|
| `src/football_prediction_lab/evaluation/walk_forward_protocol.py` | عقد الطيات الزمنية وحواجز الترتيب والعزل |
| `scripts_evaluate_cycle33.py` | تشغيل دورة 33 وإنتاج JSON/CSV |
| `tests/test_walk_forward_protocol.py` | اختبارات الطيات وحماية 2526 |
| `tests/test_cycle33_evaluation.py` | اختبارات bootstrap وno_release |
| `reports/generated/cycle_33_walk_forward.json` | التقرير التفصيلي per-fold وpooled والـgate |
| `reports/generated/cycle_33_fold_metrics.csv` | جدول المقاييس لكل fold/market/variant |
| `reports/generated/manifests/cycle_33_walk_forward.manifest.json` | manifest للمخرج الرئيسي |
| `reports/generated/manifests/cycle_33_fold_metrics.manifest.json` | manifest لجدول المقاييس |

## الفحوص

شُغّلت الفحوص التالية محليًا: `pytest -q`، و`ruff check .`، و`python -m compileall -q src scripts_*.py`، و`git diff --check`، و`python scripts_test_summary.py`. لا يُعد فشل GitHub Actions نجاحًا أو فشلًا برمجيًا إلا بعد تنفيذ خطوات فعلية قابلة للتحقق؛ سيُسجل CI كما هو دون ادعاء نجاح غير قابل للتحقق.
