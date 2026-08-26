# دورة 44: Worker محلي قابل للاستعادة

## الحكم والنطاق

تضيف هذه الدورة نواة worker محلية قابلة للتشغيل المحدود والاستعادة بعد الانقطاع. التنفيذ callback-driven ويعمل على fixtures محلية في `dry-run` أو `shadow` أو `telegram-disabled`. لا يوجد مصدر حي، ولا polling خارجي، ولا إرسال Telegram حقيقي، ولا scheduler مُدار، ولا نشر عام. وجود حلقة `run_forever` في الكود لا يعني أن النظام أصبح خدمة 24/7 مستضافة فعلياً.

> **قرار السلامة:** worker لا يقرأ targets أو results، ولا يعيد تدريب النموذج تلقائياً، ولا يفتح اتصالاً خارجياً من تلقاء نفسه. أي callback خارجي يحتاج حقناً صريحاً واختبارات واعتماداً منفصلاً.

تبقى `commercial_release=false`. لا تُستخدم odds أو EV أو ROI أو stake sizing، ولا تدخل 2526 في التطوير أو الاختيار أو المعايرة، بينما يبقى 2627 محجوزاً وفق policy الحالية.

## دورة التشغيل

يستقبل worker `EventSource` يعيد أحداثاً normalized، و`Predictor` يعيد `WorkerPrediction` prelabel، و`Notifier` اختيارياً. لكل تشغيل `as_of_utc` واعٍ بالمنطقة الزمنية. يرفض worker الحدث المتأخر أو stale data أو prediction بعد kickoff، ويصنف no-data وpartial-data صراحةً.

تُحفظ الحالة في JSON canonical يُستبدل ذرّياً، ويُحفظ operational event log append-only. تشمل الحالة iteration وheartbeat وcurrent event/phase وprocessed event keys وprediction keys وnotification keys وretry queue وdead-letter counters وcircuit state وrestart recoveries. ويمنع `FileLock` تشغيل نسختين على نفس state root.

## الاستعادة والتكرار

قبل بدء cycle، إذا بقي `current_event_key` بسبب crash، يسجل worker `startup_recovery` ويعيد الحدث إلى retry queue، ثم يعيد تشغيله عبر المصدر المحلي. بعد prediction وnotification الناجحين تُحفظ event key وprediction key، وتُتخطى إعادة المعالجة. وعند فشل notification تبقى event key في retry queue أو dead-letter حسب السياسة، ولا تُعلّم processed قبل نجاح الإرسال.

يدعم worker graceful shutdown عبر `request_stop`، و`run_forever(max_iterations=...)` لحدود اختبارية واضحة. كل callback يعمل داخل timeout محدود؛ failures المتكررة تفتح circuit breaker مؤقتاً للمصدر أو notifier. توجد backoff محدودة للمحاولات، وheartbeat لكل iteration.

## الأوضاع

| الوضع | المصدر | prediction | notification |
|---|---|---|---|
| `dry-run` | local callback | prelabel | يسجل dry-run فقط |
| `shadow` | local أو callback مصرح | prelabel | يحتاج notifier محقوناً ومختبراً |
| `telegram-disabled` | local أو callback مصرح | prelabel | يسجل skip ولا يستدعي Telegram |

CLI `scripts_run_worker.py` يستخدم fixture محلياً ويقبل `--iterations` و`--as-of-utc`، ولا يثبت استضافة دائمة. Smoke `scripts_run_worker_smoke.py` ينتج سيناريوهات dry-run وdedup وtelegram-disabled وno-data وshadow، مع state وevent logs فقط.

## الاختبارات

يختبر `tests/test_cycle44_worker.py` completed وdedup وtelegram-disabled وshadow notifier failure وretry/dead-letter وstale/late/no-data/partial-data وsource timeout وsource circuit breaker وprediction timeout وstartup recovery وcrash marker وlock contention وrun bound وgraceful shutdown وtimezone-aware contracts وcanonical state وعدم وجود الحقول المحظورة.

## التشغيل والأدلة

```bash
python scripts_run_worker.py --mode=dry-run --iterations=2
python scripts_run_worker.py --mode=shadow --iterations=1
python scripts_run_worker.py --mode=telegram-disabled --iterations=1
python scripts_run_worker_smoke.py \
  --output-root reports/generated/cycle_44_worker_smoke
```

يجب أن تكون نتيجة smoke `validation=passed` و`network_scope=none`، ويجب ألا تحتوي state أو event logs targets أو results أو odds أو EV أو ROI أو stake أو raw data أو secrets.

## ملفات الدورة

- `src/football_prediction_lab/worker/core.py`
- `src/football_prediction_lab/worker/__init__.py`
- `scripts_run_worker.py`
- `scripts_run_worker_smoke.py`
- `tests/test_cycle44_worker.py`
- `reports/generated/cycle_44_worker_smoke/`

## خارج النطاق

لا تشمل الدورة مصدر بيانات حي، Telegram حقيقياً، webhook، scheduler خارجي، process supervisor، database persistence، monitoring service، أو استضافة 24/7. هذه العناصر لا تُعتبر منفذة بمجرد وجود worker loop محلي.
