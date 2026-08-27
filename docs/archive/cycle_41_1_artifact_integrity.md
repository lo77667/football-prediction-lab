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
reports/generated/cycle_41_1_service_smoke/runs/356b08d69b859a1d30e24865196ac120aacb118679127d859f1f202e57ba2ec0/
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

التشغيل الحالي يحمل `code_commit=513d818cabdf38f1a621fa1c005b46b287ce631f`، و`request_fingerprint` و`run_fingerprint` متساويان، و`source_manifest_fingerprint=2a07a99fe1041e034f782012a4d0801ecea62bfefe9801e234bc5a2e3b6e8d12`. لا توجد مخرجات current أو historical أخرى داخل root التسليم.

## hashes والعدادات

| الحقل | القيمة |
|---|---|
| request SHA-256 | `10666205536b926d5c54ef0f641bdb3b16f94a58dd7433e888cd33435d6b29cf` |
| response file SHA-256 | `453c2ff6daf0e3aa3482162574cb6a8475ecfe9faafd932c9d76ca5322c2ff83` |
| response content SHA-256 | `07b1f7994439ecfccd2ed80f20357b8481ae4f2f099924c5438311cd9fddd3eb` |
| ledger file SHA-256 | `617c13ae3a34998e8ddacbcfaa7305d736bc8c10a16c164034bfe4d9d5a29a50` |
| prediction artifact SHA-256 | `2d86adcb362c8fb325630793da5d799a0e44e9ff99a87f3a8048c2cf04548644` |
| manifest SHA-256 | `2894cfde1cc6f3e8ab0e9bd2b25f7685363fb62dc1811ea78a23ff0bd9ffc784` |
| validation SHA-256 | `ca5226b9bf19328d043310b1d22bbc5a857882b415196e9a9b4d024f1681620a` |
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

يُحسب request fingerprint من semantic request فقط، مع استبعاد request_id وoutput root وruntime timestamp وhostname. لذلك أعاد التشغيل أو تغيير output root نفس prediction IDs وprobabilities وresponse content hash. اختلاف request fingerprints بين تشغيل سابق والـrun الحالي يُسجل باعتباره ناتجاً عن اختلاف `expected_source_commit` الدلالي: التشغيل السابق كان على `b37f632`، أما التشغيل canonical الحالي فمبني على `513d818` بعد إصلاح validator؛ لا يُفسر الاختلاف بالوقت وحده.

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
