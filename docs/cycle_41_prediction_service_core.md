# دورة 41: Prediction Service Core محلي

## الملخص التنفيذي

أُنشئت في دورة 41 طبقة **Prediction Service Core** محلية تفصل عقد الخدمة عن التطبيق وعن transport. تستقبل الطبقة طلباً داخلياً يشير إلى manifest متحقق، وتستدعي Shadow Runner الموجود بدلاً من تكرار منطق التنبؤ، ثم تعيد response prelabel قابلاً للتدقيق وتدعم Shadow Ledger append-only. لم يُنشر endpoint عام، ولم تُستخدم شبكة أو مصادر خارجية أو scheduler أو labels أو odds أو EV أو ROI أو stake sizing.

> هذه الدورة تثبت قابلية تشغيل خدمة محلية بعقد صارم، ولا تثبت أداء النموذج أو قيمة اقتصادية أو جاهزية تجارية.

## الملفات المنفذة

| الملف | الدور |
|---|---|
| `src/football_prediction_lab/service/contracts.py` | عقود request/response/metrics/error مع `extra=forbid` وUTC وحدود probability |
| `src/football_prediction_lab/service/application.py` | التحقق من provenance وتشغيل Shadow Runner وresponse hash وidempotency وhealth/version |
| `src/football_prediction_lab/service/errors.py` | أخطاء مستقرة وآمنة بلا raw input أو path أو secret |
| `src/football_prediction_lab/service/version.py` | service/code/policy/model/feature versions بلا مسارات |
| `src/football_prediction_lab/service/transport.py` | local adapter لفصل parsing عن application؛ لا HTTP server ولا binding عام |
| `scripts_run_service_smoke.py` | smoke flow محلي يبني manifest من fixture test-only ويصدر response |
| `scripts_validate_service_response.py` | إعادة حساب response hash وفحص الحقول المحظورة وledger chain |
| `tests/test_service_cycle41.py` | اختبارات contract/provenance/timing/security/idempotency |
| `tests/fixtures/cycle41_service/` | fixtures اختبارية للـpre-match والسيناريوهات المرفوضة |

## عقد الخدمة

يطلب `PredictionServiceRequest` صراحة `request_id` و`manifest_fingerprint` و`as_of_utc` وmarket محصوراً في `btts` أو `cards`، إضافة إلى policy/model/feature versions و`expected_source_commit` و`mode=shadow`. تُرفض الحقول الزائدة، والحقول الشبيهة بالمسارات أو الأسرار، وأي mode آخر. لا يحمل الطلب raw features أو CSV أو source URI.

يعيد `PredictionServiceResponse` request metadata وversions وmanifest fingerprint وas_of وpredictions وskipped وoperational metrics و`response_content_sha256` مع `commercial_release=false`. يعاد حساب hash من المحتوى الدلالي فقط؛ `request_id` metadata ولا يغيّر prediction IDs أو probabilities أو response content hash. لا يحتوي response targets أو post-match fields أو financial fields.

## مسار التطبيق والتحقق

يبحث التطبيق عن manifest الذي يطابق fingerprint المطلوب داخل `allowed_manifest_root`، ثم يستدعي `validate_manifest` للتحقق من input/output hashes والـcanonical fingerprint. لا يقبل manifest path من العميل؛ والـpath المستخدم داخلياً يجب أن يبقى تحت root المسموح. يفحص التطبيق policy/model/feature versions وcommit المتوقع قبل تشغيل runner، ويقرأ processed artifact المتحقق فقط.

يمنع preflight إصدار طلب عندما يكون `as_of_utc` بعد kickoff لأي صف في manifest أو عندما تكون probability خارج `[0,1]`. ويمنع runner targets/post-match fields، ويستبعد 2627 وفق الحماية المقفلة، بينما لا يدخل 2526 في tuning أو selection أو calibration. لا يوجد automatic retraining أو label revelation endpoint.

يُستدعى Shadow Runner القائم، فينتج prelabel predictions ويضيفها إلى `ShadowLedger`. ويُشتق `request_fingerprint` من contract الدلالي بعد استبعاد request_id، ويُستخدم run ID حتمي؛ لذلك لا يكرر الطلب المكرر prediction IDs أو ledger records ولا يغير artifact السابق. اختلاف output root لا يدخل response content hash.

## health/version وtransport

الـtransport المحلي مجرد adapter دوال، وليس خادم HTTP. لم تُضف dependency جديدة ولم يُفتح binding. تعيد `health` حالة `not_ready` دون manifest، و`blocked_provenance` عند فشل التحقق، و`healthy` فقط مع manifest verified. أما `version` فيعرض service/code/policy/model/feature versions و`commercial_release=false` دون absolute paths أو secrets. لا توجد endpoints عامة أو authentication تجارية في هذه الدورة؛ boundary العقدي موجود فقط.

## smoke result

استُخدم fixture test-only pre-match مع ثلاثة صفوف وprobabilities مجمدة. عند `as_of_utc=2025-01-01T12:00:00Z` وmarket `btts`:

| المؤشر | النتيجة |
|---|---:|
| manifest verified | نعم |
| predictions في response | 3 |
| ledger records | 6؛ سوقان من Shadow Runner القائم |
| skipped items | 0 |
| `response_content_sha256` | `6bf1dd482e681c1fc0860dc13cb9f2bd1d88979e929433d00c06607eda45676e` |
| response validation | passed |
| ledger chain | passed |
| network calls | none |
| `commercial_release` | `false` |

ملفات smoke موجودة في `reports/generated/cycle_41_service_smoke/`، وتشمل response وservice manifest وhealth/version وingestion manifest وledger وrun artifact وvalidation output. لا تُستخدم هذه الملفات لإثبات performance أو economic value.

## الاختبارات والحماية

تثبت الاختبارات رفض target/result/odds/ROI/EV/stake، ورفض fingerprint أو policy/model/feature mismatch، ورفض as_of بعد kickoff، ورفض path traversal، ورفض probability غير الصالحة، ومنع الوصول إلى source غير verified. كما تثبت ثبات response hash عند اختلاف request_id أو output root، وعدم تكرار ledger، وصحة ledger chain، وبقاء 2627 محجوزاً و`commercial_release=false`.

| الفحص | النتيجة المحلية |
|---|---|
| `python -m pytest -q` | `243 passed` |
| `ruff check .` | `All checks passed` |
| `python -m compileall -q src scripts_*.py` | passed |
| `git diff --check` | passed |
| `scripts_run_service_smoke.py` | passed |
| `scripts_validate_service_response.py` | passed |

## حدود الدورة

لم تُستخدم أي شبكة أو API أو source خارجي. لم تُضف odds أو labels أو targets إلى response، ولم تتغير models أو features أو calibration أو policy 2526/2627 أو نتائج الدورات السابقة. لا يوجد public deployment أو scheduler أو worker أو financial execution. تبقى `commercial_release=false`، وتبقى هذه الخدمة محلية تجريبية prelabel فقط.
