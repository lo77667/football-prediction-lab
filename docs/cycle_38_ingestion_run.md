# دورة 38 — تقرير التشغيل المحلي والـprovenance

## الملخص التنفيذي

اكتمل بناء عقد ingestion المحلي deterministic لملفات CSV المصرح بها. شُغّل العقد على fixture صغيرة test-only، ثم جرى التحقق من manifest والـhashes وإعادة التشغيل validation-only. لم تُستخدم بيانات تاريخية أو odds أو API خارجية، ولم يتغير أي نموذج أو feature list أو artifact من دورات 33–37.

| البند | النتيجة |
|---|---|
| نوع التشغيل | local CSV adapter، بلا شبكة |
| fixture | `tests/fixtures/cycle38_smoke/authorized_matches.csv` |
| season في fixture | `2425` فقط |
| rows read | 3 |
| rows accepted | 3 |
| rows quarantined | 0 |
| status | completed |
| deterministic sort | `kickoff_utc`, ثم `match_id` |
| replay | passed |
| validation | passed |
| commercial release | false |

## نتائج smoke run

شُغّل الأمر من جذر المستودع مع output root معزول تحت `reports/generated/cycle_38_smoke/` وبـsource policy معلنة `test-only-fixture`. نتجت الطبقات التالية: نسخة raw باسم input hash، normalized وprocessed بالـhash نفسه، quarantine report، manifest، وmatch registry.

| الحقل | القيمة |
|---|---|
| input SHA-256 | `9e7952716d52881ee3e86a93f9fe88b15a65551674c3462d6f073231ce95a8b0` |
| normalized output SHA-256 | `06599790c27e862d60153a88efbccac675add788340b9cddf3a3ab957d27a06b` |
| manifest fingerprint | `92e8346f0630d78942e01b8127df7b4fd80079809c03000a1031fa3eae605fac` |
| quarantine counts | `{}` |
| duplicate count | 0 |
| timezone failure count | 0 |
| replay output hash | مطابق للـnormalized output |
| replay fingerprint | مطابق للـmanifest fingerprint |

يعتمد fingerprint canonical على metadata غير المتغيرة ويحذف timestamps التشغيلية فقط. لذلك بقي fingerprint وoutput hash ثابتين عند إعادة التشغيل بنفس input و`run_id`، بينما تبقى أوقات التشغيل موثقة داخل run.

## الاختبارات

بعد إضافة ingestion contracts وadapter وscripts وfixtures، شُغّلت البوابة الكاملة داخل venv نظيفة تحتوي dependencies من `requirements.lock`:

```text
pytest -q                         186 passed
ruff check .                      All checks passed!
python -m compileall -q src scripts          passed
python -m compileall -q src scripts_*.py     passed
git diff --check                  passed
```

يغطي `tests/test_ingestion_cycle38.py` رفض timestamps naive، غياب timezone في Date + Time، target/post-match columns في pre-match، duplicate IDs، وصول source بعد kickoff، source hash conflict، idempotency، replay، والترتيب المستقل عن ترتيب الوصول.

## طبقات الحماية

ظل `2526` خارج tuning وselection وcalibration، ولم يُقرأ في هذا التشغيل. ظل `2627` محجوزًا وغير مقيم. لا يضيف ingestion targets أو post-match fields إلى normalized pre-match schema؛ الأعمدة المحظورة تُعزل مع سبب واضح. لا توجد odds أو ROI أو EV أو stake sizing أو معاملات مالية.

## provenance والقيود

كل manifest يذكر source name/version ووقت retrieval timezone-aware وinput hash وlicense/usage policy وschema version وrow count، إضافة إلى run ID وcommit وoutput hash والعدادات والـrejection reasons والمسارات. ولا تُحفظ الأسرار أو البيانات المحلية الكبيرة في Git. إعادة التقييم التاريخي تحتاج data محلية مصرحًا بها وmanifest/hash خارج المستودع.

الـexternal adapter غير مهيأ عمدًا؛ `UnavailableExternalAdapter` يفشل برسالة صريحة بدل تنزيل مصدر غير موثق. ولا يوجد API عامة أو dashboard أو scheduled execution أو background worker في دورة 38.

## ملفات الدورة

| الملف | الوظيفة |
|---|---|
| `src/football_prediction_lab/ingestion/contracts.py` | SourceRecord وMatchRecord وIngestionRun |
| `src/football_prediction_lab/ingestion/adapter.py` | interface وexternal fail-closed adapter |
| `src/football_prediction_lab/ingestion/local_csv.py` | local CSV normalization/validation/manifest |
| `scripts_ingest_local.py` | تشغيل ingestion |
| `scripts_validate_ingestion.py` | تحقق manifest وhashes |
| `scripts/replay_ingestion.py` | replay validation |
| `tests/test_ingestion_cycle38.py` | اختبارات العقد |
| `docs/cycle_38_ingestion_contract.md` | التصميم والقواعد |

## القرار

عقد ingestion المحلي اجتاز smoke execution والـvalidation والـreplay والبوابة المحلية. هذا يثبت correctness تشغيليًا على fixture test-only، ولا يثبت صلاحية مصدر خارجي أو أداء نموذج أو ربحية. تبقى الحالة البحثية فقط، و`commercial_release=false`.

## المراجع الداخلية

[1]: cycle_38_ingestion_contract.md "Cycle 38 ingestion contract"
[2]: ../src/football_prediction_lab/ingestion/contracts.py "Strict ingestion contracts"
[3]: ../src/football_prediction_lab/ingestion/local_csv.py "Deterministic local CSV adapter"
[4]: ../tests/test_ingestion_cycle38.py "Cycle 38 ingestion tests"
[5]: ../reports/generated/cycle_32_test_summary.json "Generated test summary"
