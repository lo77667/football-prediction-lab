# تفعيل مصادر كرة القدم الأربعة

أضيفت المحولات الأربعة التي ظهرت في مراجعة `public-apis/public-apis`: `OpenLigaDB` و`SportScore` و`football-data.org` و`TheSportsDB`. التفعيل الحالي هو **تفعيل محلي للمحولات والـregistry**، وليس فتحاً تلقائياً للشبكة أو اعتماداً تجارياً للمصدر.

## الحالة الحالية

| المصدر | الحالة المحلية | الاعتماد | الشبكة الافتراضية | الاستخدام المقترح |
|---|---|---|---|---|
| OpenLigaDB | مفعّل في registry | لا يحتاج مفتاحاً | مغلقة | fixtures ونتائج الدوريات |
| SportScore | مفعّل في registry | لا يحتاج مفتاحاً للطبقة المعلنة مع الإسناد | مغلقة | fixtures ونتائج وتفاصيل وstandings ضمن shadow |
| football-data.org | مفعّل في registry | `FOOTBALL_DATA_API_TOKEN` عند التشغيل | مغلقة | fixtures ونتائج وجداول كاحتياط |
| TheSportsDB | مفعّل في registry | `THESPORTSDB_API_KEY` عند التشغيل | مغلقة | مصدر مساعد أو تاريخي |

يُحفظ الإعداد في `configs/external_sources.yaml`. يبقى `mode=shadow_only` و`commercial_release=false`. لا تُحفظ المفاتيح في المستودع، ولا يقرأ registry إلا متغيرات البيئة عند وجودها.

## التحقق المحلي

لتأكيد أن المحولات الأربعة مسجلة دون إجراء network call:

```bash
python scripts/ingestion/scripts_run_provider_readiness.py \
  --date 2026-08-28 \
  --output reports/generated/provider_readiness.json
```

ينتج التشغيل الافتراضي حالة `deferred` لكل مزود مع `network_requested=false`. هذه هي الحالة المقصودة للاختبارات المحلية. لا يتحول المصدر إلى `reachable` إلا عند تمرير `--allow-network` صراحةً، وعندها يحتاج مزودا `football-data.org` و`TheSportsDB` إلى مفاتيح صالحة في متغيرات البيئة.

## التشغيل الشبكي الصريح

إذا توفرت موافقة مستقلة على اختبار مصدر خارجي، تُمرر المفاتيح عبر البيئة فقط:

```bash
export FOOTBALL_DATA_API_TOKEN='ضع-المفتاح-خارج-Git'
export THESPORTSDB_API_KEY='ضع-المفتاح-خارج-Git'
python scripts/ingestion/scripts_run_provider_readiness.py \
  --date YYYY-MM-DD \
  --allow-network
```

لا يرسل هذا المشغل توقعات أو Telegram أو odds أو EV أو ROI، ولا يضيف نتائج المصدر إلى تقييم BTTS تلقائياً. يجب أولاً حفظ provenance، والتحقق من `kickoff_utc`، والتكرار، والتغطية، وحقول ما قبل المباراة، ثم تمرير البيانات إلى ingestion المعتمد. نجاح endpoint واحد لا يثبت دقة النموذج أو صلاحية المصدر التجارية.

## حواجز المشروع

يبقى `2526` خارج التطوير والاختيار والمعايرة، ويبقى `2627` محجوزاً وغير مقيم. لا تتغير `TARGET_COLUMNS` أو `POST_MATCH_AUDIT_COLUMNS` أو حواجز temporal leakage. لا يوجد نشر أو ربط بمنصة Manus ضمن هذه الإضافة.

## المراجع

[1]: https://github.com/public-apis/public-apis "Public APIs directory"
[2]: https://www.openligadb.de/ "OpenLigaDB"
[3]: https://sportscore.com/developers/ "SportScore Developers"
[4]: https://www.football-data.org/documentation/quickstart "football-data.org Quickstart"
[5]: https://www.thesportsdb.com/api.php "TheSportsDB API"
