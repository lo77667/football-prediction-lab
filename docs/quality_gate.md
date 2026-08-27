# بوابة الجودة المحلية

هذه البوابة تتحقق من سلامة المصدر والعقود وإعادة التشغيل محلياً. نجاحها لا يثبت الربحية أو `ROI` أو `EV` أو صلاحية تشغيل تجاري، ولا يفتح `commercial_release` الذي يبقى `false`.

## الأوامر الإلزامية

شغّل الأوامر التالية من جذر checkout الحالي داخل البيئة النظيفة المعتمدة:

```bash
pytest -q
ruff check .
python -m compileall -q src scripts
git diff --check
```

يجب أن تعرض بوابة الاختبار تنفيذ `pytest` فعلياً، ويجب ألا تستخدم `continue-on-error: true` لإخفاء الفشل. في هذه الشجرة كانت النتيجة المحلية الأخيرة `370 passed`، ونجح Ruff وcompileall و`git diff --check`. هذا العدد نقطة تحقق زمنية ويجب توليد أي عدد جديد عبر `scripts/ops/scripts_test_summary.py`.

## حواجز إلزامية

| الحاجز | معيار القبول |
|---|---|
| الاستيراد | تشير `football_prediction_lab.__file__` إلى `src/` في checkout الحالي |
| الاختبارات | نجاح `pytest -q` مع عداد فعلي قابل للتدقيق |
| التنسيق | نجاح `ruff check .` بلا أخطاء مخفية |
| الترجمة | نجاح `python -m compileall -q src scripts` |
| الفروق | نجاح `git diff --check` |
| الزمن | لا تستخدم features أو targets أو post-match fields قبل وقت الإصدار |
| المواسم | `2526` خارج التطوير/الاختيار/المعايرة، و`2627` محجوز وغير مقيم |
| العقود | لا تغيير في `TARGET_COLUMNS` أو `POST_MATCH_AUDIT_COLUMNS` دون موافقة موثقة |
| النشر | لا push أو deploy أو ربط بمنصة Manus ضمن هذه الدورة |
| الإصدار | `commercial_release=false` ثابت |

## فحوص smoke المساندة

يمكن تشغيل فحصي التحقق من المسارات المنظمة كما يلي:

```bash
python scripts/quality/verify_cycle36_reproducibility.py
python scripts/quality/verify_cycle37_workflow.py
```

يفحص الأول الاختبارات وRuff وcompileall وسجل العدادات، ويفحص الثاني أن workflow يحتوي job وخطوات تنفيذ فعلية. لا يساوي نجاح الفحصين نجاح تشغيل بعيد؛ حالة GitHub Actions لا تُعلن إلا من سجل فعلي قابل للتحقق على آخر commit، وهو خارج التنفيذ المحلي الحالي.

## نطاق مجمد

Android، ومستودع اللاعبات اليافعات، وPower BI، وdrift، والأسواق غير BTTS، والمصدر الخارجي الحي، وTelegram الحقيقي، وeconomic benchmark كلها مجمدة أو مؤجلة وفق `FREEZE_NOTICE.md`. لا تُضاف تغييرات سلوكية أو tuning أثناء إعادة التنظيم.
