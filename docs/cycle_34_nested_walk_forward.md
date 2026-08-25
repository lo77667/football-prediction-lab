# دورة 34: Nested Walk-Forward ومنع Selection-on-Outer-Test

**المستودع:** `football-prediction-lab`  
**الدورة:** 34  
**الحالة:** تقييم بحثي خارج العينة؛ لا توجد odds حقيقية أو edge/EV أو ROI أو stake sizing أو تنفيذ مالي.  
**الهدف:** إصلاح مشكلة دورة 33 التي كانت تستخدم نتائج outer test في decision gate لتسمية variants بـ`release`.

## الملخص التنفيذي

تستخدم دورة 34 بروتوكولًا nested زمنيًا. لكل outer fold توجد ثلاث مناطق مرتبة: `inner_train`، ثم `inner_validation` لاختيار variant، ثم `outer_test` للتقييم النهائي للـvariant المختار. دالة `select_variant_on_inner_validation` لا تستقبل outer test أصلًا، وتعيد `outer_test_used=false` داخل سجل الاختيار.

النتيجة المهمة هي أن `selected_variant` يختلف من طية إلى أخرى، ولا يُفترض أن variant واحدًا هو الأفضل دائمًا. هذا يقدّر أداء variant تم اختياره داخل كل دورة، بدل اختيار نموذج بعد رؤية نتائج الاختبار الخارجي. ومع ذلك، لا تمنح دورة 34 أي `commercial_release`؛ الحقل ثابت على `false` بسبب غياب odds الحقيقية وعدم كفاية الدليل المستقبلي.

> **قرار الدورة:** `commercial_release = false` دائمًا. نتائج outer test وصفية خارج العينة وليست توصية أو إثبات ربحية.

## تقسيم outer/inner

لكل سوق بُنيت **8 طيات** على المواسم التاريخية قبل `2526`:

| الجزء | التعريف |
|---|---|
| `outer_train` | كل المواسم المتاحة قبل موسم outer test، ويضم inner train وinner validation |
| `inner_train` | المواسم الأقدم داخل outer train |
| `inner_validation` | الموسم السابق مباشرة لموسم outer test؛ يستخدم لاختيار variant فقط |
| `outer_test` | الموسم التالي؛ لا تدخل labels الخاصة به في الاختيار |
| المعايرة | Platt، عند اختيار variant المعاير، تستخدم بيانات داخل outer train فقط |
| الحماية | `2526` ممنوع في كل المراحل |
| الاختيار | Brier ثم Log Loss ثم ECE ثم بساطة variant، بقواعد ثابتة قبل التشغيل |

لا يوجد shuffle أو random K-fold. كل طية تحتوي training cutoff وprediction windows وعدادات الصفوف ونسخ feature/model. لا توجد overlaps بين inner train وinner validation وouter test.

## selected_variant لكل طية

| السوق | fold | outer test | selected_variant | outer test داخل الاختيار؟ | commercial_release |
|---|---|---|---|---|---|
| BTTS | fold_01 | 1718 | legacy | لا | false |
| BTTS | fold_02 | 1819 | legacy | لا | false |
| BTTS | fold_03 | 1920 | constant_train_rate | لا | false |
| BTTS | fold_04 | 2021 | constant_train_rate | لا | false |
| BTTS | fold_05 | 2122 | legacy | لا | false |
| BTTS | fold_06 | 2223 | expanded | لا | false |
| BTTS | fold_07 | 2324 | constant_train_rate | لا | false |
| BTTS | fold_08 | 2425 | platt_expanded | لا | false |
| cards | fold_01 | 1718 | constant_train_rate | لا | false |
| cards | fold_02 | 1819 | constant_train_rate | لا | false |
| cards | fold_03 | 1920 | platt_referee_enhanced | لا | false |
| cards | fold_04 | 2021 | constant_train_rate | لا | false |
| cards | fold_05 | 2122 | constant_train_rate | لا | false |
| cards | fold_06 | 2223 | constant_train_rate | لا | false |
| cards | fold_07 | 2324 | platt_referee_enhanced | لا | false |
| cards | fold_08 | 2425 | referee_enhanced | لا | false |

