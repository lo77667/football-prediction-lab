# دورة 36 — نماذج مرشحة قابلة للتدقيق وfuture holdout 2627

## الملخص التنفيذي

بنت هذه الدورة مجموعة صغيرة من candidates الرياضية القابلة للتفسير، واختبرتها على مواسم التطوير `1516`–`2425` فقط باستخدام nested walk-forward. عومل موسم `2526` باعتباره مكشوفًا ومستهلكًا بعد تقييم دورة 35، ولذلك لم يدخل في التدريب أو feature discovery أو candidate selection أو calibration أو tuning. أما موسم `2627` فحُجز كبروتوكول مستقبلي فقط؛ لا توجد له نتيجة في هذه الدورة ولا يجوز تقييمه قبل توفر بياناته.

> هذه الدورة تقييم تطويري خارج العينة داخل مواسم تاريخية، وليست commercial release ولا دليل ربحية ولا توصية مالية.

## 1. سياسة البيانات والزمن

تفرض بوابات Cycle 36 أن تكون مواسم التطوير مساوية تمامًا للقائمة `1516` إلى `2425`. إذا ظهر `2526` في input التطوير، يفشل التشغيل صراحة. يتضمن كل fold partitions زمنية مرتبة: `inner_train` ثم `inner_validation` ثم `outer_test`. لا تُستخدم نتائج `outer_test` لاختيار candidate.

| الفئة | المواسم | الاستخدام |
|---|---|---|
| Development | `1516`–`2425` | التدريب والاختيار والتقييم الخارجي التطويري |
| Exposed | `2526` | ممنوع في Cycle 36 بالكامل؛ لا إعادة استخدام لنتيجة Cycle 35 |
| Future holdout | `2627` | محجوز، غير متاح، وغير مقيم |

تستعمل ميزات التنبؤ أعمدة pre-match وrolling state فقط. لا تدخل أهداف المباراة الحالية أو إحصاءاتها النهائية في feature list؛ وتوجد اختبارات mutation تثبت أن تغيير target الحالي أو نتيجة مباراة لاحقة لا يغير features أو probability للمباراة السابقة.

## 2. candidates المنفذة

| السوق | candidate | التعريف القابل للتدقيق | الحالة |
|---|---|---|---|
| BTTS | `constant_train_rate` | معدل target في training partition فقط | متاح |
| BTTS | `logistic_legacy` | LogisticRegression مع ميزات BTTS legacy السابقة للمباراة | متاح |
| BTTS | `logistic_expanded` | LogisticRegression مع rolling وderived pre-match features | متاح |
| BTTS | `poisson_goals_btts` | معدلان موجبان للهدفين مع shrinkage ثم معادلة BTTS | متاح |
| Cards | `constant_train_rate` | معدل target في training partition فقط | متاح |
| Cards | `cards_logistic_legacy` | LogisticRegression مع ميزات البطاقات legacy | متاح |
| Cards | `cards_logistic_referee_enhanced` | LogisticRegression مع team/referee pre-match state | متاح |
| Cards | `poisson_cards_rate` | معدل Poisson للبطاقات مع team/referee state وshrinkage | متاح |

لـBTTS، يحسب المرشح الرياضي معدلي `lambda_home` و`lambda_away` من scoring/conceding rolling state السابقة، ثم يستخدم:

`P(BTTS) = 1 − exp(−λ_home) − exp(−λ_away) + exp(−(λ_home + λ_away))`.

وللبطاقات، يحسب `lambda_total_cards` من team rates وreferee rate السابقة، ثم يحولها إلى:

`P(total_yellows > 3.5) = 1 − PoissonCDF(3; lambda_total_cards)`.

تُقيد المعدلات إلى مجال موجب ومحدود، ويُطبق shrinkage ثابت معلن بقوة `5.0`. لم تُستخدم مكتبات خارجية جديدة أو بيانات اصطناعية.

## 3. بروتوكول الاختيار

