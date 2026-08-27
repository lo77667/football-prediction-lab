# دمج OpenLigaDB للدوري الإنجليزي

## النطاق

تمت إضافة adapter محلي لـOpenLigaDB دون API key. لا يُسمح بالاتصال الشبكي افتراضياً؛ يلزم تمرير `allow_network=True` صراحةً. لا يتضمن الدمج odds أو EV أو ROI أو stake sizing أو Telegram أو إطلاقاً تجارياً، وتبقى `commercial_release=false`.

## الاختبار الحي المحدود

في 27 أغسطس 2026 تم اختبار المسار العام التالي:

```text
https://api.openligadb.de/getmatchdata/pl/2026
```

أعاد المصدر 380 مباراة لموسم `Premier League 2026/2027`، منها 10 مباريات موسومة منتهية و370 مباراة غير منتهية في الاستجابة وقت الاختبار. استخدم adapter الحقل `matchDateTimeUTC` بدلاً من `matchDateTime` المحلي، ورفض أي timestamp لا يحمل UTC صريحاً. كما تحقق من معرف المباراة، هوية الفريقين، season وleague shortcut، وبنية النتائج.

SHA للاستجابة في ذلك الاختبار:

```text
3b6986e8a0476301a2ac8c026ca4c6a32d54e55e669486b1e32a2ec2a3e3375d
```

هذه القيمة تخص استجابة اختبارية زمنية وليست قيمة ثابتة؛ ستتغير عند تحديث المصدر. يجب حفظها مع وقت الجلب وcommit وendpoint في أي shadow run.

## الضوابط

يحوي client على timeout، وrate interval افتراضي، وcache داخل الذاكرة، ورفض path injection، ورفض JSON غير الصحيح أو الحقول غير المعروفة أو التوقيت غير UTC. لا يرسل client أي بيانات إلى جهة أخرى ولا يحتاج إلى secret.

## القيود

OpenLigaDB مصدر مجتمعي للنتائج الرياضية. وجود endpoint عام بلا مفتاح لا يثبت تلقائياً الترخيص التجاري أو التغطية الكاملة أو SLA. يجب فحص تغطية البطاقات والإحصاءات قبل استخدام هذه الحقول في model features. نتيجة الاختبار تثبت أن endpoint أعاد fixtures للموسم المحدد، ولا تثبت جودة النموذج أو precision أو الربحية.

## الحالة

الحالة الحالية هي `live_probe_passed` للمسار العام و`shadow_only` للمشروع. لم تُنقل البيانات الحية إلى تدريب النموذج، ولم تُستخدم نتائج المباريات القادمة قبل kickoff. الخطوة التالية الآمنة هي تشغيل shadow period تحفظ كل snapshot وprovenance ثم تقييم freshness وcoverage وduplicate rate قبل أي اعتماد للنموذج.

## المراجع

[1]: https://api.openligadb.de/index.html "OpenLigaDB Swagger UI"

[2]: https://github.com/OpenLigaDB/OpenLigaDB-Samples "OpenLigaDB official samples and API documentation"
