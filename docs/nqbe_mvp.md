# NQBE Research MVP — Implementation Status

يحتوي هذا المستودع الآن على طبقة NQBE بحثية قابلة للاختبار والتدقيق. التنفيذ لا يتصل بمكاتب المراهنات، ولا ينفذ أوامر مالية، ولا يقدّم ضمانًا تنبؤيًا أو عائدًا ماليًا. جميع النتائج موسومة `research_only`، وجميع المدخلات يجب أن تكون معروفة قبل وقت الانطلاق لمنع تسرب المستقبل.

## المكونات المنفذة

| الطبقة | المكوّن | التنفيذ | الحالة |
|---|---|---|---|
| الاستشعار والتنقية | NNF | `NeuralNoiseFilter`: rolling median + EMA كبديل حتمي شفاف | منفذ؛ CNN حقيقي مؤجل |
| الاستشعار والتنقية | LFA | `LiveFlowAnalyzer`: عوائد لوغاريتمية، EWMA، درجة Z، وإشارة `buy/sell/hold` | منفذ |
| التحليل الكلاسيكي | BAP | `BayesianAdaptivePoisson`: Gamma-Poisson لمعدلات المضيف والضيف واحتمال BTTS | منفذ |
| التحليل الكلاسيكي | SAD | `SmartArbitrageDetector`: مجموع الاحتمالات الضمنية وهامش المراجحة | منفذ؛ فحص رياضي فقط |
| التسريع الهجين | QKAD | `QuantumKernelAnomalyDetector`: RBF/kernel proxy كلاسيكي بواجهة موسومة بوضوح | منفذ كمحاكاة كلاسيكية |
| التسريع الهجين | QBN | `QuantumBayesianNetwork`: دمج احتمالات عبر amplitudes proxy | منفذ كمحاكاة كلاسيكية |
| التسريع الهجين | QCAS | `QuantumCombinatorialArbitrageSearch`: تعداد تركيبات حتمي | منفذ كبديل كلاسيكي؛ لا Grover/QAOA فعلي |
| السياق | ESS | `ExtremeScenarioSimulator`: حالات baseline والانهيار الدفاعي واحتمال BTTS الموزون | منفذ |
| السياق | TCE | `TemporalContextEncoder`: متجه زخم موزون زمنيًا | منفذ كخط أساس حتمي |
| السياق | MTM | `MarketTopologyMapper`: ارتباطات، حواف، درجات، وعقدة hub | منفذ |
| السياق | TPS | `TacticalParticleSimulator`: محاكاة أهداف Poisson حتمية ببذرة ثابتة | منفذ؛ ليس ABM للاعبين بعد |
| السياق | MNRA | `MarketNarrativeResonanceAnalyzer`: baseline قائم على كلمات مفتاحية | منفذ؛ لا يجمع أخبارًا ذاتيًا |
| السياق | CPMD | `ContextualPsychologicalManipulationDetector`: ارتباط تدفق المعلومات بالسوق | منفذ كإشارة فحص، لا إثبات سببي |
| السياق | PTSC | `LivePsychoTacticalStressCalibrator`: تطبيع مدخلات ضغط اختيارية | منفذ؛ لا تحليل فيديو/صوت |
| المخاطر | QAE-RE | `QuantumAmplitudeEstimationRiskEngine`: VaR كلاسيكي بواجهة QAE-compatible | منفذ كبديل كلاسيكي |
| المخاطر | Half-Kelly | `half_kelly_fraction`: نصف كيلي محدود بسقف | منفذ كتشخيص بحثي فقط |
| سير العمل | NQBE workflow | `NQBEResearchWorkflow`: يربط التدفق، BAP، السيناريوهات، TPS، QBN، السياق، الشذوذ وVaR | منفذ |
| الواجهة والتخزين | API + ledger | `NQBEAPI` و`NQBEResearchLedger`: عقد JSON وسجل JSONL append-only | منفذ محلي/داخل العملية |

## الملفات الرئيسية

```text
src/football_prediction_lab/nqbe.py
src/football_prediction_lab/nqbe_hybrid.py
src/football_prediction_lab/nqbe_workflow.py
src/football_prediction_lab/nqbe_api.py
tests/test_nqbe.py
tests/test_nqbe_hybrid.py
tests/test_nqbe_workflow.py
tests/test_nqbe_api.py
```

## مثال تشغيل

```python
from football_prediction_lab.nqbe_api import NQBEAPI

response = NQBEAPI().post_analysis({
    "match_id": "fixture-1",
    "captured_at": "2026-08-31T18:30:00+00:00",
    "kickoff_at": "2026-08-31T19:00:00+00:00",
    "odds_history": [2.10, 2.00, 1.90],
    "home_rate": 1.30,
    "away_rate": 1.00,
    "event_deltas": [0.1, 0.4, -0.1],
    "narrative_texts": ["strong form"],
})
```

يرفض سير العمل أي `captured_at` يساوي أو يتجاوز `kickoff_at`. كما أن `NQBEResearchLedger` يرفض تخزين استجابة غير موسومة `research_only`.

## ما يزال مؤجلًا

لم تُنفذ بعد تكاملات بيانات حية مرخصة، و42+ مزود أسعار، وRedis، وPostgreSQL، وواجهة مستخدم، وGPU training، وشبكات 1D-CNN/LSTM/Transformer/GNN حقيقية، وتحليل فيديو أو صوت، ونموذج ABM مفصل للاعبين، واتصال Qiskit/Cirq أو أجهزة كمومية فعلية، وGrover/QAOA/QAE الحقيقي. هذه ليست بيانات يمكن اختلاقها بأمان؛ يلزم توفير مصادر مرخصة، مخططات بيانات، artifacts تدريب، وسياسات تقييم قبل تحويل البدائل الحالية إلى مكونات إنتاجية.

كما أن التنفيذ الآلي للمراهنات **مستبعد عمدًا** من المشروع الحالي. المخرجات إشارات بحثية للتقييم الخلفي وليست توصيات مالية أو أوامر تنفيذ.

## التحقق

تم تشغيل الاختبارات الجديدة والاختبارات الكاملة. النتيجة الحالية هي **399 اختبارًا ناجحًا**، مع تحذيرات DeprecationWarning موجودة مسبقًا في `features/pre_match.py` ولا تتعلق بإضافة NQBE. يمكن إعادة التشغيل عبر:

```bash
python3 -m pytest -q
ruff check src/football_prediction_lab/nqbe.py \
  src/football_prediction_lab/nqbe_hybrid.py \
  src/football_prediction_lab/nqbe_workflow.py \
  src/football_prediction_lab/nqbe_api.py
```
