# دورة 45: التخزين التشغيلي والنسخ والاستعادة

أضيفت طبقة SQLite محلية مستقلة في `storage/sqlite_store.py` لحفظ ingestion runs وsource manifests وpredictions وshadow runs وnotifications وnotification attempts وfailures وhealth snapshots وmodel-policy versions وaudit events. تستخدم القاعدة schema migration معلنة، وقيود uniqueness لمنع التكرار، وفحوص probability، ومعاملات صريحة مع rollback عند الفشل.

تُكتب audit payloads بصيغة JSON canonical، وتُرفض الحقول الحساسة أو التشغيلية المحظورة، بما فيها token وauthorization وsecret وraw_data وtarget وresult وodds وROI وEV وstake، حتى داخل بنى متداخلة. لا تحفظ القاعدة نصوص Telegram أو أسراراً أو labels.

يدعم `SQLiteStore.backup_to` نسخاً عبر SQLite backup API إلى ملف مؤقت ثم استبداله ذرياً، مع integrity check قبل وبعد النسخ. ويدعم `restore_from` التحقق من النسخة في مسار مؤقت قبل استبدال الوجهة، لذلك لا تستبدل نسخة سليمة بملف تالف. أضيفت أداتا `scripts_backup_sqlite.py` و`scripts_restore_sqlite.py` للاستخدام المحلي فقط.

| الفحص | النتيجة |
|---|---|
| الاختبارات الكاملة | `320 passed` |
| Ruff | passed |
| compileall | passed |
| diff check | passed |
| integrity check | `PRAGMA integrity_check` وforeign-key check |
| backup/restore | اختبارات نجاح وملف تالف واستبدال ذري |
| secrets/labels | مرفوضة في audit payloads |
| network | none |
| commercial release | `false` |

لا تشمل الدورة قاعدة بيانات مُدارة أو مزامنة خارجية أو cloud backup أو scheduler أو monitoring service أو Telegram حقيقياً. بقيت 2526 خارج التطوير و2627 محجوزاً وفق السياسة، ولم تتغير النماذج أو الميزات أو نتائج الدورات السابقة.

## الملفات

`src/football_prediction_lab/storage/sqlite_store.py`، و`src/football_prediction_lab/storage/__init__.py`، و`scripts_backup_sqlite.py`، و`scripts_restore_sqlite.py`، و`tests/test_cycle45_storage.py`.
