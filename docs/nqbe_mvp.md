# NQBE MVP

يقدّم هذا المستودع نسخة MVP قابلة للتدقيق من المكونات الأولى في وثيقة تصميم **NEMESIS QUANTUM BETTING ENGINE**. التنفيذ مخصص للبحث التاريخي والاختبار الخلفي فقط، ولا يتصل بمكاتب مراهنات ولا ينفذ أوامر مالية.

## المكونات

| المكوّن | التنفيذ الحالي | ملاحظة نطاق |
|---|---|---|
| NNF | `NeuralNoiseFilter` | مرشح زمني robust median + EMA كبديل شفاف إلى حين توفر نموذج CNN مدرّب ومثبت الإصدار |
| LFA | `LiveFlowAnalyzer` | عوائد لوغاريتمية للأسعار مع متوسط وتباين أسيين ودرجة Z وإشارة buy/sell/hold |
| BAP | `BayesianAdaptivePoisson` | سابق Gamma-Poisson مستقل لمعدلي أهداف المضيف والضيف، مع احتمال BTTS |
| SAD | `SmartArbitrageDetector` | يحسب مجموع الاحتمالات الضمنية ويضع علامة فرصة عندما يكون أقل من 1 |
| إدارة المخاطر | `half_kelly_fraction` | تشخيص Half-Kelly مقيد بسقف، وليس توصية مالية أو آلية تنفيذ |

## مثال استخدام

```python
from football_prediction_lab.nqbe import (
    BayesianAdaptivePoisson,
    LiveFlowAnalyzer,
    SmartArbitrageDetector,
    half_kelly_fraction,
)

flow = LiveFlowAnalyzer().analyze([2.10, 2.04, 1.92])
poisson = BayesianAdaptivePoisson()
poisson.update(goals_home=2, goals_away=1)
probability = poisson.predict_btts()
arbitrage = SmartArbitrageDetector().scan({"home": 2.2, "draw": 4.0, "away": 4.5})
sizing = half_kelly_fraction(probability, decimal_odds=2.0)
```

## حدود علمية وتشغيلية

لا يدّعي هذا الـMVP وجود تسريع كمومي فعلي أو تفوق تنبؤي بنسبة محددة. مكونات QKAD وQBN وQCAS وQAE-RE وTCE وMNRA وCPMD وPTSC وTPS مؤجلة إلى مراحل لاحقة لأنها تتطلب بيانات، نماذج مدرّبة، عقود تقييم، أو تكاملات لم يثبتها المستودع الحالي. يجب تقييم كل إشارة على بيانات زمنية منفصلة مع منع تسرب المستقبل وتسجيل مصدر البيانات والإصدار.

لتشغيل اختبارات الوحدة:

```bash
pytest -q
```
