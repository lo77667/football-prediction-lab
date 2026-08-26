# Cycle 40.1: Readiness Fingerprint Migration

## الملخص

أصلحت دورة 40.1 قابلية نقل readiness reports بين checkout أو output root مختلفين. كان التقرير السابق يضع `policy_path` المطلق داخل JSON، كما كان CLI يطبع `report_path` المطلق ضمن المخرجات. لذلك كانت bytes التقرير، ومن ثم SHA الملف، تختلف عند تغيير مكان checkout حتى عندما تكون policy والمحتوى المنطقي متطابقين.

الآن تُحفظ المفاتيح النسبية الثابتة داخل المحتوى canonical:

| الحقل | القيمة |
|---|---|
| `policy_artifact_key` | `configs/cycle40_external_source_policy.yaml` |
| `report_artifact_key` | `reports/generated/cycle_40_source_readiness.json` |
| `policy_sha256` | SHA لمحتوى policy canonical |
| `report_content_sha256` | SHA لمحتوى readiness canonical بعد استبعاد metadata التشغيلية |
| `source_commit` | commit المصدر، عندما يكون معروفاً |

## الفرق بين hashes

`report_content_sha256` هو hash منطقي قابل للنقل. يُعاد حسابه من JSON canonical UTF-8 باستخدام `sort_keys=true` وseparators ثابتة وقوائم مرتبة، مع استبعاد `runtime_metadata` وحقول المسارات وhostname وruntime timestamps وحقول self-hash. لذلك يبقى ثابتاً عندما يُعاد تشغيل الأمر من `/checkout-a` أو `/checkout-b` مع نفس policy والمحتوى والcommit.

أما **manifest file SHA** فهو hash للـbytes الفعلية لملف manifest المكتوب. ويظل منفصلاً عن report content hash. ملف manifest يربط `policy_sha256` و`report_content_sha256` وartifact keys، ويمكن حساب hash المادي له بواسطة `write_manifest`. لا يجوز استخدام manifest file SHA بديلاً عن content hash عند مقارنة checkoutات مختلفة.

| نوع الدليل | ما الذي يثبته؟ | هل يتأثر بمسار الملف؟ |
|---|---|---|
| `policy_sha256` | تطابق محتوى policy | لا |
| `report_content_sha256` | تطابق readiness content canonical | لا |
| manifest file SHA | تطابق bytes ملف manifest المحدد | يتأثر بأي byte تغيير، لكنه لا يحتوي مساراً مطلقاً |
| runtime metadata | مكان التشغيل ووقت التشغيل وhostname للتدقيق المحلي | نعم؛ خارج canonical hash |

## runtime metadata

إذا احتاج التشغيل المحلي إلى المسارات، تُحفظ داخل قسم `runtime_metadata` الاختياري، مثل `policy_path` و`report_path` و`output_root` و`hostname` و`generated_at_utc`. هذه القيم لا تدخل في `report_content_sha256` ولا تستخدم في قرار portability. أما التقرير canonical فلا يحتوي مسارات مطلقة أو أسراراً أو runtime metadata.

## التحقق المنفذ

شُغّل CLI من مسارين مختلفين للـpolicy والـoutput root، وكانت النتائج:

```text
root_a_content_hash=18e53a3ceb1eba6b495952ee727aa81b653c9f7ffb9c781ef78af4958ac3ccef
root_b_content_hash=18e53a3ceb1eba6b495952ee727aa81b653c9f7ffb9c781ef78af4958ac3ccef
policy_hash=87bea18b599cd8564936f3749bb39353c7e24ee483a369d23fcb2dbdc17431b4
portable_hash_equal=true
root_a_validation=passed
root_b_validation=passed
network_calls=none
```

كما تثبت الاختبارات أن تغيير runtime timestamp أو hostname أو absolute path لا يغير content hash، وأن تغيير policy أو counters أو status يغيره. ويعيد validator حساب policy hash وreport content hash دون مقارنة المسار المطلق.

## الحالة السياسية والتشغيلية

لم يُدخل Cycle 40.1 أي مصدر خارجي ولم ينفذ network call. بقي `external_source_status=deferred_missing_authorized_source`، وبقي `benchmark_status=deferred` و`commercial_release=false`. لم تتغير النماذج أو features أو نتائج الدورات السابقة أو policy حماية 2526/2627.
