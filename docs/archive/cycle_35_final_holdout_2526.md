# دورة 35 — التقييم النهائي المحجوز لموسم 2526

## الملخص التنفيذي

نفّذت هذه الدورة بروتوكولًا زمنيًا مغلقًا: حُسبت سياسة deployment من artifact دورة 34 فقط، ثم حُفظ **policy lock** قبل تنفيذ التقييم على labels موسم `2526`. أُنشئ أولًا artifact predictions منفصل لا يحتوي targets، ثم أُجري join مستقل مع labels للتقييم. لم تُستخدم odds أو ROI أو EV أو stake sizing أو أي تنفيذ مالي، ولذلك يبقى النظام **Research-Only** و`commercial_release=false`.

> النتيجة صالحة كتقييم وصفي لموسم holdout محجوز لسياسة ثابتة، وليست دليل ربحية أو توصية مراهنة.

## 1. قفل السياسة قبل holdout

يُثبت الملف [`configs/cycle35_policy_lock.json`](../configs/cycle35_policy_lock.json) الإصدار `cycle35-deployment-policy-v1`، ومصدر الاختيار هو دورة 34 (`d0041b9`). يحتوي القفل على hash للـartifacts السابقة، ومواسم التدريب حتى `2425`، و`protected_holdout=["2526"]`، و`commercial_release=false`.

تم تطبيق القاعدة المحددة مسبقًا في الكود: **اختيار variant الأكثر تكرارًا في دورة 34 لكل سوق، ثم tie-break ثابت حسب البساطة**. أُعيد حساب القرار من counts الموجودة في تقرير دورة 34 وقورِن بالسياسة المقفلة؛ لم تُقرأ labels موسم 2526 لمسار الاختيار.

| السوق | counts من دورة 34 | التعادل | policy المختارة | calibration |
|---|---:|---|---|---|
| BTTS | constant=3، legacy=3، expanded=1، platt_expanded=1 | constant مقابل legacy | `constant_train_rate` | none |
| Cards | constant=5، platt_referee_enhanced=2، referee_enhanced=1 | لا يوجد | `constant_train_rate` | none |

في حالة BTTS حُسم التعادل لصالح `constant_train_rate` لأن ترتيب البساطة المقفّل يضعه قبل `legacy`. كما يرفض guard صريح تمرير `2526` إلى selection أو tuning.

## 2. artifact predictions قبل labels

أُنشئ [`cycle_35_2526_predictions_prelabel.json`](../reports/generated/cycle_35_2526_predictions_prelabel.json) في مرحلة `prelabel`. يحتوي على **760 prediction**، بواقع 380 لكل سوق، ولا يحتوي على target columns. كل سجل يحمل `match_id` و`kickoff_utc` و`issued_at` و`training_cutoff` و`model_version` و`feature_version` و`policy_version` و`probability` وprovenance hashes.

تحققت الاختبارات من عدم وجود `btts` أو `total_yellows_over_3_5` أو `home_goals` أو `away_goals` أو `total_yellows` داخل سجلات predictions، ومن عدم تكرار `match_id` داخل السوق. كما أن `issued_at` يسبق kickoff، و`training_cutoff` يسبق kickoff وجميع مواسم التدريب لا تتضمن `2526`.

## 3. نتيجة التقييم على 2526

أُجري التقييم مرة واحدة بعد وجود policy lock وartifact prelabel. يستخدم baseline معدلًا تاريخيًا مجمدًا محسوبًا من البيانات السابقة لـ`2526`، وليس من labels holdout. العتبة المعلنة هي `0.5`، والمقاييس تشمل Accuracy وBrier وLog Loss وROC-AUC وAverage Precision وECE، مع slope/intercept كتشخيص معايرة فقط.

| السوق | rows / coverage | policy probability | historical baseline | Accuracy | Brier | Log Loss | ROC-AUC | AP | ECE(10) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTTS | 380 / 1.000 | 0.523421 | 0.523421 | 0.560526 | 0.247713 | 0.688571 | 0.500000 | 0.560526 | 0.037105 |
| Cards | 380 / 1.000 | 0.457105 | 0.457105 | 0.447368 | 0.256355 | 0.705893 | 0.500000 | 0.552632 | 0.095526 |

بما أن policy المختارة في السوقين هي `constant_train_rate`، فإن probability تطابق baseline التاريخي المجمد. لذلك فإن Brier وLog Loss skill يساويان صفرًا في هذا الاختبار، وROC-AUC يساوي `0.5` لأن التنبؤ ثابت. هذه نتيجة تشخيصية مهمة وليست تحسنًا تجاريًا.

## 4. paired bootstrap

استُخدم paired bootstrap على مستوى `match_id`، ببذرة `3501` وعدد `1000` تكرارًا وفاصل `95%`. المقارنة descriptive فقط بين policy وbaseline، ولا تتضمن أي مقياس اقتصادي.

