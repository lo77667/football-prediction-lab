# خطة توحيد السكربتات

هذه القائمة أُنشئت قبل أي حذف أو دمج. الغرض الأول هو توثيق العائلات المتقاربة وظيفياً؛ لا يعني التشابه الاسمي أن النتائج متكافئة.

| العائلة المرشحة | الملفات الحالية | القرار الحالي |
|---|---|---|
| مقارنة BTTS | `scripts_compare_btts_ablation.py`, `scripts_compare_btts_hybrid.py`, `scripts_compare_btts_multiseason.py`, `scripts_compare_btts_variants.py` | نقل فقط الآن؛ يلزم diff سلوكي وartifact comparison قبل أي دمج. |
| مقارنة البطاقات | `scripts_compare_cards_ablation.py`, `scripts_compare_cards_multiseason.py` | نقل فقط الآن؛ لا حذف ولا تغيير نتائج. |
| walk-forward BTTS | `scripts_walk_forward.py`, `scripts_walk_forward_calibrated_btts.py`, `scripts_walk_forward_platt_btts.py`, `scripts_walk_forward_selected_btts.py`, `scripts_walk_forward_tuned.py`, `scripts_walk_forward_window_selected_btts.py` | نقل فقط الآن؛ تبقى سياسات الزمن و2526/2627 منفصلة حتى تثبت التكافؤ. |
| bootstrap/calibration | `scripts_bootstrap_platt_cards_vs_constant.py`, `scripts_bootstrap_platt_vs_constant.py`, `scripts_bootstrap_uncertainty.py`, `scripts_calibrate_btts_holdout.py` | لا دمج قبل مقارنة المخرجات والمخططات والـseeds. |
| التقييمات الدورية | `scripts_evaluate_cycle33.py`, `scripts_evaluate_cycle34_nested.py`, `scripts_evaluate_cycle35_holdout.py`, `scripts_evaluate_cycle36_candidates.py` | تاريخية؛ تحتفظ بها البنية الجديدة دون حذف. |
| الإدخال والتحقق | `scripts_ingest_local.py`, `scripts_ingest_season_file.py`, `scripts_validate_ingestion.py`, `scripts_validate_season.py`, `scripts_validate_shadow.py` | نقل فقط؛ يلزم تحديث المسارات واختبار الاستيراد. |
| التشغيل والعمليات | `scripts_run_shadow.py`, `scripts_run_local_shadow.py`, `scripts_run_worker.py`, `scripts_run_worker_smoke.py`, `scripts_run_service_smoke.py`, `scripts_serve_local_api.py`, `scripts_backup_sqlite.py`, `scripts_restore_sqlite.py` | نقل فقط؛ لا تغيير لعقود التشغيل أو kill switch. |
| OpenLigaDB وAI | `scripts_run_openligadb_readiness.py`, `scripts_test_openligadb_now.py`, `scripts_run_ai_shadow_probe.py`, `scripts_run_ai_shadow_pipeline.py`, `scripts_record_shadow_result.py`, `scripts_run_telegram_adapter_smoke.py` | مسار حديث؛ لا دمج مع سكربتات تاريخية قبل تثبيت العقود. |

## قواعد الدمج اللاحقة

لا يُحذف أي ملف إلا بعد ربطه بتقرير أو artifact تاريخي، وتشغيل النسخة القديمة والجديدة على نفس المدخلات، ومقارنة المخرجات canonical، وإضافة اختبار regression. لا يجوز تعديل `TARGET_COLUMNS` أو `POST_MATCH_AUDIT_COLUMNS` أو سياسات منع التسرب ضمن عملية التنظيم.

في هذه الدورة تُنفذ إعادة تسمية ونقل فقط. أي توحيد فعلي عبر `--mode` يُؤجل إلى دورة منفصلة بعد مراجعة النتائج، ولا تُحذف الملفات القديمة لمجرد تشابه أسمائها.
