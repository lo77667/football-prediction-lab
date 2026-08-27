# دورة 37 — GitHub Actions Quality Gate

## الحكم التنفيذي

أُصلح workflow الخاص بـGitHub Actions ليحتوي quality gate صريحًا وقابلًا للفحص الساكن، مع jobs matrix حقيقية لـPython 3.11 و3.12 وخطوات تنفيذ معلنة لـcheckout والتثبيت وimports وpytest وRuff وcompileall. كما أُضيف فاحص ثابت يمنع عودة jobs الفارغة أو reusable workflow غير المحلول أو الأسرار أو `continue-on-error`.

لكن **لم تُغلق قابلية التحقق من CI عن بُعد** بعد: أحدث runs ما زالت تنشئ jobs ثم تفشل قبل تخصيص runner، مع `runner_id=0` و`runner_name` فارغ و`steps=[]` وعدم وجود log. لذلك لا يُدّعى نجاح GitHub Actions، رغم نجاح الفحوص المحلية داخل venv نظيفة.

> النتيجة: workflow أصبح صحيح البنية وقابلًا للتنفيذ نظريًا، لكن دليل CI الفعلي ما زال محجوزًا بسبب runner/تهيئة GitHub Actions.

## فحص الحالة السابقة

كان الملف الوحيد في `.github/workflows/` هو `quality-gate.yml`. وكان يحتوي job باسم `test-and-lint` وmatrix لإصداري Python، لكنه لم يتضمن `workflow_dispatch`، وكان يعتمد على `cache-dependency-path: pyproject.toml`، ويثبت extras مباشرة دون استخدام lock. كما احتوى خطوة debug بعد الفشل، لكنها لم تُنتج logs عندما فشل runner قبل بدء أي خطوة.

السبب المثبت لـ`steps: []` ليس نقصًا في تعريف steps داخل YAML؛ فالـjobs تظهر في GitHub Actions بالأسماء والmatrix. السبب هو فشل تخصيص runner قبل بدء التنفيذ: jobs تبدأ وتنتهي خلال ثوانٍ، `runner_id=0`، `runner_name` فارغ، وendpoint logs يعيد `log not found`. هذا دليل فشل runner/تهيئة، لا دليل فشل pytest أو Ruff.

## workflow الجديد

يعمل `.github/workflows/quality-gate.yml` عند push إلى `main`، وpull request إلى `main`، و`workflow_dispatch`. يستخدم `permissions: contents: read`، ولا يطلب secrets أو permissions إضافية، ولا يستخدم reusable workflow أو `continue-on-error`.

يحتوي job واحدًا بمصفوفة فعلية لإصداري Python `3.11` و`3.12`، ولكل قيمة في المصفوفة تسع خطوات تنفيذ محددة:

| الترتيب | الخطوة | التنفيذ |
|---:|---|---|
| 1 | Checkout | `actions/checkout@v4` |
| 2 | Python setup | `actions/setup-python@v5` مع `cache: pip` و`requirements.lock` |
| 3 | Execution context | طباعة runner وevent وref وSHA وإصدار Python وpip |
| 4 | Locked install | ترقية pip، تثبيت `requirements.lock`، ثم `pip install -e '.[dev]'` و`pip check` |
| 5 | Import path | طباعة مساري الحزمة ووحدة Cycle 36 |
| 6 | Tests | `python -m pytest -q` |
| 7 | Lint | `ruff check .` |
| 8 | Compile | `python -m compileall -q src scripts` و`src scripts_*.py` |
| 9 | Whitespace | `git diff --check` |

لا يحتوي workflow على بيانات محلية أو secrets، ولا يعيد تشغيل أي تقييم تاريخي أو يستخدم موسم `2526` في التطوير.

## dependency lock

