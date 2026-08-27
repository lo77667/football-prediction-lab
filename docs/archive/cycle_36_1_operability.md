# دورة 36.1 — قابلية التشغيل المستقل وفحص Ruff

## الحكم والتنفيذ

استجابت هذه الدورة للحكم المرحلي الذي أوقف الاعتماد على Cycle 36 حتى إصلاح قابلية التشغيل المستقل والتحقق من Ruff. نُفّذ إصلاح ضيق النطاق فقط: أضاف مشغل `scripts_evaluate_cycle36_candidates.py` bootstrap ذاتيًا لمسار `src` قبل imports، بحيث يعمل من checkout مباشرة دون اشتراط ضبط `PYTHONPATH` خارجيًا. أُضيف اختبار isolated import باستخدام Python `-I`، وأُبقيت خوارزميات candidates وبروتوكول الاختيار ونتائج Cycle 36 دون تغيير.

> دورة 36.1 ليست دورة نمذجة جديدة؛ إنها تصحيح تشغيلي واختبار انحدار للحفاظ على نتائج Cycle 36 كما هي.

| البند | الحالة |
|---|---|
| source commit قبل الإصلاح | `ed320db7ef3f639ca8457097708242cfe4886221` |
| source commit بعد الإصلاح | `4814ec2162b4ef9979d2d673f9323606dd9324bd` |
| artifact/report commit | `e8da8faad10a2f8a20ad3f9183504f37b88ee3f6` |
| نطاق التعديل | bootstrap لمسار `src` + isolated import test |
| تغيير منهج الاختيار | لا يوجد |
| تغيير candidates أو metrics | لا يوجد |
| تغيير Cycle 35 artifacts | لا يوجد |
| `commercial_release` | `false` |

## التشغيل المستقل

قبل الإصلاح، كان التشغيل العادي في البيئة الحالية ينجح بسبب إعدادات Python الموجودة في sandbox، لكن لم يكن هناك ضمان صريح بأن المشغل يهيئ مسار الحزمة بنفسه. بعد الإصلاح، شُغّل الأمر التالي مباشرة من جذر المستودع، مع إزالة `PYTHONPATH` من البيئة:

```text
env -u PYTHONPATH python3 scripts_evaluate_cycle36_candidates.py
```

انتهى الأمر بنجاح وأعاد إنشاء التقرير والسياسة و`fold_rows=16`. كما نجح اختبار Python المعزول الذي يستورد المشغل عبر `python -I` دون تنفيذ التقييم، وبذلك يتحقق من قابلية تحميل المشغل من checkout مستقل دون الاعتماد على user-site أو إعدادات البيئة الخارجية.

البيانات التاريخية المحلية تبقى dependency تشغيلية مقصودة وليست جزءًا من هذا الإصلاح؛ المسار `data/` غير متتبع في Git. لذلك يثبت هذا الإصلاح استقلال **تهيئة الحزمة والاستيراد**، ولا يدّعي أن checkout نظيفًا بلا ملفات البيانات يمكنه تنفيذ التقييم الكامل دون توفير مصدر البيانات المحلي المصرح به.

## فحص Ruff

شُغّل `ruff check .` بعد الإصلاح وانتهى بالرسالة `All checks passed!`. أُضيفت استثناءات `E402` موضعية فقط للاستيرادات التي تأتي بعد bootstrap الضروري لمسار `src`، ولم تُستخدم لإخفاء أخطاء أخرى أو تعطيل فحص عام.

## مقارنة النتائج قبل وبعد

حُفظ artifact Cycle 36 المنشور قبل الإصلاح، ثم أُعيد تشغيل evaluator مباشرة بعد الإصلاح. قورنت نسختا JSON بعد التطبيع الذي يحذف timestamp المتغير داخل policy فقط؛ كانت نتيجة المقارنة `cmp exit=0`.

| مجال المقارنة | النتيجة |
|---|---|
| selected variants لكل fold | مطابق |
| inner metrics | مطابق |
| outer metrics | مطابق |
| pooled BTTS metrics | مطابق |
| pooled cards metrics | مطابق |
| stability summaries | مطابق |
| guards الخاصة بـ2526 و2627 | مطابقة |
| `commercial_release` | `false` في النسختين |

