# دورة 39: Shadow Mode محلي قابل للتدقيق

**الحالة:** مكتملة محلياً وقابلة لإعادة التشغيل، مع بقاء `commercial_release=false`.

**نطاق الدورة:** إصدار توقعات pre-match تجريبية محلية وتسجيلها بطريقة deterministic وappend-only، من دون targets أو نتائج أو odds أو ROI أو EV أو stake sizing أو تنفيذ مالي أو API أو scheduler أو مصدر خارجي.

> Shadow Mode في هذه الدورة هو مسار رصد وتجربة فقط؛ لا يعلن توصية مراهنة، ولا ينفذ صفقة، ولا يقيس عائداً مالياً.

## 1. القرار والحدود

أُعيد استخدام policy دورة 36 المقفلة كما هي، ولم تُجرَ إعادة مواءمة أو tuning أو selection أو calibration. الإصدار المقفل هو `cycle36-future-2627-policy-v1`، والمخطط هو `cycle36-future-holdout-policy-v1`. السوقان المسموحان في المسار هما BTTS وcards، وكلاهما يستخدم `selected_candidate_policy=constant_train_rate` كما هو مسجل في ملف السياسة المقفل [1].

| قيد | تطبيق دورة 39 | نتيجة التحقق |
|---|---|---|
| سياسة Cycle 36/2627 | قراءة الملف المقفل والتحقق من schema وpolicy version | ناجح |
| موسم 2526 | ليس ضمن `development_seasons`؛ لا يدخل tuning أو selection أو calibration | محمي |
| موسم 2627 | `future_holdout=["2627"]`؛ صفوفه تُتجاوز ولا تُقيّم | محجوز |
| الإصدار التجاري | الحقل ثابت على `commercial_release=false` في prediction وrun | ناجح |
| المعرفة الزمنية | `as_of_utc` و`training_cutoff` إلزاميان وصريحان، و`as_of_utc < kickoff_utc` | ناجح |
| النشاط المالي | لا odds أو ROI أو EV أو stake أو تنفيذ أو تحويل إلى قرار مالي | غير موجود |
| التشغيل الخارجي | لا API عامة أو auth أو scheduler أو worker أو مصدر شبكة | غير موجود |

المدخل التجريبي يحتوي احتمالات مجمدة باسمَي `probability_btts` و`probability_cards`. هذه القيم **مدخل pre-match مصدرّي للاختبار** وليست تدريباً جديداً، ولا استدلالاً جديداً، ولا feature list إضافية، ولا تغييراً في نموذج دورة 36. وقد وُسّع canonical record hash ليشمل تغير هذه القيم، بحيث لا يمكن تغييرها مع بقاء manifest fingerprint دون تغيير.

## 2. مسار التنفيذ

يبدأ المسار من manifest ناتج عن ingestion المحلي في دورة 38/38.1. يتحقق runner من manifest والملف processed، ويرفض أي target أو result أو عمود post-match. بعد ذلك يرتب الصفوف ترتيباً ثابتاً حسب `kickoff_utc` و`match_id`، ولا يسمح إلا بالصفوف التي تكون فيها features متاحة عند `as_of_utc`، ويستبعد kickoff الماضي أو المساوي لـ`as_of_utc`.

لكل صف صالح ولكل سوق، يتحقق runner من وجود frozen probability ومن المجال `[0,1]`. تُنشأ `ShadowPrediction` مع تعريف السوق، kickoff، as-of، training cutoff، policy/model/feature versions، مصدر manifest، وhash لمحتوى feature قبل إصدار artifact. ثم تُكتب prediction artifact وrun artifact وledger محلياً.

| الملف أو الوحدة | الوظيفة |
|---|---|
| `src/football_prediction_lab/shadow/contracts.py` | عقود Pydantic للتوقع والـrun، مع timezone-aware وقيود الترتيب الزمني ورفض commercial release |
| `src/football_prediction_lab/shadow/ledger.py` | JSONL append-only مع `GENESIS` وhash chain وidempotent append ورفض duplicate/conflict |
| `src/football_prediction_lab/shadow/runner.py` | إصدار pre-match deterministic مع policy guards، availability checks، skip reasons، وartifact immutability |
| `scripts_run_shadow.py` | تشغيل محلي بتواريخ explicit |
| `scripts_validate_shadow.py` | تحقق مستقل من artifact والـrun والـledger والـhashes |
| `scripts_replay_shadow.py` | إعادة تشغيل محلية بنفس manifest وas-of وrun-id وtraining cutoff |
| `scripts_cycle39_test_summary.py` | توليد collected/passed count من pytest الفعلي |

## 3. الحماية من التسرب والنتائج

يمنع العقد `extra="forbid"` في prediction الحقول غير المعلنة. كما يطبق runner قائمة target/post-match ممنوعة على input وartifact. لا يقرأ المسار أي labels كي يصدر prediction، ولا يضيف target أو result أو post-match field إلى prediction artifact. أسباب التخطي مسجلة كـmetadata تشغيلية، وليست labels.

توجد حماية إضافية ضد إعادة الكتابة الصامتة. إذا كان prediction artifact موجوداً للـ`run_id` نفسه، يجب أن تكون bytes مطابقة؛ وإلا يفشل التنفيذ برسالة conflict. ويعامل run artifact الحقول الزمنية runtime كبيانات تدقيق، لكنه يرفض اختلاف المحتوى الدلالي. أما ledger فيرفض mutation، يكشف كسر السلسلة، ويقبل إعادة append لنفس prediction إذا كان السجل مطابقاً.

## 4. النتيجة المحلية القابلة لإعادة التشغيل

