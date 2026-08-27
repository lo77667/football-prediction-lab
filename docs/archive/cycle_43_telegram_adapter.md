# دورة 43: Telegram Adapter آمن ومنع التكرار

## الحكم والنطاق

تضيف هذه الدورة طبقة إشعارات منفصلة عن منطق التنبؤ. لا تتصل الطبقة بشبكة Telegram، ولا تستخدم Bot Token أو Chat ID حقيقياً، ولا ترسل رسالة خارجية. الوضع الافتراضي `dry_run`، ووضع `test` لا يعمل إلا مع `FakeTelegramClient` محقون، بينما `production` مرفوض صراحةً.

> **قرار الأمان:** لا يمكن اعتبار نجاح fake client دليلاً على نجاح Telegram الحقيقي، ولا توجد في هذه الدورة أي موافقة على إرسال خارجي.

تبقى `commercial_release=false`، ولا توجد odds أو EV أو ROI أو stake sizing أو targets أو results أو raw features. لم تدخل 2526 في التطوير أو الاختيار أو المعايرة، ويبقى 2627 محجوزاً وفق policy المقفلة.

## عقد الرسالة

يعتمد adapter على `NotificationSignal` ذي `extra=forbid`، ويضم السوق، match ID، kickoff UTC، probability، model version، policy version، issued time، وdisclaimer معلوماتياً. تُحوّل الإشارة إلى `TelegramMessage` ذي `extra=forbid` و`MarkdownV2`، مع escaping للنصوص وحد أقصى 4096 حرفاً.

تُرفض الحقول أو المصطلحات التي تشير إلى target أو result أو odds أو ROI أو EV أو stake أو raw CSV أو source URI أو مفاتيح الأسرار. الرسالة تذكر صراحةً أنها pre-match ومعلوماتية وغير مضمونة وليست توصية مالية.

يُشتق `notification_id` من تمثيل JSON canonical يشمل Chat ID وعناصر الإشارة الدلالية. لذلك يظل ثابتاً عند إعادة المحاولة أو إعادة التشغيل أو تغيير request ID غير الموجود في العقد، وتُتخطى الإشعارات التي سبق تسجيلها بحالة `sent` أو `dry_run`.

## السياسة وطرق التشغيل

| الوضع | السلوك | النقل المسموح |
|---|---|---|
| `dry_run` | يسجل event واحداً ولا يستدعي client | لا شبكة |
| `test` | يستخدم fake client محقوناً فقط | لا شبكة |
| `production` | يرفع `ProductionDisabledError` | محظور في دورة 43 |

لا يسمح `NotificationPolicy` بالإرسال إلا عندما تكون `enabled=true` والسوق ضمن القائمة المسموحة، ولا يسمح production حتى لو مرر المستدعي إعداداً مخالفاً. لا يوجد token أو authorization header في configuration أو logs أو fixtures.

## Ledger منفصل وretry

`NotificationLedger` ملف append-only مستقل عن prediction ledger. يسجل notification ID، status، attempt، error code، retryable، message ID الآمن، و`commercial_release`، ولا يسجل نص الرسالة أو raw data أو Bot Token أو Authorization.

الأخطاء القابلة لإعادة المحاولة، مثل 429 و5xx في fake client، تستخدم exponential backoff محدوداً وعدداً أقصى للمحاولات. الأخطاء الدائمة تنتقل مباشرةً إلى `dead_letter`. عند استنفاد المحاولات يسجل adapter الحالة النهائية ولا يستمر بلا حدود. الاستثناءات غير المتوقعة تُحوّل إلى error code آمن بلا traceback أو raw input.

## الاختبارات وsmoke

أضيف `tests/test_cycle43_telegram_adapter.py` لاختبار dry-run وtest fake client وdedup وnotification ID وretry/backoff و429/5xx وdead-letter وmessage length وMarkdown escaping وforbidden fields وmissing chat ID وproduction-disabled وledger filtering وprelabel conversion.

وينشئ `scripts_run_telegram_adapter_smoke.py` الأدلة التالية دون network:

| الملف | الغرض |
|---|---|
| `message_contract.json` | schema canonical لعقد الإشارة والرسالة |
| `notification_ledger_dry_run.jsonl` | dry-run event وسجل duplicate |
| `notification_ledger_test.jsonl` | retry ثم fake send |
| `validation.json` | نتيجة dry-run/retry/production block |
| `smoke_summary.json` | فهرس الأدلة وnotification ID |

أثبت smoke فعلياً: `dry_run`، و`duplicate_skipped`، و`sent` بعد محاولتين، و`production_blocked=true`، و`network_scope=none`.

## التشغيل

```bash
python scripts_run_telegram_adapter_smoke.py \
  --output-root reports/generated/cycle_43_telegram_smoke
```

يظل التشغيل الحقيقي محظوراً. إذا احتاجت دورة لاحقة إلى token أو Chat ID حقيقي، يجب حفظهما خارج Git والـcommand line والـlogs، ثم طلب تأكيد صريح قبل أي إرسال مع عرض recipient وmessage sample.

## الأدلة النهائية

| الفحص | النتيجة الحالية |
|---|---|
| regression المستهدف | `69 passed` |
| full pytest | `297 passed` |
| adapter source commit | `acf0649a924096a3953f96ec7fe66500f6e9b649` |
| Ruff | passed |
| compileall | passed |
| git diff check | passed |
| fake/dry-run smoke | passed |
| network scope | none |
| production mode | blocked by default |
| commercial release | `false` |

أُعيد تشغيل الاختبار الكامل بعد تثبيت المصدر: `297 passed`. لا يُعد fake client أو smoke المحلي دليلاً على وصول رسالة إلى Telegram أو على صلاحية تشغيل تجاري.

## خارج النطاق

لا تشمل هذه الدورة إنشاء worker أو scheduler أو polling أو webhook أو Telegram token أو Chat ID حقيقياً أو إرسالاً خارجياً أو database persistence أو public deployment. هذه العناصر لا تُنفذ ضمن Cycle 43.
