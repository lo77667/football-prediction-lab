# Cycle 41 service fixtures

هذه fixtures اختبارية محلية فقط، وليست دليلاً على أداء نموذج أو قيمة اقتصادية. لا تحتوي odds أو ROI أو EV أو stake، ولا تُستخدم لإظهار targets في response.

| الملف أو السيناريو | الغرض |
|---|---|
| `valid_prematch.csv` | صفوف pre-match مع frozen probabilities؛ تُحوّل الاختبارات نسخة منها إلى manifest داخلي صالح |
| `past_kickoff.csv` | اختبار رفض `as_of_utc` عندما يكون kickoff ماضياً |
| `invalid_probability.csv` | اختبار رفض probability خارج [0,1] |
| `target_column.csv` | اختبار منع target من طبقة الخدمة؛ ingestion أو manifest verification يمنع القراءة غير المصرح بها |
| fingerprint خاطئ | يرفضه application قبل التشغيل |
| policy/model/feature mismatch | ترفضه عقود الخدمة والتطبيق |
| duplicate request | يعيد نفس response content hash ولا يكرر ledger prediction IDs |
| path traversal | يرفضه allowed manifest root وhealth يصبح `blocked_provenance` |
| invalid policy | يرفضه locked policy validation ولا يُستخدم في smoke |

المسار التشغيلي يقرأ manifest verified فقط، ولا يقبل CSV raw أو arbitrary feature payload من العميل، ولا يكشف labels أو مصادر شبكة.
