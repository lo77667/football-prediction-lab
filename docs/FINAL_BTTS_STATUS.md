# الحالة النهائية لمسار BTTS

**الحالة:** تقييم بحثي وصفي مكتمل محلياً، وليس اعتماداً تجارياً.  
**القرار:** `commercial_release=false` و`economic_benchmark=deferred`.

## نطاق التقييم

أُجري التقييم على artifact المحلي `data/processed/epl_1516_2425_features.csv` للمواسم `1516` إلى `2425` فقط. استخدم البروتوكول ثماني طيات زمنية؛ في كل طية دُرّب النموذج على المواسم الأقدم، واستُخدم موسم سابق واحد للمعايرة، ثم جرى الاختبار على الموسم التالي. لم يُستخدم `2526` في التطوير أو الاختيار أو المعايرة، ولم يُقيّم `2627`.

النموذج هو `BttsLogisticBaseline` مع `SELECTED_FEATURES` الموجودة مسبقاً، ولم تُجرَ إعادة tuning أو إضافة ميزات. طُبقت معايرة Platt على موسم المعايرة السابق مباشرة، ثم قورنت الاحتمالات قبل وبعد المعايرة بخط أساس ثابت محسوب من train-plus-calibration.

## النتائج المجمعة

| الحالة | الطيات | صفوف الاختبار | Brier mean | Log Loss mean | ECE(10) mean |
|---|---:|---:|---:|---:|---:|
| baseline ثابت train-plus-calibration | 8 | 3040 | 0.249600 | 0.692348 | 0.029477 |
| selected features قبل Platt | 8 | 3040 | 0.255588 | 0.705270 | 0.072393 |
| selected features بعد Platt | 8 | 3040 | 0.249448 | 0.692056 | 0.034173 |

بعد Platt كان الفرق المتوسط عن baseline هو `-0.000152` في Brier و`-0.000292` في Log Loss. هذه فروق وصفية صغيرة؛ ولا تكفي وحدها لإثبات تفوق مستقر أو صلاحية تشغيلية.

## عدم اليقين

استُخدم paired bootstrap على طيات الاختبار، مع `2000` إعادة وبذرة ثابتة `4201`. عُرّف الفرق بأنه Platt-calibrated selected features ناقص baseline؛ لذلك تشير القيم السالبة إلى تحسن عددي في المقياس، لكن فاصل الثقة الذي يعبر الصفر يجعل النتيجة غير حاسمة.

| المقياس | الفرق المتوسط | فاصل الثقة 95% |
|---|---:|---:|
| Brier | -0.000146 | [-0.001455, 0.001247] |
| Log Loss | -0.000279 | [-0.002948, 0.002565] |

## القيود والقرار

لا يحتوي هذا التقييم على odds حية أو benchmark اقتصادي أو `EV` أو `ROI` أو stake sizing. لا توجد منه توصية مراهنة أو ادعاء ربحية. نجاح الاختبارات، وتحسن المقاييس بعد Platt في هذه العينة، وفواصل bootstrap الوصفية لا تفتح الإصدار التجاري. يبقى المسار shadow-only، ويظل المصدر الخارجي المرخص وshadow period الحقيقية والتشغيل الدائم والمراقبة المستقلة متطلبات مؤجلة.

تحافظ الشجرة على `TARGET_COLUMNS` و`POST_MATCH_AUDIT_COLUMNS` وحواجز temporal leakage. كما تبقى سياسة `2526` خارج التطوير والتقييم، و`2627` محجوزاً، و`commercial_release=false` ثابتاً.

## provenance وإعادة التدقيق

| العنصر | القيمة |
|---|---|
| التقرير canonical | `reports/generated/btts_final_evaluation.json` |
| input artifact | `data/processed/epl_1516_2425_features.csv` |
| input SHA-256 | `ebaec5d28231129a4a88bcd810a3e227c7b0c0d2c66239bb209c27c52eff490e` |
| source commit وقت التوليد | `83ab3b809bbe47853cf5687abafa0387de4a69de` |
| schema | `btts-final-evaluation-v1` |
| المعايرة | Platt sigmoid على موسم المعايرة السابق مباشرة |
| الحالة التجارية | `rejected` |

لإعادة التدقيق محلياً، شغّل مولد التقييم المكافئ على نفس input وبنفس بروتوكول الطيات والبذرة، ثم قارن الحقول الرقمية وقيود المواسم والـprovenance. لا يُعاد تشغيل أي مصدر شبكة؛ التقرير مبني على البيانات المحلية الموجودة فقط.

## المراجع الداخلية

[1]: ../reports/generated/btts_final_evaluation.json "Canonical BTTS final evaluation"
[2]: RESEARCH_LOG.md "Research and decision log"
[3]: FREEZE_NOTICE.md "Scope freeze notice"