داخل كل outer fold، جرى تقييم كل candidate متاح على `inner_validation` فقط وفق الترتيب المحدد مسبقًا: أقل Brier، ثم أقل Log Loss، ثم أقل ECE، ثم الأبسط حسب ترتيب complexity ثابت. بعد ذلك فقط جرى قياس candidate المختار على `outer_test`. يسجل كل fold `candidate_status` و`selected_variant` و`selection_rule_version` وinner metrics وouter metrics للنسخة المختارة وحدها.

| السوق | fold | outer season | candidate المختار |
|---|---|---:|---|
| BTTS | 01 | 1718 | `logistic_legacy` |
| BTTS | 02 | 1819 | `poisson_goals_btts` |
| BTTS | 03 | 1920 | `constant_train_rate` |
| BTTS | 04 | 2021 | `constant_train_rate` |
| BTTS | 05 | 2122 | `logistic_legacy` |
| BTTS | 06 | 2223 | `logistic_expanded` |
| BTTS | 07 | 2324 | `constant_train_rate` |
| BTTS | 08 | 2425 | `poisson_goals_btts` |
| Cards | 01 | 1718 | `constant_train_rate` |
| Cards | 02 | 1819 | `constant_train_rate` |
| Cards | 03 | 1920 | `constant_train_rate` |
| Cards | 04 | 2021 | `constant_train_rate` |
| Cards | 05 | 2122 | `poisson_cards_rate` |
| Cards | 06 | 2223 | `poisson_cards_rate` |
| Cards | 07 | 2324 | `cards_logistic_legacy` |
| Cards | 08 | 2425 | `cards_logistic_referee_enhanced` |

عدد مرات الاختيار كان BTTS: constant `3`، legacy `2`، Poisson `2`، expanded `1`. وكان للبطاقات: constant `4`، Poisson `2`، logistic legacy `1`، referee-enhanced `1`. المرشح modal للتطوير المستقبلي هو `constant_train_rate` في السوقين مع tie-break complexity ثابت عند الحاجة، لكن هذا لا يحول النتيجة إلى commercial release.

## 4. النتائج المجمعة للـouter folds

الأرقام التالية هي aggregate موزون بالصفوف للنسخة التي اختيرت داخل كل fold، وليست أداء نموذج واحد موحد. متوسطات كل fold التفصيلية وinner metrics والـbootstrap موجودة في artifact JSON وCSV.

| السوق | rows | Accuracy | Brier | Brier Skill | Log Loss | Log-loss Skill | ROC-AUC | AP | ECE(10) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTTS | 3040 | 0.542763 | 0.249659 | -0.000235 | 0.692532 | -0.000266 | 0.514845 | 0.541149 | 0.014413 |
| Cards | 3040 | 0.586184 | 0.243157 | 0.025309 | 0.679693 | 0.017973 | 0.584453 | 0.534528 | 0.033805 |

يظل `calibration_slope` و`calibration_intercept` في artifact تشخيصيين فقط. لم تُستخدم فواصل عدم اليقين لاختيار candidate بعد رؤية outer results.

## 5. paired bootstrap والاستقرار

استُخدم paired bootstrap على مستوى `match_id`، ببذرة `3601` وعدد `1000` تكرارًا وفاصل `95%` لفروق candidate المختار مقابل baseline الخاص بالطية. يشمل artifact فروق Brier وLog Loss وROC-AUC وAverage Precision. المقارنة وصفية ولا تتضمن odds أو ROI أو EV أو stake sizing.

| السوق | نسبة طيات التفوق في Brier | متوسط ΔBrier لكل fold | ΔBrier موزون | أكبر تغير موسمي | stability |
|---|---:|---:|---:|---:|---|
| BTTS | 0.250000 | 0.000059 | 0.000059 | 0.004425 | unstable |
| Cards | 0.500000 | -0.006314 | -0.006314 | 0.016760 | inconclusive |

حدود stability أُعلنت قبل التشغيل: `stable` يتطلب نسبة فوز Brier لا تقل عن `0.75` وأقصى تغير مطلق لا يتجاوز `0.05`. تُوسم الحالة `unstable` عند نسبة لا تتجاوز `0.25` أو تغير أكبر من `0.15`، وإلا فهي `inconclusive`. بناءً على ذلك، BTTS غير مستقر، والبطاقات غير حاسمة.

