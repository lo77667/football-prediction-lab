# تقرير الدورة 32: جاهزية pre-match odds snapshots

**المستودع:** `football-prediction-lab`  
**الدورة:** 32  
**الحالة:** طبقة schema وvalidator والاختبارات مكتملة؛ benchmark اقتصادي حقيقي مؤجل لعدم توفر snapshots موثقة زمنيًا ومرخصة لإعادة الاستخدام  
**القرار:** لا توجد مراهنات أو معاملات مالية أو stake sizing أو توصيات.

## القرار التنفيذي

فحصت الدورة ملفات Football-Data.co.uk المحلية. تحتوي الملفات الخام على أعمدة odds تاريخية مثل `B365H/B365D/B365A` و`AvgH/AvgD/AvgA`، لكن هذه الأعمدة ليست snapshots مستقلة؛ فلا يوجد لكل quote داخل الملف `captured_at` وtimezone و`provenance_id` و`input_sha256` وسياسة ترخيص مرتبطة بالصف. كما أن ملاحظات المصدر تصف الحقول بأنها **pre-closing odds** وتفرق closing odds باللاحقة `C`، لكنها لا توفر في الملفات المحلية سجلًا زمنيًا مستقلًا لكل تغير في السعر [1].

لذلك لم أتعامل مع الأعمدة الخام على أنها بيانات benchmark اقتصادي حقيقية. الناتج المعتمد هو **readiness report** يثبت سبب التأجيل، مع تنفيذ كامل للعقد والـvalidator وfixtures الاختبارية فقط. لا توجد أرقام edge أو EV حقيقية في التقرير الرئيسي، ولم تُستخدم أي بيانات اصطناعية لقياس الأداء.

## نتائج فحص المصدر

| البند | النتيجة |
|---|---|
| المصدر المحلي المرشح | Football-Data.co.uk |
| ملفات المواسم التاريخية المفحوصة | 10 ملفات، مع استبعاد `2526` |
| أعمدة odds-like موجودة | نعم، بصيغة أعمدة تاريخية مجمعة |
| snapshots ذات `captured_at` لكل quote | غير متاحة |
| provenance/hash/license لكل snapshot | غير متاح |
| بيانات قابلة لإدخال benchmark pre-match | صفر |
| حالة benchmark الاقتصادي | مؤجل حتى توفير مصدر مرخص ومؤرخ |
| استخدام closing odds في pre-match benchmark | مرفوض |
| 2526 في اختيار المصدر أو الضبط | لا |

المصدر الرسمي يذكر أن بياناته تتضمن odds تاريخية لعدد من bookmakers، وتوضح صفحة الملاحظات تعريفات pre-closing وclosing [1] [2]. لكن وجود عمود تاريخي لا يكفي لإثبات وقت الالتقاط التشغيلي قبل kickoff؛ لذلك بقيت البيانات خارج طبقة Cycle 32.

## schema وvalidator

أُضيف الملف `src/football_prediction_lab/evaluation/odds_schema.py`. يحتوي `OddsSnapshot` على `snapshot_id` و`match_id` و`match_kickoff_utc` و`market` و`market_definition` و`selection` و`decimal_odds` و`captured_at` و`source_name` و`source_version` و`provenance_id` و`input_sha256` و`odds_type` و`is_licensed_or_reusable` ومعرف bookmaker اختياري.

يرفض العقد السعر الأقل من أو المساوي لـ1، والقيم غير الصالحة، والتوقيت naive، والسجل غير المرخص أو غير القابل لإعادة الاستخدام، وmatch_id غير المعروف، واختلاف kickoff خارج tolerance معلنة، وsnapshot بعد kickoff، وclosing عند استخدام protocol pre-match، وتعريف السوق غير المطابق، وتكرار outcome داخل snapshot. ويمنع `extra="forbid"` إدخال target أو outcome نهائي أو أي حقل غير مصرح به إلى السجل.

## المطابقة الزمنية

تبدأ المطابقة بـ`match_id` ثم تتحقق من تطابق `match_kickoff_utc` المصدر مع kickoff المرجعي ضمن tolerance افتراضية قدرها 60 ثانية. لا توجد مطابقة بالفرق وحدها. بعد ذلك يُطبق protocol معلن: `latest_pre_match` يحتفظ بآخر snapshot قبل kickoff، و`opening` يحتفظ بأول snapshot، مع تسجيل الصفوف التي أُزيلت وسبب الإزالة. لا يُستخدم forward-fill، ولا يمكن للصف اللاحق أن يملأ سعرًا مفقودًا لمباراة أخرى.

ينتج `OddsAuditResult` قائمة accepted وقائمة `discarded_rows` تتضمن سببًا صريحًا، إضافة إلى `raw_snapshots` و`valid_snapshots` وcounts حسب السبب وcoverage حسب الموسم وأول وآخر وقت التقاط وprotocol المستخدم.

## تعريف الاحتمال السوقي