أُضيفت `SQLAlchemy==2.0.52` و`greenlet==3.5.4` إلى `requirements.lock` لأن أحدث main كان قد أضاف dependency معلنة في `pyproject.toml` لوحدة player warehouse؛ وبدونها يفشل التثبيت المحلي والـCI عند جمع الاختبارات بـ`ModuleNotFoundError: sqlalchemy`. هذا تغيير packaging ضروري للـquality gate وليس تغييرًا في نموذج تنبؤ أو feature list أو artifacts الدورات السابقة.

## التحقق المحلي

شُغّل الفاحص `scripts/verify_cycle37_workflow.py` ونجح:

```text
cycle37_workflow_static_check=passed
jobs=1 steps=9
```

كما أُنشئت venv نظيفة (`/tmp/cycle37-clean-venv`) وثُبّتت dependencies من lock، ثم نُفذت الأوامر التالية:

```text
python -m pytest -q              -> 176 passed
ruff check .                     -> All checks passed!
python -m compileall -q src scripts -> passed
python -m compileall -q src scripts_*.py -> passed
git diff --check                -> passed
```

العدد 176 يعكس الحالة الحالية الكاملة للمستودع بعد إضافة اختبارات warehouse في commits بعيدة سبقت إصلاح دورة 37. لا توجد تغييرات في خوارزميات Cycle 33–36 ضمن commits دورة 37.

## تحقق GitHub Actions الفعلي

في اختبار workflow الجديد، أُنشئ run `32917577143` على commit `8cb4294`، لكنه انتهى failure مع jobَي Python و`steps=[]`. أُعيد تشغيله، فبقي failure مع attempt 2 و`steps=[]` و`log not found`.

بعد تبديل runner label من `ubuntu-22.04` إلى `ubuntu-latest`، أُنشئ run `32917685527`، وبقيت jobs بلا خطوات تنفيذ. وبعد تحديث lock، أُنشئ run `32917832139` على commit `5bce697`، وبقيت النتيجة نفسها في آخر اختبار workflow وlock قبل commit هذا التقرير:

| job | conclusion | steps | runner |
|---|---|---:|---|
| Test and lint (Python 3.12) | failure | 0 | `runner_id=0` |
| Test and lint (Python 3.11) | failure | 0 | `runner_id=0` |

أعاد `gh run view --log-failed` رسالة `log not found`. لذلك لم تظهر logs تحتوي تنفيذ pytest أو Ruff، ولا يمكن اعتبار CI ناجحًا أو فاشلًا على مستوى الكود. الفشل الحالي قبل execution boundary.

## سلامة النطاق

تغييرات دورة 37 محصورة في:

| الملف | الغرض |
|---|---|
| `.github/workflows/quality-gate.yml` | quality gate صريح وmatrix وtriggers كاملة |
| `scripts/verify_cycle37_workflow.py` | فحص ساكن يمنع workflow غير القابل للتحقق |
| `requirements.lock` | إغلاق dependency موجودة في `pyproject.toml` كي ينجح التثبيت |
| `docs/cycle_37_quality_gate.md` | هذا التقرير |

لم تُعدّل نماذج أو features أو artifacts أو نتائج دورات 33–36، ولم تُعدّل policy 2627. بقيت `commercial_release=false`، ولم تدخل secrets أو data محلية إلى workflow.

## القرار

تم إصلاح بنية quality gate، وأصبح workflow يحدد خطوات فعلية صريحة. أما معيار القبول النهائي المتعلق بظهور logs CI الحقيقية فلم يتحقق بسبب runner allocation failure المتكرر. لا يجوز إغلاق دورة 37 بوصفها CI-passed قبل أن يظهر run فيه `steps` فعلية وlogs للأوامر ونتائج pytest وRuff. الفحوص المحلية الناجحة لا تستبدل دليل GitHub Actions المطلوب.

## المراجع الداخلية

[1]: ../.github/workflows/quality-gate.yml "Cycle 37 executable quality gate"
[2]: ../scripts/verify_cycle37_workflow.py "Static workflow verifier"
[3]: ../requirements.lock "Locked dependencies"
[4]: ../pyproject.toml "Project dependency declarations"
[5]: cycle_36_2_reproducibility.md "Cycle 36.2 reproducibility baseline"
