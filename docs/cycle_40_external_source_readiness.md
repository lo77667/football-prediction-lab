# دورة 40: External Source Readiness

**الحالة:** مكتملة كمسار readiness مؤجل، ولا يوجد مصدر خارجي حقيقي معتمد داخل هذه الدورة.

**القرار الأساسي:** `external_source_status=deferred_missing_authorized_source`.

لم يقدّم المستخدم في هذه الدورة ملفاً خارجياً مرخصاً أو provider محدداً مع سياسة استخدام واضحة أو credentials صريحة. وبناءً على ذلك لم يُجرَ أي اتصال شبكي، ولم تُستخدم API عشوائية، ولم تُنزّل بيانات خارجية، ولم تُنشأ أرقام اقتصادية. هذا هو المسار الصحيح عند غياب مصدر موثق، وليس دليلاً على جودة النموذج.

> بوابة المصدر تتحقق من قابلية استقبال بيانات موثقة؛ ولا تثبت صلاحية نموذج التنبؤ أو profitability أو أي benchmark اقتصادي.

## 1. حدود دورة 40

تحافظ الدورة على نماذج وميزات وسياسة ونتائج الدورات 33–39 دون تعديل. لم تُستخدم 2526 في tuning أو selection أو calibration، وبقي 2627 محجوزاً وفق policy دورة 36/2627. لا توجد رهانات أو معاملات أو stake sizing أو API عامة أو scheduler أو worker دائم.

| القيد | التطبيق |
|---|---|
| مصدر خارجي حقيقي | غير متوفر؛ لا source verified |
| مصادر مسموحة | القائمة فارغة عمداً في policy |
| إعادة الاستخدام | غير مسموح دون authorization موثق |
| cutoff | UTC؛ captured/available يجب أن يسبقا cutoff وkickoff وفق الحالة |
| closing odds | غير مسموحة في policy الحالية |
| seasons المحمية | 2526 و2627 محميتان؛ 2627 future holdout |
| economic benchmark | `deferred`؛ لا edge أو EV أو ROI أو odds output |
| الإصدار التجاري | `commercial_release=false` دائماً |

## 2. العقود والـadapter

يعرّف `external_contracts.py` عقد `ExternalSource` لمعلومات المصدر غير السرية: الاسم، provider، dataset أو endpoint identifier غير السري، الإصدار، الترخيص أو policy reference، allowed reuse، timestamps، snapshot/request ID، SHA-256، schema، retention، وowner غير حساس. يرفض العقد المصدر بلا license/policy أو timestamp أو input hash أو source version، كما يمنع markers الشائعة للأسرار في metadata.

ويعرّف `ExternalSnapshotRecord` هوية الحدث أو المباراة، kickoff، capture/availability timestamps، snapshot version، input hash، وحقول market/odds الاختيارية. لا يُقبل سجل pre-match إذا كان `captured_at_utc >= kickoff_utc` أو `available_at_utc >= kickoff_utc`. وعند وجود odds يجب أن تكون decimal odds أكبر من 1، وأن تكون market definition وselection وodds type واضحة؛ لا توجد في readiness الحالية أي odds فعلية أو fair probability أو overround calculation.

| الوحدة | الغرض |
|---|---|
| `src/football_prediction_lab/ingestion/external_contracts.py` | عقود المصدر والسجل الخارجي مع timezone/hash/license guards |
| `src/football_prediction_lab/ingestion/external_adapters.py` | interface موحد و`UnavailableExternalAdapter` بلا network call |
| `src/football_prediction_lab/ingestion/external_readiness.py` | policy loader، deferred report، provenance/hash/matching/cutoff audit |
| `configs/cycle40_external_source_policy.yaml` | policy version وallowed sources وcutoff وretention والحماية الزمنية |
| `scripts_audit_external_source.py` | تشغيل readiness محلياً عبر `--mode readiness` |
| `scripts_cycle40_test_summary.py` | توليد عدد pytest الفعلي وعدم تثبيت عدد يدوي |
| `tests/test_external_source_readiness.py` | اختبار fail-closed والسلوك الزمني والمطابقة وعدم الأسرار |

إذا وفر المستخدم لاحقاً ملفاً خارجياً مرخصاً، فالخطوة الآمنة التالية هي adapter file-based أولاً، مع manifest للملف نفسه وترخيصه وhashه وتوقيتاته؛ لا تُضاف API حقيقية تلقائياً.

## 3. سياسة المصدر

توجد policy في `configs/cycle40_external_source_policy.yaml` بإصدار `cycle40-readiness-deferred-v1`. `allowed_sources` فارغة، ولذلك لا يُسمح للتنفيذ بادعاء وجود مصدر موثق. ويعلن التقرير صراحة أن الحالة deferred، مع `source_count=0` و`raw_rows=0` و`valid_rows=0` و`matched_rows=0`.

