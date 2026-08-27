# سجل البحث والقرارات

**المشروع:** `football-prediction-lab`  
**النطاق الحالي:** مختبر محلي، shadow-only، مع تركيز BTTS.  
**قاعدة ثابتة:** `commercial_release=false`، ولا تُعد أرقام الاختبارات أو smoke أو المقاييس الوصفية دليلاً على الربحية أو `ROI` أو `EV`.

هذا السجل يلخص النتائج الرقمية التي ظهرت في تقارير الدورات أو في التحقق المحلي الحالي. أما التفاصيل الكاملة، والجداول per-fold، والـartifacts، فتوجد في `docs/archive/` و`reports/generated/`. لا يُعاد تفسير نتيجة تاريخية عند نقلها إلى الأرشيف؛ ويُستخدم الرمز `غير مذكور` عندما لا يقدم التقرير المصدر رقماً قابلاً للتدقيق.

| الدورة | القرار | النتيجة الرقمية الموثقة | الحالة |
|---|---|---|---|
| 32 | تأجيل economic benchmark وعدم تحويل odds-like columns إلى snapshots | `94` عموداً تاريخياً شبيهاً بـodds؛ raw snapshots=`0`، standardized=`0`، discarded=`0` | مرفوض للاعتماد التجاري / مؤجل |
| 33 | قبول المقارنة كبحث داخلي فقط، ورفض اعتماد تجاري | `8` طيات لكل سوق، `3040` صف اختبار لكل variant، و`400` bootstrap؛ BTTS `platt_expanded`: Brier=`0.249480` مقابل baseline=`0.249859` | مقبول داخلياً؛ التجاري مرفوض |
| 34 | اعتماد nested walk-forward لمنع selection-on-outer-test | `8` طيات لكل سوق، `3040` صف outer-test لكل سوق، و`400` bootstrap؛ BTTS Brier=`0.249942` وLog Loss=`0.693107` | مقبول منهجياً؛ التجاري مرفوض |
| 35 | تثبيت policy قبل holdout، دون استخدام 2526 في الاختيار | `760` prediction prelabel؛ `380` لكل سوق؛ `evaluation_runs=1`؛ Brier BTTS=`0.247713` وcards=`0.256355` | تقييم وصفي؛ commercial release مرفوض |
| 36.1 | إيقاف الاعتماد حتى إصلاح قابلية التشغيل وفحص Ruff | `0` تغيير في النموذج أو الميزات؛ blocker تشغيلي واحد معلن: قابلية التثبيت/Ruff | مؤجل |
| 36.2 | قبول Full Reproducible Source Bundle بعد تحقق venv نظيفة | `268` ملفاً متتبعاً في Git و`268` ملفاً في الأرشيف؛ snapshot التحقق سجل `174 collected / 174 passed` | مقبول لإعادة الإنتاج؛ ليس تجارياً |
| 37 | إصلاح workflow وبناء quality gate قابل للرؤية، دون ادعاء نجاح CI عن بعد | محلياً: `1` job و`9` steps في الفحص الثابت؛ التحقق الحالي: `370 passed` | مقبول محلياً؛ حالة CI البعيدة غير معلنة |
| 38 | اعتماد عقد ingestion المحلي ورفض المصدر الخارجي غير الموثق | fixture: `3` rows read، `3` accepted، `0` quarantined؛ التقرير التاريخي: `186 passed` | مقبول للاختبار المحلي فقط |
| 39 | اعتماد shadow mode الحتمي المحلي فقط | `3` rows seen، `6` predictions issued، `0` skipped، و`0` اتصال خارجي | مقبول كـshadow-only |
| 40 | فصل canonical report عن runtime paths وتأجيل المصدر الخارجي | `source_count=0`؛ لا مصدر خارجي موثق في التشغيل؛ لا network call | مؤجل |
| 41.1 | فحص سلامة artifacts وخدمة محلية دون فتح إصدار | `0` قناة Telegram حقيقية و`0` ادعاء أداء تجاري؛ تفاصيل الاختبار محفوظة في التقرير المؤرشف | مقبول للتشغيل المحلي فقط |
| 42 | اعتماد loopback API smoke فقط | `275 passed`؛ ledger=`6` records؛ الأسواق المفحوصة=`2` (`btts/cards`) | مقبول محلياً؛ لا نشر |
| 43 | اعتماد Telegram adapter الجاف فقط | `297 passed`؛ حالات smoke المعلنة=`4`؛ `production_blocked=true` | مقبول للاختبار؛ الإرسال الحقيقي مرفوض |
| 44 | اعتماد worker المحلي مع عدم تشغيل دائم خارجي | `312 passed`؛ worker smoke=`validation=passed` | مقبول محلياً؛ ليس خدمة إنتاج |
| 45 | اعتماد التخزين المحلي والنسخ/الاستعادة كطبقة اختبار | `320 passed` | مقبول محلياً؛ لا backup سحابي أو scheduler خارجي |
| 46 | تأجيل مصدر حي وshadow period حقيقية بسبب غياب مصدر مرخص وcredentials مقدمة صراحة | `verified_snapshots=0`، `shadow_status=deferred`، `326 passed`، و`0` network calls | مؤجل |
| 47 | منع closed beta والإطلاق العام حتى اكتمال provenance والجودة والعمليات والموافقة | `0` إطلاق عام، `0` إرسال Telegram حقيقي، `production_enabled=false`، `recipients=[]` | محجوب؛ commercial release مرفوض |

## الضوابط غير القابلة للتفاوض

يبقى الموسم `2526` خارج التطوير والاختيار والمعايرة، ويبقى `2627` محجوزاً كـfuture holdout غير مقيم. لا تُعدّل عقود `TARGET_COLUMNS` أو `POST_MATCH_AUDIT_COLUMNS` ولا حواجز `temporal leakage` ضمن إعادة التنظيم. لا توجد odds حية، ولا `EV` أو `ROI` أو `stake sizing` أو نشاط تجاري في هذا الإصدار.

أُعيد توليد عداد الاختبارات الحالي من التنفيذ المحلي بعد إعادة التنظيم: **370 collected / 370 passed**. هذا العدد نقطة تحقق لهذه الشجرة، وليس رقماً ثابتاً يُنسخ إلى تقارير مستقبلية؛ المرجع التنفيذي هو `scripts/ops/scripts_test_summary.py` وartifact الناتج في `reports/generated/`.

## المراجع

[1]: archive/cycle_32_odds_readiness.md "Cycle 32 odds readiness"
[2]: archive/cycle_33_walk_forward_model_comparison.md "Cycle 33 walk-forward comparison"
[3]: archive/cycle_34_nested_walk_forward.md "Cycle 34 nested walk-forward"
[4]: archive/cycle_35_final_holdout_2526.md "Cycle 35 final holdout"
[5]: archive/cycle_36_2_reproducibility.md "Cycle 36.2 reproducibility"
[6]: archive/cycle_38_ingestion_run.md "Cycle 38 ingestion run"
[7]: archive/cycle_39_shadow_mode.md "Cycle 39 shadow mode"
[8]: archive/cycle_46_live_source_shadow_period.md "Cycle 46 live source shadow period"
[9]: archive/cycle_47_closed_beta_release_gate.md "Cycle 47 closed beta release gate"
