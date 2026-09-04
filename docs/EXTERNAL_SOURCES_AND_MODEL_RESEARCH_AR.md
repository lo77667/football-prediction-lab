# نتائج البحث الخارجي واختيار مصادر البيانات والنموذج

## القرار

المصدر الأنسب كبداية منخفضة المخاطر هو **OpenLigaDB** للمباريات والنتائج في الدوريات التي يغطيها، لأنه يعلن أن الوصول لا يحتاج مصادقة وأن البيانات تحت Open Database License (ODbL). لا يعني ذلك أن كل استخدام تجاري مباح تلقائيًا؛ يجب حفظ attribution والالتزام بشروط ODbL.

المصدر الرسمي الأكثر قابلية للتوسعة هو **football-data.org**. يوفر API منظمة للمسابقات والمباريات، لكنه محدود السرعة ويحتاج `X-Auth-Token` للمصادر المسجلة. يُستخدم فقط مع caching وsnapshots وmanifest، وليس polling مفرطًا.

أفضل مصدر وجدته لتقييم odds التاريخية هو **The Odds API**. وثائقه تصف snapshots تاريخية بوقت محدد، لكنها تذكر أن endpoint التاريخي متاح فقط في الخطط المدفوعة. لذلك لا يمكن اعتباره حلًا مجانيًا، ولا ينبغي تفعيل benchmark الاقتصادي قبل اشتراك مرخص وظهور `captured_at_utc` و`available_at_utc`.

**API-Football/API-Sports** يغطي fixtures والإصابات والتشكيلات وpre-match odds، لكنه يعتمد على API key وخطط استخدام. يصلح كمصدر تجريبي ثانوي، وليس كبديل مجاني مثبت، إلى أن تتم مراجعة الخطة والترخيص وتغطية الدوريات المطلوبة.

## تقييم المصادر

| المصدر | بيانات متوقعة | المصادقة | ملاءمة حالية | القرار |
|---|---|---|---|---|
| OpenLigaDB | نتائج ومواعيد وترتيب، تركيز قوي على ألمانيا وبعض الدوريات | لا يحتاج token | جيد للمباريات، محدود جغرافيًا | ابدأ به للـsnapshots المرخصة |
| football-data.org | مسابقات ومباريات ونتائج وفرق | `FOOTBALL_DATA_API_TOKEN` | جيد للمسار الأساسي مع rate limiting | مصدر رسمي أساسي بعد إضافة السر |
| TheSportsDB | فرق ومباريات ومحتوى رياضي | `THESPORTSDB_API_KEY` | يحتاج فحص التغطية والترخيص | مصدر احتياطي، لا يخلط تلقائيًا |
| API-Football/API-Sports | fixtures، statistics، lineups، injuries، odds | `x-apisports-key` | تغطية واسعة لكن مدفوعة/محدودة حسب الخطة | مرشح للبيانات الغنية بعد مراجعة تجارية |
| The Odds API | odds حية وتاريخية snapshots | `THE_ODDS_API_KEY` في query | ممتاز للـbenchmark، التاريخي مدفوع | مؤجل حتى توفر اشتراك مرخص |
| Football-Data.co.uk | ملفات تاريخية وodds-like columns | لا يعتمد على API token | لا يثبت وقت التقاط السعر | لا يستخدم كـtimestamped odds benchmark |

## نموذج مفتوح المصدر تمت مراجعته

تمت مراجعة `Hicruben/world-cup-2026-prediction-model`. المستودع يعلن MIT License ويستخدم Elo ثم Dixon-Coles bivariate Poisson ثم Monte Carlo، كما يتضمن backtest walk-forward ومقاييس log-loss وBrier وECE. يمكن الاستفادة من الفكرة والبنية لأن الترخيص MIT، لكن لا يجب نسخ البيانات أو ادعاءات track record دون التحقق المستقل.

القرار الهندسي هو إضافة Dixon-Coles كمرشح داخلي مستقل، مع إبقاء Poisson الحالي كخط أساس. لا يعتمد الاختيار على ادعاءات accuracy في README لأي مستودع خارجي. يعتمد فقط على نتيجة walk-forward داخل هذا المشروع.

## نموذج البيانات المقترح

لكل مباراة يجب الاحتفاظ بـ `source_name` و`source_version` و`request_or_snapshot_id` و`captured_at_utc` و`available_at_utc` و`kickoff_utc` و`input_sha256` و`license_or_usage_policy`. تُرفض أي لقطة لا تثبت أن البيانات كانت متاحة قبل kickoff.

## قرار الربحية

لا توجد نتيجة بحث تثبت أن API أو مستودعًا مفتوحًا يضمن الربح. القيمة التجارية تعتمد على احتمالات معايرة وأسعار متاحة فعليًا وتكاليف التنفيذ. لذلك تبقى `commercial_release=false`، وتبقى stake sizing والتنفيذ المالي خارج النظام.

## الروابط الرسمية

- [football-data.org API](https://www.football-data.org/documentation/api)
- [football-data.org policies](https://docs.football-data.org/general/v4/policies.html)
- [OpenLigaDB](https://www.openligadb.de/)
- [OpenLigaDB samples](https://github.com/OpenLigaDB/OpenLigaDB-Samples)
- [The Odds API v4 documentation](https://the-odds-api.com/liveapi/guides/v4/)
- [The Odds API historical odds](https://the-odds-api.com/historical-odds-data/)
- [API-Football documentation](https://www.api-football.com/documentation-v3)
- [MIT-licensed Dixon-Coles model repository](https://github.com/Hicruben/world-cup-2026-prediction-model)

## References

[1]: https://www.football-data.org/documentation/api "Football-Data.org API documentation"
[2]: https://docs.football-data.org/general/v4/policies.html "Football-Data.org API policies"
[3]: https://www.openligadb.de/ "OpenLigaDB official site and license information"
[4]: https://the-odds-api.com/liveapi/guides/v4/ "The Odds API v4 documentation"
[5]: https://www.api-football.com/documentation-v3 "API-Football official documentation"
[6]: https://github.com/Hicruben/world-cup-2026-prediction-model "MIT-licensed open-source Dixon-Coles prediction model"