يحدد cutoff protocol المنطقة الزمنية UTC، ويمنع closing odds، ويحدد maximum age معلناً، كما يحدد tolerance مطابقة kickoff بخمس دقائق عند وجود مصدر مرخص لاحقاً. وتبقى إعادة الاستخدام غير مسموحة ضمن سياسة retention الحالية.

## 4. نتيجة readiness الفعلية

شُغّل الأمر التالي في البيئة النظيفة:

```bash
python scripts_audit_external_source.py --mode readiness
```

النتيجة المولدة في `reports/generated/cycle_40_source_readiness.json` هي:

| المؤشر | النتيجة |
|---|---:|
| `external_source_status` | `deferred_missing_authorized_source` |
| `source_status` | `source_deferred` |
| `source_count` | 0 |
| `allowed_source_count` | 0 |
| `raw_rows` | 0 |
| `valid_rows` | 0 |
| `matched_rows` | 0 |
| `unmatched_rows` | 0 |
| `ambiguous_rows` | 0 |
| `late_rows` | 0 |
| `missing_provenance` | 0 |
| `license_failures` | 0 |
| `duplicate_snapshots` | 0 |
| `benchmark_status` | `deferred` |
| `commercial_release` | `false` |
| policy SHA-256 | `4eac304503cddfb168975d0604577ed7f632637983df53f130d4350015316ece` |
| readiness report SHA-256 | `54803f7cf1e8b37012cef177251040809dc6e54bca9f4e0fddd41e07c8714bd5` |

هذه أرقام readiness لعدم وجود مصدر، وليست أرقام تغطية سوق أو أداء نموذج. لا يوجد source manifest حقيقي؛ deferred report نفسه هو manifest evidence لمسار الغياب المصرح.

## 5. الاختبارات والـquality gates

أضيفت اختبارات تثبت رفض المصدر بلا license، رفض timestamp غير aware، رفض snapshot بعد kickoff، رفض hash غير صالح أو غير المطابق للمصدر، عزل duplicate snapshots، عدم الربط العشوائي للمباراة unknown أو ambiguous، حماية 2526/2627، عدم استدعاء network من unavailable adapter، deterministic replay، غياب الحقول الاقتصادية والأسرار من deferred artifact، وثبات `commercial_release=false`.

| الفحص | النتيجة |
|---|---|
| `python -m pytest -q` | `216 passed` |
| `pytest --collect-only` عبر Cycle 40 summary | `216 collected` |
| collected/passed invariant | `216 == 216` |
| `ruff check .` | `All checks passed` |
| `python -m compileall -q src scripts_*.py` | passed |
| `git diff --check` | passed |
| `scripts_audit_external_source.py --mode readiness` | deferred، بدون network |
| no-source benchmark | deferred؛ لا edge/EV/ROI |

يوثق `reports/generated/cycle_40_test_summary.json` العدد المولد فعلياً مع timestamp UTC وcommit ونسخ Python/pytest/Ruff. ولا تُخلط fixtures الاختبارية مع metrics أو historical reports أو commercial ledger.

## 6. حالة CI

تم دفع مصدر دورة 40 إلى repository الخاص `lo77667/football-prediction-lab`. آخر run موثق على commit `6ef4cc4bc3fd4ae1fc9133e9a15936ba2d028d57` هو run `32976877125` [1]. انتهى run بـ`failure` قبل تنفيذ أي خطوة؛ job Python 3.12 بالمعرف `98203655621` وjob Python 3.11 بالمعرف `98203655815` ظهرا بـ`steps=[]`. لا يوجد log تنفيذ قابل للاستخراج.

بالتالي، quality gates المحلية ناجحة، بينما CI البعيد **runner-blocked قبل step execution**. لا يصح ادعاء نجاح CI، ولا يصح نسبة failure إلى pytest أو Ruff لأن runner لم يبدأ الأوامر. تعريف workflow نفسه يحتوي steps صريحة، لكن الدليل التشغيلي البعيد لا يزال يثبت الفشل قبل التنفيذ.

## 7. الخلاصة

تغلق Cycle 40 بوابة المصدر في حالة deferred الآمنة: لا يوجد مصدر خارجي حقيقي موثق، ولا بيانات خارجية مستخدمة، ولا secrets في Git أو logs، ولا economic benchmark. أصبح للمشروع عقد واضح لاستقبال مصدر مصرح به لاحقاً، وadapter fail-closed، وسياسة cutoff وretention، وquality gates للمطابقة الزمنية والترخيص والhash والهوية.

لا تعني هذه النتيجة أن النموذج جاهز تجارياً أو أن التنبؤات مربحة. تبقى `commercial_release=false`، وتبقى نتائج دورات 33–39 دون تعديل.

### المراجع

[1]: https://github.com/lo77667/football-prediction-lab/actions/runs/32976877125 "GitHub Actions quality-gate run 32976877125"
