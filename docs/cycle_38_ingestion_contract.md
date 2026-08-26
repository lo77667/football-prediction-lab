# دورة 38 — عقد ingestion التشغيلي قبل المباراة

## الغرض والنطاق

تبني دورة 38 طبقة ingestion محلية deterministic وقابلة للتدقيق لملفات CSV المصرح بها. الهدف هو تجهيز حد فاصل واضح بين المصدر الخام والبيانات الموحدة والبيانات الصالحة للبناء والميزات والتوقعات، مع عزل الرفض في quarantine وتسجيل provenance كامل. لا تنفذ الدورة API عامة أو dashboard أو authentication أو scheduled execution أو background worker، ولا تضيف odds أو مصدرًا خارجيًا.

> ingestion قبل المباراة لا يقبل targets أو post-match fields، ولا يقبل timestamp naive في `kickoff_utc` دون سياسة timezone معلنة.

## طبقات البيانات

يستخدم المشغل الجذر المنطقي التالي عند تمرير `--output-root`:

| الطبقة | الغرض | سياسة التعديل |
|---|---|---|
| `raw/` | نسخة bytes من CSV المصدر | immutable؛ collision hash مختلف مرفوض |
| `normalized/` | schema موحد لهوية المباراة والـkickoff | يعاد بناؤه من نفس input hash |
| `processed/` | نسخة صالحة للبناء downstream | لا تحتوي صفوف quarantine |
| `features/` | ميزات pre-match فقط | ليست جزءًا من هذا المشغل |
| `predictions/` | توقعات بلا targets | ليست جزءًا من هذا المشغل |
| `quarantine/` | أسباب الصفوف المرفوضة وsample محدود | لا تُحذف تلقائيًا |
| `manifests/` | provenance وhashes والعدادات | سجل تشغيل قابل للتحقق |

لا ينشئ المشغل `data/` تلقائيًا داخل Git. إذا كان input غير موجود، يفشل برسالة `authorized local CSV not found` بدل الاعتماد على مسار صامت أو تنزيل مصدر غير موثق.

## عقود المصدر والتشغيل

توجد العقود في `src/football_prediction_lab/ingestion/contracts.py` باستخدام Pydantic مع `extra='forbid'` وقيود non-empty. يحتوي `SourceRecord` على اسم المصدر وإصداره ووقت الاسترجاع timezone-aware ومسارًا غير سري وSHA-256 وسياسة الاستخدام وإصدار schema وعدد الصفوف. ويحتوي `MatchRecord` على match identity وseason وcompetition والفرق و`kickoff_utc` وprovenance ID وrun ID و`record_version`، ولا يتيح fields للنتائج.

يحتوي `IngestionRun` على run ID وأوقات البداية والنهاية وsource metadata وcommit وinput/output hashes وعدادات القراءة والقبول والعزل والحالة وملخص الأخطاء. تُرفض timestamps naive، وIDs الفارغة، والعدادات غير المنطقية، والحالة خارج `completed|failed|quarantined`.

## adapter interface

يحدد `DataSourceAdapter` lifecycle methods هي `discover` و`fetch` و`normalize` و`validate` و`write_immutable_raw` و`build_manifest`. التطبيق الحالي هو `LocalCsvAdapter` لملف CSV محلي مصرح به فقط. ويوجد `UnavailableExternalAdapter` يعيد خطأً صريحًا عند محاولة استخدام مصدر خارجي غير مهيأ؛ لا توجد API calls في دورة 38.

يدعم adapter أسماء `match_id` و`home_team` و`away_team` و`season` و`competition`، ويدعم إما `kickoff_utc` timezone-aware أو `Date` + `Time` مع `--source-timezone` صريح. يتحول الزمن إلى UTC، وتفرز الصفوف حتميًا بـ`kickoff_utc` ثم `match_id` باستخدام stable sort.

## قواعد الرفض وquarantine

يُعزل الصف إذا كان match ID أو team فارغًا، أو كان الفريقان متساويين، أو كان kickoff غير قابل للتحليل أو بلا timezone، أو كان season/competition غير صالح، أو كان `record_version` غير موجب. ويُعزل الصف أيضًا إذا كان `available_at_utc` بعد kickoff أو غير timezone-aware، أو إذا ظهرت أعمدة target/post-match مثل `btts` أو `home_goals` أو `home_yellows` في pre-match input.

تُسجل أسباب الرفض في `quarantine/<run_id>.json` مع `rejection_counts_by_reason` وsample لا يتجاوز 100 عنصرًا. يُحسب `rows_quarantined` على مستوى الصفوف الفريدة لا على عدد الأسباب المكررة. الحد الافتراضي المعلن هو `max_rejection_rate=0.25`؛ إذا تجاوزته النسبة يُحفظ manifest وquarantine ثم يفشل المشغل برسالة واضحة.

## idempotency وimmutability

