# دورة 42: واجهة API محلية لطبقة Prediction Service Core

## الحكم والنطاق

تضيف هذه الدورة طبقة نقل HTTP محلية فوق `PredictionApplication`، مع بقاء منطق التنبؤ وطبقة التطبيق والعقود الأساسية كما هي. التنفيذ محصور في دورة 42؛ لا ينتقل إلى Telegram أو worker دائم أو scheduler أو التخزين المستمر، ولا يفتح منفذاً عاماً.

> **قرار الأمان:** الخادم يرفض أي bind خارج loopback، ولا يقبل raw CSV أو source URI أو arbitrary features أو targets أو نتائج أو odds أو حقولاً مالية.

تبقى `commercial_release=false` ثابتة. لا توجد network calls خارج loopback أثناء smoke والاختبارات، ولا تُستخدم odds أو EV أو ROI أو stake sizing، ولا تدخل 2526 في التطوير أو الاختيار أو المعايرة، بينما يبقى 2627 محجوزاً وفق policy المقفلة.

## المسارات

| المسار | الطريقة | السلوك |
|---|---|---|
| `/health` | GET | يعيد `not_ready` أو `healthy` فقط بعد التحقق من تشغيل ذري كامل |
| `/ready` | GET | يعيد `ready` عند health صحي، وإلا `not_ready` |
| `/version` | GET | يعرض service/policy/model/feature/code provenance بلا مسارات محلية |
| `/v1/shadow/predictions` | POST | يقبل `PredictionServiceRequest` فقط ويستدعي طبقة التطبيق في `shadow` |
| `/openapi.json` | GET | snapshot حتمي للعقود والمسارات |

الواجهة تستخدم `LocalServiceAPI` كموزع قابل للاختبار، و`LocalAPIHTTPServer` كخادم loopback اختياري مبني من مكتبة Python القياسية. لا توجد dependency جديدة ولا تشغيل عام. يستطيع المستدعي استخدام `port=0` لاختيار منفذ محلي مؤقت أثناء الاختبار. يوفر `scripts_serve_local_api.py` نقطة تشغيل محلية تتطلب `--allowed-manifest-root` و`--output-root`، وتقبل host loopback فقط. ويستخدم smoke workspace مؤقتاً منفصلاً عن output artifacts ثم يحذفه عند الإنهاء.

## العقود والضوابط

تُعاد الاستفادة من عقود Pydantic الموجودة مع `extra=forbid`؛ لذلك تُرفض الحقول الزائدة قبل الوصول إلى التطبيق، بما في ذلك `target` و`result` و`odds` و`roi` و`ev` و`stake` و`source_uri` و`raw_csv` و`features`. يتحقق التطبيق من manifest وpolicy/model/feature/code provenance ومن توقيت `as_of_utc` قبل تشغيل Shadow Runner، ولا يُقبل `mode` غير `shadow`.

الاستجابة تبقى prelabel وتضم request fingerprint وresponse content hash وoperational metrics فقط. لا يعيد adapter raw exception أو absolute path أو سرّاً. رموز الأخطاء ثابتة: `invalid_request` و`manifest_path_rejected` و`contract_mismatch` و`blocked_provenance` و`payload_too_large` و`unsupported_media_type` و`not_found` و`method_not_allowed`.

يُفرض حد body افتراضي مقداره 64 KiB. ويكتب audit log اختيارياً بصيغة JSONL canonical يحتوي method/path/status و`commercial_release`، ولا يسجل body أو raw features أو secrets أو tokens. الطلبات الدلالية المتطابقة مع `request_id` مختلف تعيد نفس fingerprint وcontent hash، ويترك idempotent replay للحالة التشغيلية التي تنتجها طبقة التطبيق.

## OpenAPI وartifacts

يولد `scripts_write_local_api_openapi.py` snapshot JSON مرتب المفاتيح وبفواصل ثابتة. وينشئ `scripts_run_local_api_smoke.py` تشغيل loopback واحداً ويكتب داخل output root:

| الملف | الغرض |
|---|---|
| `service_request.json` | الطلب canonical |
| `service_response.json` | الاستجابة prelabel |
| `service_manifest.json` | provenance وSHA والعدادات |
| `shadow_ledger.jsonl` | ledger الحقيقي الناتج من runner |
| `validation.json` | نتيجة validator وhashes |
| `audit.jsonl` | سجل تدقيق منقح |

يعاد تشغيل `scripts_validate_service_response.py` على response وledger للتحقق من hash وعدد records وسوقي `btts` و`cards`، ويبقى فرق `response_predictions_count=3` وledger count `6` معلناً صراحةً في metrics.

## الاختبارات

أضيف `tests/test_service_cycle42_local_api.py` لاختبار routes وOpenAPI وHTTP loopback وextra fields وraw/financial/target rejection وpath traversal وversion mismatch وlate timing وmode mismatch وpayload limit وmalformed JSON وaudit safety وidempotency وmissing ledger readiness ورفض non-loopback bind وعدم الاتصال الخارجي. تُشغّل اختبارات دورة 41 و41.1 أيضاً كـregression.

## التشغيل والتحقق

الأمر المحلي:

```bash
python scripts_serve_local_api.py \
  --allowed-manifest-root /path/to/verified/ingestion \
  --output-root /path/to/local/service-output \
  --host 127.0.0.1 --port 8765

python scripts_run_local_api_smoke.py --output-root reports/generated/cycle_42_local_api_smoke
python scripts_write_local_api_openapi.py --output reports/generated/cycle_42_local_api_openapi.json
python scripts_validate_service_response.py \
  --response reports/generated/cycle_42_local_api_smoke/service_response.json \
  --ledger reports/generated/cycle_42_local_api_smoke/shadow_ledger.jsonl
```

يجب أن تكون نتيجة smoke `network_scope=loopback-only` و`commercial_release=false`، ويجب ألا يصبح `/health` صحياً بسبب manifest منفرد أو ledger مفقود. لا يُعتبر نجاح smoke دليلاً على أداء النموذج أو الربحية.

## خارج نطاق الدورة

لا تشمل هذه الدورة Telegram أو أي token أو Chat ID أو إرسال حقيقي، ولا worker 24/7 أو scheduler أو polling أو external ingestion أو public deployment أو database persistence أو monitoring إداري دائم. هذه العناصر مؤجلة إلى دوراتها المخصصة ولا يجوز تنفيذها ضمن Cycle 42.

## الملفات

- `src/football_prediction_lab/service/local_api.py`
- `scripts_run_local_api_smoke.py`
- `scripts_write_local_api_openapi.py`
- `scripts_serve_local_api.py`
- `tests/test_service_cycle42_local_api.py`
- `reports/generated/cycle_42_local_api_smoke/`
- `reports/generated/cycle_42_local_api_openapi.json`

## المراجع الداخلية

المرجع التشغيلي هو `PredictionApplication` وعقود `PredictionServiceRequest` و`PredictionServiceResponse` و`ServiceError` داخل المستودع، مع validator دورة 41.1 بوصفه بوابة سلامة artifacts السابقة. لا يعتمد هذا التقرير على مصدر خارجي أو network.
