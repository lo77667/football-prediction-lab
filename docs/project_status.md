# حالة المشروع الحالية

**آخر تحديث:** بعد commit إعادة تنظيم السكربتات محلياً.
**الوضع:** بحثي ومحلي فقط، و`commercial_release=false`.

## الخلاصة

المشروع مختبر لتقييم توقعات كرة القدم، مع أولوية لمسار **BTTS** ومنع استخدام نتائج المباراة قبل وقت الإصدار. لا ينفذ المشروع مراهنات أو معاملات مالية، ولا يحتوي هذا الإصدار على odds حية أو `EV` أو `ROI` أو `stake sizing` أو قناة Telegram إنتاجية.

## ما أُنجز

نُظمت السكربتات تحت `scripts/ingestion/` و`scripts/features/` و`scripts/evaluation/` و`scripts/walk_forward/` و`scripts/shadow/` و`scripts/ops/` و`scripts/quality/`، مع تحديث الاختبارات ومراجع التشغيل. لم يُحذف أي سكربت ولم يُدمج سلوكياً؛ النقل كان تنظيمياً فقط.

أُنشئ [`RESEARCH_LOG.md`](RESEARCH_LOG.md) لتجميع القرارات والأرقام الموثقة، ونُقلت التفاصيل التاريخية إلى [`archive/`](archive/). يبقى `FREEZE_NOTICE.md` المرجع الحاكم لنطاق التجميد، وتبقى `consolidation_plan.md` مرجعاً لقرارات عدم الحذف أو الدمج.

## التحقق المحلي الأخير

شُغّلت الفحوص من جذر checkout الحالي باستخدام البيئة النظيفة `/tmp/cycle37-clean-venv`:

| الفحص | النتيجة |
|---|---|
| `pytest -q` | `370 passed` |
| `ruff check .` | `All checks passed!` |
| `python -m compileall -q src scripts` | ناجح |
| `git diff --check` | ناجح |
| `verify_cycle36_reproducibility.py` | `cycle36_reproducibility=passed` |
| `verify_cycle37_workflow.py` | `cycle37_workflow_static_check=passed` |

العدد أعلاه ناتج عن التنفيذ المحلي الحالي. يجب توليد أي عدد لاحقاً عبر `scripts/ops/scripts_test_summary.py` بدلاً من نسخه يدوياً إلى وثيقة.

## الحواجز والسياسات

يبقى `2526` خارج التطوير والاختيار والمعايرة، ويبقى `2627` محجوزاً كـfuture holdout غير مقيم. لا تُعدّل `TARGET_COLUMNS` أو `POST_MATCH_AUDIT_COLUMNS` أو حواجز temporal leakage دون موافقة موثقة. لا يتحول المسار إلى مصدر حي أو إطلاق مغلق أو خدمة تجارية بسبب نجاح اختبارات محلية فقط.

## ما هو مؤجل

المصدر الخارجي المرخص، وshadow period الحقيقية، والتشغيل الدائم الخارجي، والمراقبة الخارجية، وإدارة الأسرار، والإرسال الحقيقي، وأي benchmark اقتصادي كلها خارج هذه الدورة أو مؤجلة حتى تتوفر متطلبات مستقلة قابلة للتحقق. كما جُمّدت مسارات Android، ومستودع اللاعبات اليافعات، وPower BI، وdrift، والأسواق غير BTTS وفق `FREEZE_NOTICE.md`.

## طريقة القراءة

ابدأ بـ`FREEZE_NOTICE.md` ثم `RESEARCH_LOG.md`. راجع artifacts تحت `reports/generated/` والاختبارات تحت `tests/` عند الحاجة إلى دليل قابل للتدقيق. لا تُعامل الوثائق المؤرشفة أو smoke fixtures كدليل على الربحية أو الصلاحية التجارية.