| السوق | metric | delta mean | 95% lower | 95% upper | status |
|---|---|---:|---:|---:|---|
| BTTS | Brier | 0.000000 | 0.000000 | 0.000000 | inconclusive |
| BTTS | Log Loss | 0.000000 | 0.000000 | 0.000000 | inconclusive |
| Cards | Brier | 0.000000 | 0.000000 | 0.000000 | inconclusive |
| Cards | Log Loss | 0.000000 | 0.000000 | 0.000000 | inconclusive |

الفاصل يمر بالصفر، كما أن candidate وbaseline متطابقان بنيويًا؛ لذلك وُسمت النتائج `inconclusive` ولم تُستخدم لإثبات تفوق أو لاتخاذ قرار مالي.

## 5. حواجز الصلاحية والقرار

| الحاجز | الحالة |
|---|---|
| policy lock موجود وصالح قبل التقييم | ناجح |
| policy lock لم يتغير بعد إنشاء predictions | ناجح |
| labels 2526 لم تدخل selection أو tuning أو calibration | ناجح |
| prediction artifact بلا targets | ناجح |
| timestamps قبل kickoff وtraining cutoff قبل kickoff | ناجح |
| uniqueness لكل مباراة داخل كل سوق | ناجح |
| لا post-match fields في مسار features | ناجح |
| إعادة التشغيل بنفس القفل تعطي نفس الاحتمالات | ناجح |
| `evaluation_runs` | 1 |
| `evaluation_valid` | true |
| `evaluation_invalidated` | false |
| `commercial_release` | false |
| economic benchmark | deferred |

اختبار تعديل labels في [`tests/test_holdout_policy.py`](../tests/test_holdout_policy.py) ينشئ labels بديلة لموسم `2526`، ثم يثبت أن policy lock والاحتمالات في artifact prelabel لا تتغير. لا يعتمد هذا الاختبار على إعادة اختيار أو إعادة ضبط بعد ظهور النتائج.

## 6. الاختبارات وprovenance

بعد commit المصدر `e56c597a5bd0fc061e627da285fbc9bcc84a7bb6`، أُعيد توليد artifacts ثم شُغّل [`scripts_test_summary.py`](../scripts_test_summary.py). النتيجة الفعلية هي **154 اختبارًا مجموعًا و154 ناجحًا**. يحتفظ artifact [`cycle_32_test_summary.json`](../reports/generated/cycle_32_test_summary.json) بالعدد والطابع الزمني وcommit المصدر.

| artifact | SHA-256 |
|---|---|
| `configs/cycle35_policy_lock.json` | `8fd0d5d3f073cd80a7b99b7c51f7b29ae66ef78ceda5a8743d785215f94ffe23` |
| `cycle_35_policy_selection.json` | `694180308e5675bcfbe326314fd0d111a4c82d8b7297a24fa59eaf086a6f5883` |
| `cycle_35_2526_predictions_prelabel.json` | `e8867fb36872928a786ed6d5411abf1160926c9a70ca1c8fcfe45fe2719e3fa7` |
| `cycle_35_2526_evaluation.json` | `ece524b651609af685987aa07acef2824787d6533bd05a3245aea1c574d67378` |
| `cycle_35_2526_metrics.csv` | `88b3081d7b882b729640bd4375ad714ce9ca1b30c40a188be414d7039fc3f822` |
| `cycle_32_test_summary.json` | `bf1082df36e99a2f73dd77a21c172424690d77bcce4dcd479c88ca70c3f12f3f` |

توجد manifests مقابلة في [`reports/generated/manifests/`](../reports/generated/manifests/)، وتشمل hashes للمدخلات والمخرجات. لم تُعدّل تقارير أو artifacts دورتي 33 و34.

## 7. حالة CI

رُفع commit المصدر إلى `origin/main`. حالة GitHub Actions السابقة على دورة 34 بقيت فاشلة على مستوى runner/تهيئة؛ أحدث job معروف كان `test-and-lint` بعدد `steps: 0`. لا توجد خطوات تنفيذ فعلية يمكن الاستناد إليها لإعلان نجاح CI، ولذلك لا يُعلن هذا التقرير نجاح GitHub Actions. كما أن فشل runner لا يُنسب هنا إلى كود دورة 35 دون سجل تنفيذ جديد قابل للتحقق.

## المراجع الداخلية

[1]: ../configs/cycle35_policy_lock.json "Cycle 35 policy lock"
[2]: ../reports/generated/cycle_35_policy_selection.json "Cycle 35 policy selection artifact"
[3]: ../reports/generated/cycle_35_2526_predictions_prelabel.json "Cycle 35 prelabel predictions"
[4]: ../reports/generated/cycle_35_2526_evaluation.json "Cycle 35 2526 evaluation"
[5]: ../reports/generated/cycle_32_test_summary.json "Generated test summary"
[6]: cycle_34_nested_walk_forward.md "Cycle 34 nested walk-forward report"
