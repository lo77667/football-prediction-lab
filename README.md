# Football Prediction Lab

منصة بحثية قابلة للتدقيق لتدريب واختبار نماذج توقع أسواق كرة القدم، تبدأ بنسخة صغيرة لسوق **كلا الفريقين يسجلان (BTTS)**. لا ينفذ المشروع مراهنات أو صفقات، ولا يقدّم ضمانًا للنتائج؛ هدفه بناء دورة علمية تحفظ التوقع قبل كشف النتيجة، ثم تقيس الأداء وتوثق الخطأ.

## دورة المشروع

1. جمع بيانات تاريخية موثقة.
2. إنشاء لقطة زمنية لا تحتوي إلا على المعلومات المتاحة قبل المباراة.
3. تدريب نموذج احتمالي بسيط.
4. إصدار توقع وحفظه في سجل غير قابل للتعديل.
5. كشف النتيجة بعد التوقع.
6. حساب الدقة والمعايرة وتحليل الأخطاء.
7. اعتماد أي تحسين فقط بعد اختبار زمني مستقل.

## نطاق الإصدار الحالي

يتضمن الإصدار الحالي مسارًا كميًا لـBTTS على عينة EPL من عشرة مواسم (`1516` إلى `2425`) بإجمالي 3800 مباراة محليًا، ونسخة بحثية منفصلة لسوق أكثر من 3.5 بطاقة صفراء. تستخدم الميزات الكمية تاريخ المباريات السابقة فقط، وتحتفظ بالطابع الزمني `Date + Time` في `kickoff_utc` مع timezone واضح (`UTC`)، وتفرز الصفوف بـ`kickoff_utc` ثم `match_id` لكسر التعادل. يدعم المسار مقارنة legacy بالموسعة على تقسيم زمني لا يخلط المستقبل بالماضي. ينتج الإدخال وبناء الميزات manifest يتضمن المصدر والبصمة وعدد الصفوف والنطاق الزمني ونسخة الميزات.

أُضيفت ميزات حكم تاريخية لسوق البطاقات، لكنها لا تُعتمد بوصفها تحسينًا عامًا إلا بعد مراجعة نتائج التحقق والاختبار المستقلين. وتُحفظ تقارير المقارنة المحلية في `reports/generated/` ولا تُرفع ملفات البيانات الكبيرة إلى Git. وتبقى أعمدة النتائج والإحصاءات اللاحقة للمباراة متاحة للتدقيق، لكنها محظورة كمدخلات نموذجية عبر عقد `TARGET_COLUMNS` و`POST_MATCH_AUDIT_COLUMNS`.

المسار النوعي الهجين ليس مُفعّلًا للتدريب بعد. توجد عقود Pydantic واختبارات تمنع استخدام حدث بلا مصدر أو حدث ظهر بعد نقطة القطع. لا يصبح النظام هجينًا إلا بعد جمع مصادر حقيقية مسموحة، وتسجيل وقت الإتاحة والدليل، وإجراء تجربة ablation خارج العينة.

## مستودع اللاعب الهجين

أُضيف مخطط عملي لمستودع أداء اللاعبات اليافعات في [`docs/youth_player_hybrid_warehouse.md`](docs/youth_player_hybrid_warehouse.md). يشمل ذلك DDL لـPostgreSQL، ومُتحققات وفهارس MongoDB، وعقود Pydantic، واستخراجًا محافظًا للمؤشرات النوعية، وتجربة كمية مقابل هجينة، وضوابط الخصوصية واللوحة التشغيلية. توجد الملفات التنفيذية في `schemas/` و`src/football_prediction_lab/player_warehouse/` والاختبارات في `tests/test_player_warehouse.py`.

هذا المسار لا يحتوي على بيانات لاعبات حقيقية ولا يفعّل أي قرار آلي. قبل التدريب الإنتاجي يجب اعتماد الموافقات، ومراجعة حماية البيانات، وإدخال مصادر حقيقية مصرح بها، وإجراء اختبار زمني مستقل مع فحوص المعايرة والإنصاف.