استُخدم fixture محلي test-only يحوي ثلاث مباريات pre-match، مع availability قبل `as_of_utc=2025-01-01T12:00:00Z` وkickoffs مستقبلية. كان `training_cutoff=2024-12-31T23:59:00Z`. لم تُستخدم ساعة النظام لتحديد الأهلية الزمنية؛ ساعة النظام تظهر فقط في `started_at_utc` و`completed_at_utc` للتدقيق.

| المؤشر | القيمة |
|---|---:|
| `rows_read` في ingestion | 3 |
| `rows_accepted` | 3 |
| `rows_quarantined` | 0 |
| `rows_seen` في Shadow run | 3 |
| `predictions_issued` | 6 |
| `rows_skipped` | 0 |
| `commercial_release` | `false` |
| prediction artifact SHA-256 | `a6713cc0d57ee49001c084e74752b74d7af00a96b56eb2caaed9693a08a92548` |
| ledger SHA-256 | `26d1bfc573dd1381ea8f8124f5ebf9d89f3776b8de219765dbc019570129ec82` |
| source commit | `4fe14db29f58832576080f414096e4a1f2e3c451` |

المخرجات موجودة تحت `reports/generated/cycle_39_shadow_smoke/`. اجتاز `scripts_validate_shadow.py` التحقق المستقل، ثم اجتاز `scripts_replay_shadow.py` إعادة التشغيل بنفس المعرّف والـroot، مع بقاء output وledger SHA-256 مطابقين. لا يثبت هذا smoke run دقة تنبؤية أو ربحية؛ فهو يثبت سلامة المسار التشغيلي فقط.

## 5. أسباب التخطي التي يغطيها الاختبار

غطت اختبارات الدورة kickoff الماضي أو المساوي لـas-of، availability المفقودة أو المتأخرة، موسم 2627 المحجوز، الاحتمال المجمد المفقود أو الخارج عن المجال، target columns، timestamps naive، training cutoff غير السابق لـas-of، وتغيير policy أو commercial flag. في حالة 2627 لا يصدر runner توقعاً ولا يضيفه إلى تقييم؛ يسجل `future_holdout_reserved` فقط.

| invariant | الاختبار أو الفحص |
|---|---|
| `as_of_utc < kickoff_utc` | `ShadowPrediction` و`run_shadow` |
| `training_cutoff < as_of_utc` | عقد prediction/run وrunner |
| availability متاحة عند as-of | `features_not_available_at_as_of` |
| 2627 reserved | `future_holdout_reserved` وpolicy guard |
| لا targets/results | extra-forbid وقائمة forbidden keys |
| لا mutation | prediction artifact conflict واختبار ledger tamper |
| لا duplicate ledger | prediction ID uniqueness وidempotent append |
| input row order مستقل | sort ثابت وmanifest canonicalization |
| frozen probability مؤثر في fingerprint | اختبار ingestion مخصص |

## 6. التحقق البرمجي

تم تشغيل التحقق في `/tmp/cycle37-clean-venv` مع Python 3.12.3. مولد summary حفظ النتيجة الفعلية في `reports/generated/cycle_39_test_summary.json`، بدلاً من تثبيت عدد اختبارات في الوثيقة.

| الفحص | النتيجة |
|---|---|
| `python -m pytest -q` | `203 passed` |
| `pytest --collect-only` عبر مولد summary | `203 collected` |
| اتساق collected/passed | `203 = 203` |
| `ruff check .` | `All checks passed` |
| `python -m compileall -q src scripts_*.py` | ناجح |
| `git diff --check` | ناجح قبل الالتزام |
| `scripts_validate_shadow.py` | `validation=passed` |
| `scripts_replay_shadow.py` | `replay=passed` |

## 7. حالة CI الفعلية

بعد دفع commit التوثيق النهائي، أُطلق workflow `quality-gate` على commit `a46bd870a3536fe7590cc40b9299f435a30d92b1`. تعريف workflow يحتوي صراحة على checkout، setup Python 3.11 و3.12، تثبيت dependencies، import-path check، pytest، Ruff، compileall، وgit diff check. لكن حالة GitHub Actions الفعلية لم تصل إلى تنفيذ هذه الخطوات: run `32971090787` انتهى بـ`failure`، وكل من jobَي Python 3.11 و3.12 ظهر له `steps=[]`، ولم يوجد log تنفيذ قابل للاستخراج [2].

لذلك القرار الدقيق هو: **quality-gate مكتوب صراحة في المستودع، لكن CI البعيد ما زال runner-blocked وغير مثبت التنفيذ**. لا تُعد هذه الدورة CI ناجحة، ولا تُنسب المشكلة إلى pytest أو Ruff أو الكود المحلي، لأن سجل التنفيذ لم يبدأ.

## 8. القرار المرحلي

تُغلق Cycle 39 من ناحية Shadow Mode المحلي: العقود، التوقيت، policy guards، ledger، idempotency، artifacts، replay، الاختبارات، والتوثيق موجودة وقابلة للتحقق. لا يوجد قرار commercial release، ولا تقييم 2526، ولا كشف 2627، ولا metric أو target في artifact. تبقى صلاحية CI البعيد نقطة بنية تشغيلية منفصلة، ويجب ألا تُسجل كنجاح إلى أن يظهر job log فعلي ينفذ الأوامر المحددة.

### المراجع

[1]: ../configs/cycle36_future_holdout_policy.json "سياسة Cycle 36/2627 المقفلة"
[2]: https://github.com/lo77667/football-prediction-lab/actions/runs/32971090787 "GitHub Actions quality-gate run 32971090787"
