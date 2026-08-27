# Football Prediction Lab

مختبر بحثي محلي قابل للتدقيق لتقييم توقعات كرة القدم، مع أولوية لمسار **كلا الفريقين يسجلان (BTTS)**. لا ينفذ المشروع مراهنات أو صفقات، ولا يقدّم ضمانًا للنتائج؛ هدفه حفظ التوقع قبل كشف النتيجة، ثم قياس الأداء وتوثيق الخطأ. تبقى `commercial_release=false`، ولا يوجد نشر أو ربط بمنصة Manus في هذه الدورة.

## دورة المشروع

1. جمع بيانات تاريخية موثقة.
2. إنشاء لقطة زمنية لا تحتوي إلا على المعلومات المتاحة قبل المباراة.
3. تدريب نموذج احتمالي بسيط.
4. إصدار توقع وحفظه في سجل غير قابل للتعديل.
5. كشف النتيجة بعد التوقع.
6. حساب الدقة والمعايرة وتحليل الأخطاء.
7. اعتماد أي تحسين فقط بعد اختبار زمني مستقل.

## نطاق الإصدار الحالي

يتضمن الإصدار الحالي مساراً بحثياً محلياً لـBTTS مع أدوات ingestion وfeatures وwalk-forward وshadow وquality منظمة تحت `scripts/`. تعتمد الميزات على التاريخ المتاح قبل المباراة فقط، وتحافظ على `kickoff_utc` صريحاً ومترتباً زمنياً. لا تُعامل fixtures أو smoke runs كدليل على جودة تجارية، ولا تُستخدم نتائج الاختبار الخارجي لاختيار النموذج.

تظل أسواق البطاقات ومسارات المقارنة السابقة محفوظة لأغراض التدقيق التاريخي فقط، وليست توسعاً نشطاً في هذه الدورة. وتبقى أعمدة النتائج والإحصاءات اللاحقة للمباراة محظورة كمدخلات نموذجية عبر `TARGET_COLUMNS` و`POST_MATCH_AUDIT_COLUMNS`، مع حماية temporal leakage.

يعرض [`docs/RESEARCH_LOG.md`](docs/RESEARCH_LOG.md) القرارات والأرقام الموثقة، بينما توجد التقارير التفصيلية القديمة في [`docs/archive/`](docs/archive/).
## المسارات المجمدة

مسارات Android، ومستودع اللاعبات اليافعات، وPower BI، وdrift، والمسار النوعي الهجين، والأسواق غير BTTS مجمدة ولا تمثل مكونات نشطة للإصدار الحالي. لا تُضاف إليها بيانات أو tuning أو تشغيل جديد قبل إثبات قيمة مسار BTTS ومراجعة موثقة.
## الوضع التشغيلي

التشغيل الحالي محلي وshadow-only. لا توجد خدمة عامة أو scheduler خارجي أو Telegram حقيقي أو مصدر odds حي. workflow الموجود في `.github/workflows/` محفوظ للتحقق من بنية الجودة، لكن لا يُعلن نجاح CI البعيد دون سجل تنفيذ فعلي على آخر commit.
## محولات مصادر كرة القدم

أضيفت محولات موحدة للمصادر الأربعة المرتبطة بالمشروع في `src/football_prediction_lab/source/providers.py`، وهي `OpenLigaDB` و`SportScore` و`football-data.org` و`TheSportsDB`. إعدادها موجود في `configs/external_sources.yaml`، وجميعها `enabled: true` داخل registry المحلي، لكن `allow_network: false` افتراضياً حتى لا تبدأ الاختبارات أو الاستيرادات طلبات خارجية. يحتاج `football-data.org` إلى متغير البيئة `FOOTBALL_DATA_API_TOKEN`، ويحتاج `TheSportsDB` إلى `THESPORTSDB_API_KEY`؛ لا تُحفظ هذه القيم في Git. التفعيل الشبكي الفعلي يتطلب تمريراً صريحاً من المشغل ومراجعة شروط المزود، ولا يفتح commercial release.

البيانات القادمة من أي مزود لا تدخل التقييم مباشرة؛ يجب أولاً فحص provenance و`kickoff_utc` والتكرار والتغطية ومنع الحقول اللاحقة للمباراة. نجاح محول أو طلب واحد لا يثبت جودة BTTS أو الربحية.

## بنية المستودع

- `src/football_prediction_lab/`: حزم جمع البيانات، الميزات، النماذج، التقييم، السجل، والوكيل التفسيري.
- `configs/`: إعدادات قابلة للتكرار.
- `data/`: بيانات خام ومعالجة وخارجية؛ لا تُحفظ أسرار أو مفاتيح هنا.
- `docs/`: بروتوكولات المشروع وقواعد الأدوار والمراجعة.
- `reports/`: مخرجات التجارب والتقارير.
- `tests/`: اختبارات آلية.

## التشغيل المحلي

يتطلب المشروع Python 3.11 أو أحدث. بعد تثبيت الاعتماديات:

```bash
python -m football_prediction_lab --help
pytest
ruff check .
```

لبناء عينة EPL متعددة المواسم وإعادة إنتاج ميزاتها:

```bash
for season in 1516 1617 1718 1819 1920 2021 2122 2223 2324 2425; do
  python scripts/ingestion/scripts_download_initial.py --season "$season" --competition E0
done
python scripts/features/scripts_combine_seasons.py \
  --output data/processed/epl_1516_2425.csv
python scripts/features/scripts_build_features.py \
  --input data/processed/epl_1516_2425.csv \
  --output data/processed/epl_1516_2425_features.csv
# يكتب أيضًا manifest بجوار ملف الميزات
python scripts/evaluation/scripts_compare_btts_multiseason.py \
  --input data/processed/epl_1516_2425_features.csv
python scripts/evaluation/scripts_compare_cards_multiseason.py \
  --input data/processed/epl_1516_2425.csv
python scripts/walk_forward/scripts_walk_forward.py \
  --input data/processed/epl_1516_2425_features.csv \
  --cards-input data/processed/epl_1516_2425.csv
python scripts/walk_forward/scripts_walk_forward_tuned.py \
  --input data/processed/epl_1516_2425_features.csv \
  --cards-input data/processed/epl_1516_2425.csv
```

لتشغيل مقارنة الكمي بالهجين، يجب توفير ملف JSONL حقيقي مصدره موثق ومسموح استخدامه؛ لا يُنشأ هذا الملف من نص مولد أو من نتيجة المباراة:

```bash
python scripts/evaluation/scripts_compare_btts_hybrid.py \
  --qualitative-events path/to/verified_events.jsonl
```

لفحص موسم مع manifest وفحوص provenance المشددة:

```bash
python scripts/ingestion/scripts_validate_season.py \
  --input data/processed/2425_E0.csv \
  --output reports/generated/validate_2425.json
```

في الإصدار الحالي تعمل المكونات الأساسية دون مفتاح API. ويجب مراجعة ترخيص كل مصدر قبل إعادة توزيع البيانات أو تشغيل خدمة عامة. ويظل `scripts/evaluation/scripts_compare_btts_hybrid.py` مسارًا اختياريًا لا يعمل دون أحداث نوعية حقيقية متحققة زمنيًا.

## معيار الانتقال بين المراحل

لا تنتقل المرحلة التالية إلا بعد مرور العمل على ستة أدوار: المنفّذ، المدقّق، المراجع، الباحث، المطوّر، والضامن. يسجل كل دور ملاحظاته في تقرير التجربة أو سجل المراجعة، ولا تُخفى الأخطاء أو تُعدّل النتائج السابقة.

## التثبيت وإعادة الإنتاج من Full Source Bundle

النسخة القابلة لإعادة الإنتاج تُستخرج من Git عبر `git archive`، ولا تعتمد على ملفات `data/` المحلية أو على checkout سابق. بعد فك الأرشيف من جذر المشروع، أنشئ بيئة نظيفة وثبّت الاعتماديات المقيدة:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install -e . --no-deps
```

يضمن الأمر الأخير تسجيل الحزمة الحالية في البيئة دون استبدال الإصدارات المقيدة في lock. بعد التثبيت، تحقّق من أن imports تشير إلى المشروع الحالي، ثم شغّل verifier الرسمي:

```bash
.venv/bin/python -c "import football_prediction_lab; print(football_prediction_lab.__file__)"
.venv/bin/python -c "import football_prediction_lab.evaluation.cycle36_model_selection as m; print(m.__file__)"
.venv/bin/python scripts/quality/verify_cycle36_reproducibility.py
```

يشغّل verifier الاختبارات وRuff وcompileall وtest summary من نفس `venv`، ويتحقق من أن مسارات modules تبدأ بجذر المشروع الحالي. كما توجد fixtures صغيرة في `tests/fixtures/cycle36_smoke/` لاختبار imports وPoisson probabilities فقط؛ لا تُستخدم هذه fixtures لإعادة إنتاج metrics التاريخية.

لإعادة إنتاج التقييم التاريخي لـCycle 36، يجب توفير ملفات البيانات المحلية المصرح بها في `data/processed/` مع manifest وSHA-256 خارج Git. لا تُضمَّن البيانات المحلية أو الأسرار في Full Source Bundle. موسم `2526` خارج التطوير والاختيار، وموسم `2627` محجوز كـfuture holdout غير متاح وغير مقيم، وتبقى `commercial_release=false`.

## وصف التسليم

الأرشيف الكامل هو **Full reproducible source bundle** وليس patch-only bundle. يُنشأ من كل الملفات المتتبعة في commit الإصدار باستخدام:

```bash
git archive --format=zip --prefix=football-prediction-lab/ HEAD -o /tmp/football-prediction-lab-full.zip
```

ويشمل `src/` و`tests/` وملفات التشغيل المنظمة تحت `scripts/` و`pyproject.toml` و`requirements.lock` و`configs/` و`docs/` و`reports/` المتتبعة. ويستبدل Git تلقائيًا marker الموجود في `SOURCE_COMMIT.txt` ببصمة commit داخل الأرشيف. لا يعتمد على حزمة انتقائية أو imports من checkout آخر.