المسار الخام يعتمد على input SHA-256، والمساران normalized وprocessed يعتمدان على input SHA-256 أيضًا، ولذلك لا ينشئ إعادة تشغيل الملف نفسه نسخة محتوى جديدة. عند وجود raw بالمسار نفسه، يُعاد حساب hash؛ يمر الملف إذا تطابق، ويفشل إذا اختلف المحتوى.

يحتوي manifest على `manifest_fingerprint` canonical يحذف timestamps التشغيلية المتغيرة من run ووقت retrieved، لكنه يحتفظ بالـsource hash والـoutput hash والعدادات والـrun ID. لذلك تعطي إعادة التشغيل نفسها بنفس `run_id` fingerprint وoutput hash متطابقين. وإذا ظهر match ID مقبول سابقًا مع source hash مختلف، لا يُستبدل السجل القديم؛ يُعزل السجل الجديد بسبب `existing_match_id_different_source_hash`.

## provenance وmanifest

ينتج كل run manifestًا يتضمن source metadata، input/output/raw/quarantine paths، hashes، schema versions، season range، time range، timezone، عدادات القراءة والقبول والعزل، rejection counts، duplicate count، timezone failure count، سياسة الحد، وحقول target المحظورة. كما يُنتج `match_registry.json` بقائمة IDs المقبولة في run الحالي.

يتحقق `scripts_validate_ingestion.py` من عقد `IngestionRun` وinput/output hashes وraw immutable hash وحسابات الصفوف. ويعيد `scripts/replay_ingestion.py` validation فقط؛ لا ينشئ version جديدة ولا يقرأ targets.

## التشغيل المحلي

بعد تثبيت الحزمة، يدعم المشروع الأوامر التالية:

```bash
python scripts_ingest_local.py \
  --input tests/fixtures/cycle38_smoke/authorized_matches.csv \
  --run-id smoke-001 \
  --output-root /tmp/cycle38-output \
  --source-name cycle38_smoke \
  --source-version fixture-v1 \
  --license-or-usage-policy test-only-fixture \
  --season 2425 \
  --competition EPL

python scripts_validate_ingestion.py \
  --manifest /tmp/cycle38-output/manifests/smoke-001.json

python scripts/replay_ingestion.py \
  --manifest /tmp/cycle38-output/manifests/smoke-001.json
```

الـfixture في `tests/fixtures/cycle38_smoke/authorized_matches.csv` test-only ولا يعيد إنتاج metrics التاريخية. إعادة إنتاج التقييمات التاريخية تحتاج البيانات المحلية المصرح بها وmanifest/hash خارج Git. لا تُضمّن دورة 38 بيانات 2526 أو 2627، ولا تستخدم أي odds.

## الحماية الزمنية

لا يغيّر هذا العقد نماذج أو feature lists أو artifacts أو نتائج دورات 33–37. يظل موسم `2526` خارج tuning وselection وcalibration، وتظل policy موسم `2627` محجوزة. كما لا يضيف هذا المشغل أي targets أو post-match fields إلى pre-match records، ولا يسمح بالصفوف المتاحة بعد kickoff.

## الملفات

| الملف | الدور |
|---|---|
| `src/football_prediction_lab/ingestion/contracts.py` | عقود Pydantic الصارمة |
| `src/football_prediction_lab/ingestion/adapter.py` | interface وexternal fail-closed adapter |
| `src/football_prediction_lab/ingestion/local_csv.py` | adapter وقواعد ingestion وmanifest |
| `scripts_ingest_local.py` | تشغيل ingestion محليًا |
| `scripts_validate_ingestion.py` | تحقق manifest وhashes |
| `scripts/replay_ingestion.py` | replay validation بلا كتابة جديدة |
| `tests/test_ingestion_cycle38.py` | اختبارات الزمن والرفض والتكرار والترتيب |
| `tests/fixtures/cycle38_smoke/authorized_matches.csv` | fixture test-only |

## القيود

هذه طبقة عقد وتشغيل محلي، وليست API عامة أو نظام إنتاج كامل. لا تُمنح صلاحية تجارية، ولا تنفذ رهانات أو نقل أموال أو stake sizing أو ROI/EV، ولا تستورد مصدرًا خارجيًا بلا ترخيص وprovenance ووقت إتاحة واضح.

## المراجع الداخلية

[1]: ../src/football_prediction_lab/ingestion/contracts.py "Cycle 38 contracts"
[2]: ../src/football_prediction_lab/ingestion/adapter.py "Adapter interface"
[3]: ../src/football_prediction_lab/ingestion/local_csv.py "Local deterministic ingestion adapter"
[4]: ../scripts_ingest_local.py "Local ingestion runner"
[5]: ../scripts_validate_ingestion.py "Manifest validator"
[6]: ../scripts/replay_ingestion.py "Replay validator"
[7]: ../tests/test_ingestion_cycle38.py "Cycle 38 ingestion tests"
