# دورة 46: مصدر البيانات الحي والتشغيل الظل

## الحكم

لم يتوفر في هذا التشغيل مصدر حي موثق ومرخّص مع credentials آمنة مقدمة صراحةً من المستخدم. لذلك سُجلت الحالة الصحيحة `deferred_missing_authorized_source`، مع `verified_snapshots=0` و`shadow_status=deferred` و`commercial_release=false`. لم تُجرَ أي network calls.

## ما نُفذ

أضيف `LocalJsonlSource` كـfile adapter read-only للـfixtures المصرح بها محلياً. يثبت adapter `input_sha256`، و`source_version`، وtimestamps UTC صريحة، ويفرض pre-match kickoff، freshness bound، match/market identity، duplicate handling، schema exactness، وquarantine للأحداث غير الصالحة. تُرتب الصفوف accepted ترتيباً حتمياً، ولا تُخلط مع labels أو targets أو نتائج ما بعد المباراة.

أضيف `scripts_run_cycle46_source_readiness.py` لإنتاج تقرير canonical. عند غياب `--input` لا يفترض وجود مصدر ويصدر deferred مباشرة. عند تمرير fixture محلي، يظل الوضع `local_fixture_only` ولا يتحول إلى verified external source ولا يفتح اتصالاً خارجياً.

## النتيجة الفعلية

| الحقل | القيمة |
|---|---|
| external_source_status | `deferred_missing_authorized_source` |
| verified_snapshots | `0` |
| accepted_rows | `0` |
| quarantined_rows | `0` |
| shadow_status | `deferred` |
| network_calls | `0` |
| commercial_release | `false` |

## الاختبارات والقيود

اختُبرت الصفوف المقبولة والترتيب والح hash، وduplicate match/market، وstale/future observation، وpost-kickoff، وnaive/non-UTC timestamps، وextra fields، وsource-version mismatch، وnaive as-of. نجحت بوابة المستودع عند `326 passed`، مع نجاح Ruff وcompileall وdiff check.

لا تشمل الدورة API حيًا أو provider أو license أو endpoint أو credentials أو shadow period حقيقية. لا توجد نتيجة أداء أو benchmark أو ربحية. 2526 لا تدخل tuning أو selection أو calibration، و2627 محجوز حسب policy.

## الملفات

`src/football_prediction_lab/source/file_adapter.py`، `src/football_prediction_lab/source/__init__.py`، `tests/test_cycle46_file_source.py`، `scripts_run_cycle46_source_readiness.py`، `reports/generated/cycle_46_source_readiness.json`، وهذا التقرير.

تدقيق مستقل: downloader الشبكي الآن يحتاج allow_network=True صراحةً، وLocalJsonlSource يرفض أي as_of غير UTC.