## التحسينات التشغيلية

توجد تحسينات الأداء والتنبيهات وCI/CD وPower BI في [`docs/operational_enhancements.md`](docs/operational_enhancements.md)، مع ترحيل PostgreSQL في `schemas/postgres/002_partitioned_summary_alerts.sql`، ومنطق التنبيه في `src/football_prediction_lab/player_warehouse/alerts.py`، وسير العمل الموحد في `.github/workflows/quality-gate.yml`، وقياسات DAX في `docs/powerbi_daily_go_no_go.dax`.

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
  python scripts_download_initial.py --season "$season" --competition E0
done
python scripts_combine_seasons.py \
  --output data/processed/epl_1516_2425.csv
python scripts_build_features.py \
  --input data/processed/epl_1516_2425.csv \
  --output data/processed/epl_1516_2425_features.csv
# يكتب أيضًا manifest بجوار ملف الميزات
python scripts_compare_btts_multiseason.py \
  --input data/processed/epl_1516_2425_features.csv
python scripts_compare_cards_multiseason.py \
  --input data/processed/epl_1516_2425.csv
python scripts_walk_forward.py \
  --input data/processed/epl_1516_2425_features.csv \
  --cards-input data/processed/epl_1516_2425.csv
python scripts_walk_forward_tuned.py \
  --input data/processed/epl_1516_2425_features.csv \
  --cards-input data/processed/epl_1516_2425.csv
```

لتشغيل مقارنة الكمي بالهجين، يجب توفير ملف JSONL حقيقي مصدره موثق ومسموح استخدامه؛ لا يُنشأ هذا الملف من نص مولد أو من نتيجة المباراة:

```bash
python scripts_compare_btts_hybrid.py \
  --qualitative-events path/to/verified_events.jsonl
```

لفحص موسم مع manifest وفحوص provenance المشددة:

```bash
python scripts_validate_season.py \
  --input data/processed/2425_E0.csv \
  --output reports/generated/validate_2425.json
```

في الإصدار الحالي تعمل المكونات الأساسية دون مفتاح API. ويجب مراجعة ترخيص كل مصدر قبل إعادة توزيع البيانات أو تشغيل خدمة عامة. ويظل `scripts_compare_btts_hybrid.py` مسارًا اختياريًا لا يعمل دون أحداث نوعية حقيقية متحققة زمنيًا.

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
.venv/bin/python scripts/verify_cycle36_reproducibility.py
```

يشغّل verifier الاختبارات وRuff وcompileall وtest summary من نفس `venv`، ويتحقق من أن مسارات modules تبدأ بجذر المشروع الحالي. كما توجد fixtures صغيرة في `tests/fixtures/cycle36_smoke/` لاختبار imports وPoisson probabilities فقط؛ لا تُستخدم هذه fixtures لإعادة إنتاج metrics التاريخية.

لإعادة إنتاج التقييم التاريخي لـCycle 36، يجب توفير ملفات البيانات المحلية المصرح بها في `data/processed/` مع manifest وSHA-256 خارج Git. لا تُضمَّن البيانات المحلية أو الأسرار في Full Source Bundle. موسم `2526` خارج التطوير والاختيار، وموسم `2627` محجوز كـfuture holdout غير متاح وغير مقيم، وتبقى `commercial_release=false`.

## وصف التسليم

الأرشيف الكامل هو **Full reproducible source bundle** وليس patch-only bundle. يُنشأ من كل الملفات المتتبعة في commit الإصدار باستخدام:

```bash
git archive --format=zip --prefix=football-prediction-lab/ HEAD -o /tmp/football-prediction-lab-full.zip
```

ويشمل `src/` و`tests/` وملفات التشغيل الجذرية و`scripts/` و`pyproject.toml` و`requirements.lock` و`configs/` و`docs/` و`reports/` المتتبعة. ويستبدل Git تلقائيًا marker الموجود في `SOURCE_COMMIT.txt` ببصمة commit داخل الأرشيف. لا يعتمد على حزمة انتقائية أو imports من checkout آخر.
