# دورة 41.1: سلامة artifacts وfail-closed

## القرار

أُصلحت في هذه الدورة مشكلة سلامة التسليم التي كانت تسمح بتمرير response مع ledger مفقود، وتخلط مخرجات تشغيلات مختلفة تحت مسارات مشتركة. التغيير محصور في التحقق والتنظيم والتوثيق؛ لم تتغير models أو features أو policy أو evaluation metrics أو نتائج الدورات السابقة، ولم تُضف شبكة أو مصدر خارجي أو API عامة أو scheduler.

> لا يمر validator الآن إلا عند وجود response وledger وprediction artifact وrequest وmanifest وvalidation ضمن تشغيل ذري واحد قابل للمطابقة.

## الإصلاحات

أصبح `scripts_validate_service_response.py` fail-closed. عند تمرير ledger مفقود أو directory أو ملف غير قابل للقراءة يخرج الأمر بخطأ غير صفري. وإذا أعلن response `ledger_records > 0` فلا يجوز حذف وسيطة ledger. يعاد حساب response content hash، وledger file SHA، وprediction artifact SHA، وتُفحص سلسلة ledger والـevent sequence وprediction IDs والحقول المحظورة.

أضيفت `src/football_prediction_lab/service/artifact_validation.py` كوحدة تحقق مركزية. وهي تطابق request fingerprint وrequest SHA وresponse file SHA وledger SHA وprediction artifact SHA وcode commit وpolicy/model/feature versions وsource manifest fingerprint وas_of. وبسبب أن Shadow Runner يكتب سوقي BTTS وcards، يشرح العقد الفرق صراحة بين `response_predictions_count=3` و`ledger_events_count=6` و`ledger_prediction_count=6` و`ledger_markets=["btts", "cards"]`.

أصبح health محصوراً في atomic run directory كامل؛ manifest file منفرد لا يكفي لإرجاع `healthy`. عند غياب ledger أو اختلاف hash تصبح الحالة `blocked_provenance`، ولا تُصدر الخدمة predictions جديدة من هذا المسار.

## atomic run الحالي

يولد `scripts_run_service_smoke.py` تشغيلًا واحدًا داخل:

```text
reports/generated/cycle_41_1_service_smoke/runs/6f064823acc7af0814601703500a173ec5c64fd9b02e319c689ad8d9e0df480d/
```

ويحتوي المجلد فقط على:

| الملف | الوظيفة |
|---|---|
| `service_request.json` | الطلب الدلالي المصدق |
| `service_response.json` | response prelabel للموقـع المطلوب |
| `service_manifest.json` | hashes وprovenance والـcounts |
| `shadow_ledger.jsonl` | ledger حقيقي قابل للتحقق، 6 records |
| `predictions_prelabel.jsonl` | prediction artifact كامل للسوقين، 6 records |
| `validation.json` | نتيجة التحقق لنفس المجلد |

التشغيل الحالي يحمل `code_commit=dddd524a17d6747e8ee700cfbc3bb423ae398dd0`، و`request_fingerprint` و`run_fingerprint` متساويان، و`source_manifest_fingerprint=2a07a99fe1041e034f782012a4d0801ecea62bfefe9801e234bc5a2e3b6e8d12`. لا توجد مخرجات current أو historical أخرى داخل root التسليم.

## hashes والعدادات

| الحقل | القيمة |
|---|---|
| request SHA-256 | `369b0fe4007a8e66b305cd7683867c16f675e5abf87e221898ab18f54f5973c5` |
| response file SHA-256 | `63eeae95df56c9ce460c60e0c0059e2b03f609576b80b7436a6f40e16c316f69` |
| response content SHA-256 | `244fd2d652b2766b8d00d012593a38acaad3512463298966ed0098ba037780d5` |
| ledger file SHA-256 | `617c13ae3a34998e8ddacbcfaa7305d736bc8c10a16c164034bfe4d9d5a29a50` |
| prediction artifact SHA-256 | `722a16bdc847e42577cc424c3ec5d134c58b065c7c15dc9606fac1c57e5322e5` |
| manifest SHA-256 | `15349fdd5749891a70fdd76cb07bc49d719478fa98ac7b3d52e06845c1d239ef` |
| validation SHA-256 | `4bafc91009b01c97a2a1021e5b3d95fdd3dda621d64dc7d85064ec2eb349140a` |
| response predictions | `3` |
| ledger events/predictions | `6 / 6` |
| ledger markets | `btts`, `cards` |
| skipped items | `0` |
| commercial release | `false` |

## fail-closed evidence

الاختبار الإيجابي للـrun الكامل أعاد `validation=passed`. وعند تشغيل validator بالـresponse نفسه مع:

```text
--ledger /tmp/nonexistent-cycle41-1-ledger.jsonl
```

كانت النتيجة exit code `1`. كما تفشل الحالات التالية: ledger فارغ مع response يعلن ستة records، ledger count مختلف، ledger SHA مختلف، commit أو request fingerprint مختلط، artifact prediction ID غير مطابق، response يحوي odds أو field مالي، وresponse بلا ledger بينما يعلن records موجبة.

## artifact index

ينشئ `scripts_index_service_artifacts.py` فهرساً مستقلاً يحدد `active_run_fingerprint` ويعرض كل المسارات النسبية وcontent SHA وsource commit و`current=true`. لا يعتمد الفهرس على absolute paths، ولا يترك ملفين بنفس basename ليبدوا تشغيلًا واحداً. التشغيل الحالي هو الوحيد الموسوم `current`، ولا توجد historical runs في حزمة هذه الدورة.

## الحتمية وportability

يُحسب request fingerprint من semantic request فقط، مع استبعاد request_id وoutput root وruntime timestamp وhostname. لذلك أعاد التشغيل أو تغيير output root نفس prediction IDs وprobabilities وresponse content hash. اختلاف request fingerprints بين تشغيل سابق والـrun الحالي يُسجل باعتباره ناتجاً عن اختلاف `expected_source_commit` الدلالي: التشغيل السابق كان على `b37f632`، أما التشغيل canonical الحالي فمبني على `dddd524` بعد إصلاح validator؛ لا يُفسر الاختلاف بالوقت وحده.

## الاختبارات

أضيفت اختبارات explicit لـmissing ledger وempty ledger وcount mismatch وledger SHA mismatch وmixed commits وmixed fingerprints وID consistency وhealth gate وoutput-root invariance والحقول المالية. نتيجة بوابة الجودة الكاملة على venv النظيفة:

| الفحص | النتيجة |
|---|---|
| `python -m pytest -q` | `254 passed` |
| `ruff check .` | `All checks passed` |
| `python -m compileall -q src scripts_*.py` | passed |
| `git diff --check` | passed |
| smoke + atomic validator | passed |
| missing-ledger negative test | failed closed، exit code 1 |

## الحدود

ما زال external source وeconomic benchmark مؤجلين. لا توجد targets أو post-match labels أو odds أو EV أو ROI أو stake sizing أو financial execution. policy 2526/2627 محفوظة: 2526 خارج التطوير و2627 محجوز، و`commercial_release=false` ثابتة. لا تنتقل الخدمة إلى نشر عام أو دورة 42 قبل اعتماد قرار مستقل.