تظل نتائج Cycle 36 كما يلي: BTTS على `3040` صفًا، Brier `0.249659`، Log Loss `0.692532`، ROC-AUC `0.514845`، AP `0.541149`، وECE `0.014413`. والبطاقات على `3040` صفًا، Brier `0.243157`، Log Loss `0.679693`، ROC-AUC `0.584453`، AP `0.534528`، وECE `0.033805`. هذه أرقام development outer evaluation وليست نتيجة تجارية أو توصية مالية.

## الاختبارات المحلية

بعد commit `4814ec2`، أعيد تشغيل الاختبارات الكاملة وسجل test summary عدد **164 collected / 164 passed**. كما نجحت البوابات التالية:

| الفحص | الحالة |
|---|---|
| `pytest -q` | 164 passed |
| `ruff check .` | ناجح |
| `python -m compileall -q src scripts_*.py` | ناجح |
| `git diff --check` | ناجح |
| isolated import test | ناجح |
| direct evaluator بدون `PYTHONPATH` | ناجح |

يشمل اختبار Cycle 36.1 الجديد تحميل المشغل في Python معزول، بينما تظل اختبارات Cycle 36 الأصلية مسؤولة عن mutation leakage، رفض `2526` في development، حماية `2627`، صلاحية Poisson probabilities، وحتمية bootstrap.

## الحماية الزمنية والقرار

لم تُقرأ labels موسم `2526` لإعادة tuning أو selection أو calibration. ظل موسم `2526` خارج development، وظل `2627` future holdout محجوزًا وغير مقيم. لم تدخل odds أو ROI أو EV أو stake sizing أو تنفيذ مالي. لا يغير هذا الإصلاح حالة الجاهزية؛ تبقى `ready_for_future_2627_holdout=false` وفق تقرير Cycle 36 لأن نتائج الاستقرار لم تحقق gate المطلوبة لكل سوق، وتبقى `commercial_release=false`.

## حالة CI

بعد نشر commit 36.1، اكتمل أحدث run `quality-gate` رقم `32911509886` على commit `e8da8faad10a2f8a20ad3f9183504f37b88ee3f6` بحالة `failure`. كان job `test-and-lint` بحالة failure مع `steps: []`، أي دون أي خطوات تنفيذ فعلية. لذلك لا يوجد دليل CI قابل للتحقق على فشل الاختبارات أو Ruff داخل الكود؛ الحالة توصف بدقة كفشل runner/تهيئة، بينما بقيت البوابات المحلية ناجحة.

## الملفات المعدلة في 36.1

| الملف | التعديل |
|---|---|
| `scripts_evaluate_cycle36_candidates.py` | تهيئة ذاتية لمسار `src` قبل imports |
| `tests/test_cycle36_models.py` | اختبار isolated import للمشغل |
| `reports/generated/cycle_36_candidate_evaluation.json` | أُعيد توليده provenance-only بعد الإصلاح، مع نتائج مطابقة |
| `configs/cycle36_future_holdout_policy.json` | أُعيد توليده provenance-only، دون تغيير السياسة |
| `reports/generated/cycle_32_test_summary.json` | عدد الاختبارات الجديد والطابع الزمني والـcommit |
| `docs/cycle_36_1_operability.md` | هذا التقرير |

## المراجع الداخلية

[1]: ../scripts_evaluate_cycle36_candidates.py "Cycle 36 evaluator"
[2]: ../tests/test_cycle36_models.py "Cycle 36 and 36.1 tests"
[3]: ../reports/generated/cycle_36_candidate_evaluation.json "Cycle 36 evaluation artifact"
[4]: ../configs/cycle36_future_holdout_policy.json "Future holdout policy for 2627"
[5]: ../reports/generated/cycle_32_test_summary.json "Generated test summary"
[6]: cycle_36_candidate_models.md "Cycle 36 candidate models report"