يُحفظ لكل fold أيضًا `inner_metrics` لكل candidate صالح، و`candidate_status` عند تعذر تقييم candidate، و`selection_rule_version`. لا تُستخدم outer-test metrics لرفض أو قبول variant داخل هذا التقرير.

## المخرجات الخارجية المجمعة

هذه المتوسطات هي **outer-test metrics للـselected variant فقط**، وليست مقارنة post-hoc لجميع variants على outer test.

| السوق | outer folds | rows | selected counts | Brier mean | Log Loss mean | ROC-AUC mean | AP mean | ECE mean |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| BTTS | 8 | 3040 | constant=3، legacy=3، expanded=1، platt=1 | 0.249942 | 0.693107 | 0.509230 | 0.532345 | 0.033980 |
| cards | 8 | 3040 | constant=5، referee=1، platt=2 | 0.244923 | 0.682987 | 0.506373 | 0.465539 | 0.064429 |

الـouter-test baseline محفوظ لكل fold باستخدام constant outer-train rate. ويُحفظ selected variant فقط في `outer_test_metrics`، مع `baseline_outer_test_metrics` للمقارنة العادلة.

## عدم اليقين

يُحسب paired bootstrap داخل outer test فقط، على مستوى `match_id`، باستخدام seed `3401` و400 تكرارًا وفاصل 95%. هذه الفواصل وصفية ولا تدخل في اختيار variant أو gate لاحق. تشمل المخرجات delta Brier وdelta Log Loss، وتضيف delta ROC-AUC وAverage Precision عندما توجد الفئتان.

أي فاصل يعبر الصفر يُوسم `inconclusive`. لا تُستخدم هذه الفواصل لتعديل المعاملات بعد التنفيذ.

## بوابات الحالة

تفصل دورة 34 بين ثلاث حالات:

| الحالة | المعنى |
|---|---|
| `selected_for_outer_evaluation` | variant اختير من inner validation فقط قبل قراءة outer labels |
| `evaluated_out_of_sample` | تم قياس variant المختار على outer test |
| `commercial_release` | **false دائمًا في دورة 34** |

هذه الدورة لا تعيد تقييم قرار دورة 33 ولا تعدل artifact دورة 33. كما لا تستخدم odds أو بيانات اقتصادية.

## اختبارات منع التسرب

أضيفت اختبارات تثبت أن تغيير labels المفترضة للـouter test لا يغير selected variant، وأن outer test غير موجود في واجهة دالة الاختيار. كما تختبر الاختبارات عزل `2526`، وعدم overlap، والترتيب الزمني، وحتمية bootstrap، وبقاء `commercial_release=false`.

## الفحوص والـprovenance

أنتجت الدورة:

| الملف | الغرض |
|---|---|
| `src/football_prediction_lab/evaluation/nested_walk_forward.py` | عقد nested folds ودالة الاختيار الداخلي وbootstrap الخارجي |
| `scripts_evaluate_cycle34_nested.py` | evaluator دورة 34 |
| `tests/test_nested_walk_forward.py` | اختبارات منع selection-on-outer-test وحماية 2526 |
| `reports/generated/cycle_34_nested_walk_forward.json` | التقرير التفصيلي لكل fold وinner/outer metrics |
| `reports/generated/cycle_34_nested_fold_metrics.csv` | جدول selected outer metrics لكل fold |
| `reports/generated/manifests/cycle_34_nested_walk_forward.manifest.json` | manifest التقرير الرئيسي |
| `reports/generated/manifests/cycle_34_nested_fold_metrics.manifest.json` | manifest جدول المقاييس |

العدد الحالي من الاختبارات هو **149 collected / 149 passed** بحسب الفحص المحلي وartifact المولد. لا يُمنح أي release تجاري.
