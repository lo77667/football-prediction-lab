# دورة 38.1 — Migration Note لبصمة manifest

## سبب الإصلاح

اكتشفت دورة 38.1 أن `normalized/processed output hash` كان ثابتًا عند تشغيل نفس input و`run_id`، لكن `manifest_fingerprint` كان يتغير بين output roots مختلفة. السبب أن التنفيذ القديم كان يضع absolute paths وبعض runtime metadata داخل payload الذي يُهش، رغم أن التقرير أعلن حذفها من canonical payload.

هذا الإصلاح محدود بالبصمة والتحقق وإعادة التشغيل. لم تتغير models أو features أو evaluation metrics أو policy `2526/2627`، ولم يُستخدم مصدر خارجي أو odds.

## الفصل الجديد

أصبح هناك فرق صريح بين:

| الهوية | المحتوى |
|---|---|
| `run_id` | هوية عملية التنفيذ، وتبقى داخل `run` metadata ولا تدخل fingerprint |
| `input_sha256` | هوية bytes المصدر |
| `output_sha256` | hash المخرج serialized الفعلي، وقد يتغير إذا احتوى المخرج runtime run ID |
| `manifest_fingerprint` | hash canonical لمحتوى ingestion، مستقل عن الوقت والمسار وrun ID |

تحتوي manifest التشغيلية على timestamps وpaths المحلية للتدقيق، لكن `canonical_manifest_payload()` لا يقرأها. ويستخدم payload JSON UTF-8 مع `sort_keys=True` وseparators ثابتة، ويرتب rejection keys وartifact roles، ويهش accepted-record content بعد تطبيع الأنواع والتوقيت إلى UTC.

تحتوي artifacts على `artifact_role` و`artifact_filename` و`relative_artifact_key` و`content_sha256` في manifest التشغيلية. أما canonical payload فيستخدم `artifact_role` و`content_sha256` فقط؛ فلا تدخل filenames أو absolute paths في البصمة.

## old/new smoke evidence

أُعيد توليد fixture نفسها `tests/fixtures/cycle38_smoke/authorized_matches.csv`، وهي test-only وتحتوي season `2425` فقط.

| الحقل | قبل 38.1 | بعد 38.1 |
|---|---|---|
| manifest file SHA-256 | `b3611456baa8cf103b97d736c3ddbc2ed436924fef6c272ef8b1c453503cd98d` | `bcd2b7e026db095b731a68455276f8b1bb1a5b6c00bce926b1c4551b0e0b4acf` |
| `manifest_fingerprint` | `92e8346f0630d78942e01b8127df7b4fd80079809c03000a1031fa3eae605fac` | `606757a7a8dd9d96e79145479aa8f68e1d4d82102f24d0cf5c1105cb0603a202` |
| normalized output hash | `06599790c27e862d60153a88efbccac675add788340b9cddf3a3ab957d27a06b` | `06599790c27e862d60153a88efbccac675add788340b9cddf3a3ab957d27a06b` |
| processed output hash | `06599790c27e862d60153a88efbccac675add788340b9cddf3a3ab957d27a06b` | `06599790c27e862d60153a88efbccac675add788340b9cddf3a3ab957d27a06b` |
| rows read/accepted/quarantined | `3/3/0` | `3/3/0` |
| `artifacts` وaccepted record hash | غير موجودين في manifest القديم | موجودان ومتحققان |

تغير old/new manifest hash وfingerprint **متوقع** لأن schema وcanonicalization contract تغيرا. لم يُعدّل normalized output يدويًا؛ بقي output content hash نفسه.

## اختبارات invariants

تثبت الاختبارات الجديدة ما يلي:

| invariant | النتيجة |
|---|---|
| نفس input وrun ID وroot مختلفان | fingerprint متطابق |
| نفس input وroot مختلفان | output content fingerprint متطابق |
| run ID مختلف | fingerprint متطابق، وrun identity مختلفة، وserialized output hash مختلف بسبب run metadata |
| تغيير input byte واحد | input hash وfingerprint مختلفان |
| تغيير accepted content | output hash وfingerprint مختلفان |
| تغيير row counts أو rejection counts | fingerprint مختلف |
| تغيير runtime timestamps والمسارات | fingerprint لا يتغير |
| إعادة ترتيب JSON/rejection keys | fingerprint لا يتغير |
| replay | يعيد input/output/fingerprint و`replay=passed` بلا كتابة نسخة جديدة |

في المقارنة التشغيلية النهائية أعطت النتائج:

```text
same_root_fingerprint=true
same_root_output=true
different_run_content_fingerprint=true
different_run_identity=true
changed_input_hash=true
changed_input_fingerprint=true
```

## validator وreplay

يُعيد `validate_manifest()` حساب raw hash وserialized normalized/processed hashes وaccepted-record canonical hash وquarantine counters ثم يعيد حساب `canonical_manifest_fingerprint`. يرفض validator manifestًا قديمًا يفتقد canonical fields بدل قبول بصمة غير قابلة للتحقق.

يعيد `replay_manifest()` التحقق فقط، ولا ينشئ raw أو processed نسخة جديدة. وتشمل النتيجة `input_sha256` و`output_sha256` و`manifest_fingerprint` و`replay=passed`.

## التشغيل المحلي

داخل venv النظيفة (`/tmp/cycle37-clean-venv`) نجحت اختبارات دورة 38.1 المستهدفة:

```text
pytest tests/test_ingestion_cycle38.py   16 passed
ruff check relevant files                All checks passed!
compileall ingestion/scripts             passed
```

سيُعاد تشغيل البوابة الكاملة بعد تثبيت commit دورة 38.1 وتحديث test summary. لا تُستخدم `2526` أو `2627` في هذا الاختبار، ولا توجد commercial release؛ الحالة تبقى `commercial_release=false`.

## المراجع الداخلية

[1]: ../src/football_prediction_lab/ingestion/local_csv.py "Canonical manifest and ingestion validator"
[2]: ../tests/test_ingestion_cycle38.py "Cycle 38 and 38.1 invariants"
[3]: cycle_38_ingestion_contract.md "Cycle 38 ingestion contract"
[4]: cycle_38_ingestion_run.md "Cycle 38 smoke run"