للسوق الثنائي فقط، يحسب النظام الاحتمال الضمني الخام بالعلاقة `1 / decimal_odds`، ثم يحسب overround كمجموع الاحتمالات ويطبّع fair probability بقسمة كل implied probability على المجموع. تُسمى النتيجة داخليًا market-implied benchmark، ولا تُعامل كحقيقة احتمالية أو كتوقع مستقل. إذا لم يكن للسوق نتيجتان مميزتان، ترفض الدالة `remove_binary_overround_from_snapshots` العملية بدل تطبيق تطبيع ثنائي بصمت.

## مقارنة النموذج والـbootstrap

أُضيف `odds_benchmark.py` ليعيد مقارنة وصفية تتضمن model probability وmarket-implied probability وmean raw edge وEV نظريًا بعد عمولة معلنة عند وجود decimal odds. لا يعيد هذا المسار ROI أو cumulative profit أو stake sizing أو أمر تنفيذ.

كما أُضيف `paired_bootstrap_comparison` بفاصل ثقة deterministic وseed ثابت، ويعيد أخذ المباراة كوحدة `match_id` لا selection منفردًا. يدعم فواصل ROC-AUC وAverage Precision وBrier Skill Score وLog-loss Skill Score ومتوسط raw edge، مع إبقاء القيم غير المتاحة `null`. لم تُحسب فواصل اقتصادية حقيقية في هذه الدورة لأن عدد snapshots المؤهلة يساوي صفرًا.

## readiness report وprovenance

أنشأ `scripts_audit_odds_readiness.py` التقرير:

- `reports/generated/cycle_32_odds_readiness.json`
- `reports/generated/manifests/cycle_32_odds_readiness.manifest.json`

ويسجل التقرير صراحة أن عدد standardized snapshots يساوي صفرًا، وأن أرقام edge/EV الحقيقية مؤجلة. ويضم manifest SHA-256 مركبًا للملفات الخام المفحوصة، وعدد الملفات، والنطاق الزمني الفارغ للـsnapshots، ونسخة طبقة readiness.

## مراجعة التسرب والأدوار الستة

| الشخصية | قرار المراجعة |
|---|---|
| المنفذ | أنشأ schema وvalidator وaudit protocol وbootstrap والاختبارات دون إدخال بيانات odds غير موثقة. |
| المدقق | اختبر kickoff قبل/بعد snapshot، mismatch، duplicate outcome، closing isolation، overround الثنائي، provenance، وextra fields. |
| المراجع | راجع مصدر Football-Data والحقول المحلية، ورفض اعتبار الأعمدة التاريخية snapshots زمنية. |
| الباحث | حفظ ملاحظات المصدر الرسمية، وميز بين pre-closing وclosing دون ادعاء توفر capture timestamps. |
| المطور | فصل طبقة odds عن النموذج، وأبقى المقارنة descriptive-only وقابلة للتوسعة عند توفير snapshots قانونية. |
| الضامن | تحقق من استبعاد 2526، وعدم وجود forward-fill أو bookmaker selection بعد النتيجة، وحتمية bootstrap. |

## الاختبارات والحالة التشغيلية

| الفحص | النتيجة |
|---|---|
| اختبارات المشروع الكاملة | 85 اختبارًا ناجحًا |
| اختبارات Cycle 32 الجديدة | ناجحة |
| Ruff | ناجح |
| `python -m compileall -q src scripts_*.py` | ناجح |
| `git diff --check` | ناجح |
| صفوف 2526 في readiness التاريخي | مستبعدة |
| بيانات odds حقيقية مؤهلة | 0 |
| تنفيذ مالي أو توصية | غير موجود |

حالة CI البعيد لا تُعلن ناجحة إلا بعد تشغيل فعلي. في آخر دورة منشورة كان GitHub Actions قد فشل على runner سريع مع `steps: []` ومن دون سجل تنفيذ؛ ستُحدّث الحالة بعد رفع Cycle 32 والتحقق من التشغيل الجديد. الفحوص المحلية أعلاه ناجحة ولا تعادل نجاح CI البعيد.

## الملفات الجديدة

| الملف | الغرض |
|---|---|
| `src/football_prediction_lab/evaluation/odds_schema.py` | عقد snapshot والمطابقة والتدقيق وإزالة overround الثنائية |
| `src/football_prediction_lab/evaluation/odds_benchmark.py` | مقارنة descriptive-only وpaired bootstrap |
| `tests/test_odds_evaluation.py` | اختبارات schema والزمن والـduplicates والـbootstrap |
| `scripts_audit_odds_readiness.py` | تقرير توفر البيانات دون اعتماد odds الخام |
| `docs/cycle_32_source_findings.md` | نتائج البحث المحلي والرسمي في المصدر |
| `reports/generated/cycle_32_odds_readiness.json` | نتيجة readiness المولدة |
| `reports/generated/manifests/cycle_32_odds_readiness.manifest.json` | manifest وبصمة المدخلات |

## المراجع

[1]: https://www.football-data.co.uk/data.php "Football-Data.co.uk historical football results and betting odds data"

[2]: https://www.football-data.co.uk/notes.txt "Football-Data.co.uk notes and odds field definitions"

[3]: https://www.football-data.co.uk/disclaimer.php "Football-Data.co.uk disclaimer"