## 6. بوابة التطوير وfuture holdout

حالة الدورة هي `candidate_selected_in_inner=true` و`evaluated_on_development_outer_test=true`. لم تُمنح `ready_for_future_2627_holdout` لأن شرط الاستقرار لم ينجح لكل الأسواق؛ الحالة الحالية `false`. هذا لا يمنع حفظ عقد 2627، لكنه يمنع تقديم المرشح على أنه جاهز تجاريًا.

الملف [`configs/cycle36_future_holdout_policy.json`](../configs/cycle36_future_holdout_policy.json) يقفل بروتوكول المستقبل: development `1516`–`2425`، exposed `2526`، future holdout `2627`، و`commercial_release=false`. لا توجد نتائج 2627 في هذه الدورة، ولا يوجد أي training أو selection أو calibration مبني على بيانات مستقبلية غير متاحة.

| الحالة | النتيجة |
|---|---|
| `candidate_selected_in_inner` | true |
| `evaluated_on_development_outer_test` | true |
| `ready_for_future_2627_holdout` | false |
| `commercial_release` | false |
| economic benchmark | deferred |
| financial execution | false |

## 7. الاختبارات والـprovenance

بعد commit المصدر `ed320db7ef3f639ca8457097708242cfe4886221`، شُغّلت الاختبارات الكاملة وسجل test summary عدد **163 collected / 163 passed**. كما نجحت Ruff وcompileall و`git diff --check` محليًا. اختبارات Cycle 36 تغطي صلاحية λ والاحتمالات، رفض `2526` في development، ثبات features عند mutation، عدم استخدام outer test للاختيار، deterministic bootstrap، وحماية future holdout `2627`.

المخرجات الأساسية هي:

| الملف | الغرض |
|---|---|
| `src/.../models/poisson_btts.py` | مرشح Poisson لمعدلات الأهداف واحتمال BTTS |
| `src/.../models/poisson_cards.py` | مرشح Poisson لمعدل البطاقات واحتمال over 3.5 |
| `src/.../evaluation/cycle36_model_selection.py` | candidates، selection، bootstrap، stability |
| `scripts_evaluate_cycle36_candidates.py` | المشغل القابل لإعادة التنفيذ |
| `cycle_36_candidate_evaluation.json` | التقرير التفصيلي لكل fold وmarket |
| `cycle_36_fold_metrics.csv` | جدول outer metrics |
| `cycle36_future_holdout_policy.json` | قفل بروتوكول 2627 |

## 8. حالة CI والقرار

نُشر مصدر Cycle 36 بعد الفحوص المحلية. يجب وصف حالة GitHub Actions من خلال سجل التنفيذ الفعلي فقط؛ لا يُعلن نجاح CI دون خطوات تنفيذ قابلة للتحقق. تبقى `commercial_release=false` دائمًا، ولا توجد odds أو نتائج اقتصادية في هذه الدورة.

القرار العلمي الحالي هو الاحتفاظ بالمرشحين كـdevelopment candidates، وعدم إعادة استخدام `2526` كـvalidation صامت، وانتظار توفر موسم `2627` لاختبار holdout مستقبلي مستقل وفق policy lock.

## المراجع الداخلية

[1]: ../configs/cycle36_future_holdout_policy.json "Cycle 36 future holdout policy"
[2]: ../reports/generated/cycle_36_candidate_evaluation.json "Cycle 36 candidate evaluation artifact"
[3]: ../reports/generated/cycle_36_fold_metrics.csv "Cycle 36 fold metrics"
[4]: ../reports/generated/cycle_32_test_summary.json "Generated test summary"
[5]: ../src/football_prediction_lab/evaluation/cycle36_model_selection.py "Cycle 36 selection and uncertainty module"
[6]: ../src/football_prediction_lab/models/poisson_btts.py "Poisson BTTS candidate"
[7]: ../src/football_prediction_lab/models/poisson_cards.py "Poisson cards candidate"
