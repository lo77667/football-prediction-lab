# Cycle 32 — مصدر odds وقرار الجاهزية

## نتائج الفحص المحلي

توجد في `data/raw/*_E0.csv` حقول odds تاريخية مثل `B365H/B365D/B365A` و`AvgH/AvgD/AvgA` وحقول over/under. لكن الملفات المحلية لا تتضمن لكل quote سجلًا مستقلًا يحوي `captured_at` وtimezone و`provenance_id` و`input_sha256` وسياسة ترخيص مرتبطة بالصف. لذلك لا تُعد هذه الحقول وحدها pre-match odds snapshots صالحة للمقارنة التشغيلية في Cycle 32.

`configs/sources.yaml` يعرّف المصدر باسم Football-Data.co.uk ويذكر صراحة ضرورة التحقق من شروط إعادة الاستخدام قبل إعادة التوزيع. لا توجد داخل مسار البيانات المحلي وثيقة license/provenance تربط كل odds snapshot بوقت الالتقاط ومعرف مصدر قابل للتدقيق.

## نتائج المصدر الرسمي

صفحة البيانات الرسمية تصف Football-Data.co.uk بأنه يوفر نتائج وإحصاءات وبيانات odds تاريخية [1]. صفحة الملاحظات الرسمية تعرّف حقول odds بأنها **pre-closing odds**، وتوضح أن closing odds تستخدم لاحقة `C` مثل `B365CH` [2]. كما تذكر الصفحة أن وقت المباراة هو kickoff، لكنها لا تحول الأعمدة التاريخية إلى سجل snapshot زمني مستقل لكل price quote.

بناءً على ذلك، فإن بيانات Football-Data المحلية مفيدة كبيانات تاريخية وصفية أو كمرجع بحثي بعد توثيق الحقوق، لكنها لا تحقق وحدها عقد Cycle 32 الذي يشترط وقت التقاط، timezone UTC، provenance/hash، وربطًا point-in-time مع kickoff. لم تُنزّل بيانات odds جديدة، ولم تُضف بيانات غير موثقة إلى Git.

## القرار

**لا توجد حاليًا بيانات odds حقيقية مكتملة provenance وقابلة للاستخدام التشغيلي في benchmark Cycle 32.** لذلك ستنفذ الدورة schema وvalidator وfixtures test-only وتقرير readiness، من دون أرقام edge أو EV حقيقية، ومن دون اختيار مصدر أو ضبط نموذج اعتمادًا على 2526.

## المصادر

[1]: https://www.football-data.co.uk/data.php "Football-Data.co.uk historical results and betting odds data"

[2]: https://www.football-data.co.uk/notes.txt "Football-Data.co.uk notes and odds field definitions"

[3]: https://www.football-data.co.uk/disclaimer.php "Football-Data.co.uk disclaimer"
