# دورة 47: بوابة التجربة المغلقة والإطلاق

## القرار التشغيلي

هذه الدورة تنفذ **حوكمة الإصدار فقط**. لا يوجد إطلاق عام، ولا إرسال Telegram حقيقي، ولا token أو Chat ID أو recipient حقيقي. الإعداد المقفل `configs/cycle47_closed_beta.json` يثبت `release_state=not_ready` و`mode=shadow_only` و`production_enabled=false` و`commercial_release=false` و`recipients=[]` و`telegram_enabled=false`.

حالة المصدر من دورة 46 هي `deferred_missing_authorized_source`، ولذلك لا تسمح البوابة بالانتقال إلى closed beta أو commercial service. لا تُعد probability أو smoke fixture دليلاً على جودة أو ربحية.

## release gate

تقيم `release/gate.py` الشروط بترتيب fail-closed. غياب provenance يحول الحالة إلى `blocked_provenance`، وغياب model quality إلى `blocked_model_quality`، ونقص worker أو Telegram test أو backup/restore أو monitoring أو security إلى `blocked_operations`. عند اكتمال تلك الشروط يبقى غياب المصدر الحي في `not_ready`، وغياب shadow period في `shadow_only`، وغياب الموافقة الصريحة في `closed_beta`. لا يمكن الوصول إلى `commercial_information_service` إلا بوجود مصدر موثق، وفترة shadow مكتملة، وموافقة المستخدم الصريحة، وتأكيد recipient، وتفعيل إنتاجي صريح.

## قائمة التحقق

| المجال | شرط البوابة | الحالة الحالية |
|---|---|---|
| المصدر | provider وlicense وsource manifest موثقة | blocked: المصدر deferred |
| provenance | policy/model/feature/code/ledger متسقة | يتطلب تحققاً مستقلاً |
| النموذج | baseline/quality معتمدان | غير معتمد للإطلاق |
| worker | restart recovery وdedup وheartbeat | منفذ محلياً فقط |
| Telegram | fake/dry-run فقط | لا إرسال حقيقي |
| التخزين | backup/restore وintegrity | منفذ محلياً |
| الأمان | لا أسرار وkill switch | مقفل افتراضياً |
| الموافقة | recipient والمحتوى والوضع | غير موجودة |

## kill switch وrollback

`KillSwitch` ملفي fail-closed: غياب الملف أو فساده يعني stopped. الكتابة ذرية، و`stop` يسجل سبب الإيقاف، و`resume` لا يُستخدم في الإنتاج. عند حادثة، أوقف worker، عطّل Telegram، حافظ على artifacts وevent logs، لا تحذف السجل، خذ backup سليماً، ثم استعد آخر نسخة معتمدة بعد integrity check. أي rollback يجب أن يعيد release state إلى `not_ready` أو `shadow_only`.

## incident runbook

عند توقف worker أو تأخر المصدر أو فساد ledger أو فشل Telegram، يُفعّل kill switch ويُحفظ وقت الحادثة وcommit وstate وhealth snapshot. يمنع التشغيل المزدوج، ويُفحص backup قبل الاستعادة، وتُراجع أسباب quarantine وretry/dead-letter. لا تُرسل رسالة إدارية إلى قناة العملاء، ولا يُكشف token أو authorization أو internal path. لا تُرفع الحالة إلى closed beta أو commercial service أثناء حادث مفتوح.

## الاختبارات

تختبر دورة 47 ترتيب حالات gate، وغياب المصدر، وفشل provenance والجودة والعمليات، والانتقال shadow/closed beta، واشتراط الموافقة الصريحة، وkill switch الافتراضي، والكتابة الذرية، والملف الفاسد. لا تختبر إرسالاً حقيقياً ولا تحتاج credentials.

## حدود النطاق

لا تشمل الدورة إطلاقاً عاماً، أو تجربة مستخدمين حقيقية، أو Telegram test channel حقيقياً، أو مصدر بيانات حي، أو قرار ربحية، أو تغيير نموذج أو policy. `2526` خارج tuning/selection/calibration و`2627` محجوز، و`commercial_release=false` ثابت.
