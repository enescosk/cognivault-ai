"""İP-4 — Hekim-döngülü iyileştirme katmanı (RLHF veri toplama, eşik öğrenme, no-show).

Şimdilik İP-4.2: hekim onay/düzeltmelerinden mahremiyet-güvenli etiket üretimi.
"""

from app.learning.labels import (  # noqa: F401
    FeedbackRecord,
    LabelExample,
    build_label_dataset,
    dataset_stats,
    build_report,
    is_training_ready,
    synthetic_feedback,
)
