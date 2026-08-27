# دورة 26: حارس التقييم المستقبلي

أضيف `scripts_assess_future_holdout_readiness.py` لمنع إعادة استخدام موسم مرئي أو اختلاق موسم غير موجود. عند تشغيله على طلب موسم `2526` وملف `epl_1516_2425.csv`، كانت النتيجة `ready=false` لأن آخر موسم observed هو `2425`، والرسالة: `defer: no genuinely future season is available; do not fabricate or reuse observed data`.

هذا الحارس لا ينشئ بيانات ولا ينفذ تقييمًا ناقصًا. بعد وصول ملف مستقل ومرخص يتضمن موسمًا أحدث من `2425`، يمكن استخدامه كبوابة قبل تشغيل walk-forward. يظل القرار البحثي الحالي: لا اعتماد BTTS أو cards مقابل constant لأن فواصل bootstrap المقترنة تعبر الصفر.
