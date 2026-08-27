# دورة 40.2: تصحيح تسليم الأرشيف ومطابقة provenance

## الهدف

هذه الدورة تصحح تسليم الأرشيف فقط. لا تغيّر models أو features أو readiness logic أو metrics أو policy 2526/2627، ولا تدخل مصدراً خارجياً ولا تنفذ network call خاصاً بالمصدر.

## سبب التصحيح

الأرشيف السابق المنسوب إلى دورة 40.1 كان مبنياً من commit أقدم من HEAD المعلن، ولذلك احتوى `SOURCE_COMMIT.txt` على commit سابق ولم يحتوي implementation/evidence كاملة لـ40.1. كان ذلك خللاً في provenance للتسليم، لا حكماً على منطق إصلاح 40.1.

## آلية المطابقة

يحتوي المستودع على `SOURCE_COMMIT.txt` بالمحتوى `$Format:%H$`، ويحدد `.gitattributes` له `export-subst`. عند استخدام:

```bash
git archive --format=zip --prefix=football-prediction-lab/ HEAD \\
  -o football-prediction-lab-cycle40.2-full-source.zip
```

يُستبدل marker تلقائياً بــ`git rev-parse HEAD` الخاص بالـarchive نفسه. لا يُكتب marker يدوياً ولا يُغيّر لمجرد تمرير فحص.

## معيار provenance

يجب أن يساوي:

```bash
unzip -p football-prediction-lab-cycle40.2-full-source.zip \\
  football-prediction-lab/SOURCE_COMMIT.txt
```

ناتج:

```bash
git rev-parse HEAD
```

الخاص بالـHEAD الذي بُني منه الأرشيف. بعد فك الأرشيف إلى مسار معزول، يجب أن يشير import إلى `src/football_prediction_lab` داخل ذلك المسار، لا إلى checkout أو site-package قديم.

## محتوى الأرشيف المقبول

يجب أن يحتوي Full Source Bundle على `src/` و`tests/` وscripts و`pyproject.toml` و`requirements.lock`، إضافة إلى implementation وtests وmigration note وportability evidence الخاصة بـCycle 40.1، ومنها `report_content_sha256` و`runtime_metadata` و`cycle_40_1_portability_evidence.txt`.

## التحقق المطلوب

تُفحص سلامة ZIP بـ`unzip -t`، ثم يُنشأ venv جديد بعد فك الأرشيف ويُثبت من `requirements.lock` ومن الحزمة المحلية. يجب أن تنجح اختبارات pytest وRuff وcompileall من الأرشيف نفسه، ويجب أن تبقى readiness:

```text
external_source_status=deferred_missing_authorized_source
source_count=0
raw_rows=0
valid_rows=0
matched_rows=0
benchmark_status=deferred
commercial_release=false
```

يجب كذلك أن يظل portability content hash متطابقاً بين root_a وroot_b، وأن تظل absolute paths وruntime timestamps وhostname خارج canonical report hash. لا تُقبل أي odds أو EV أو ROI أو stake sizing أو معاملة مالية.

## القرار

Cycle 40.2 تصحيح provenance وتسليم فقط. لا تُعتبر CI ناجحة إذا ظهر runner failure أو `steps=[]`، بل تُسجل الحالة كما هي. لا يجوز إرسال ZIP دورة 40 القديمة مع مستندات 40.1، ولا يجوز اعتبار مستند منفصل دليلاً على محتوى archive مختلف عنه.
