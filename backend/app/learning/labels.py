"""İP-4.2 — Hekim onay/düzeltmelerinden RLHF etiket üretimi (veri toplama döngüsü).

Shadow Mode'da hekim, AI taslağı için bir karar verir (onay / düzeltme / ret);
bu kararlar `ClinicalModelFeedback` olarak `training_status="pending_redaction"`
ile mahremiyet-güvenli kuyruğa alınır (bkz. `services/clinical_feedback_service`).

Bu modül o kararları **etiketli eğitim örneklerine** çevirir. İki değişmez:

1. **Mahremiyet kapısı:** ham hasta metni asla kopyalanmaz — yalnızca review_id
   referansı + niyet etiketi + karar tutulur. `pending_redaction` (redaksiyon
   onayı verilmemiş) kayıtlar etiket setine ALINMAZ; insan onayını bekler.
2. **Determinizm:** aynı girdi → aynı artefakt (timestamp yok, sıralı, diff'lenebilir).

Saf Python; numpy/sklearn yok ve DB import'u yalnızca opsiyonel adaptörün içinde
(çekirdek mantık DB'siz test edilir — `--noconftest` ile koşar).

CLI:  python -m app.learning.labels   (sentetik örnekten denetim panosu + artefakt)
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# ── Hekim kararı (ShadowReviewStatus.value ile birebir hizalı) ──────────────
OUTCOME_APPROVED = "approved"
OUTCOME_EDITED = "edited"
OUTCOME_REJECTED = "rejected"
VALID_OUTCOMES = frozenset({OUTCOME_APPROVED, OUTCOME_EDITED, OUTCOME_REJECTED})

# ── Mahremiyet kapısı: yalnızca redaksiyon-onaylı kayıtlar eğitilebilir ─────
# ClinicalModelFeedback.training_status default'u "pending_redaction".
PENDING_REDACTION = "pending_redaction"
TRAINING_READY = "redaction_approved"
READY_STATUSES = frozenset({TRAINING_READY, "approved_for_training"})

# ── Etiket tipleri ──────────────────────────────────────────────────────────
LABEL_POSITIVE = "positive_confirm"   # hekim onayladı → model niyeti doğrulandı
LABEL_CORRECTION = "correction"       # hekim düzeltti → düzeltme sinyali
LABEL_NEGATIVE = "negative"           # hekim reddetti → negatif sinyal (insana)

OUTCOME_TO_LABEL = {
    OUTCOME_APPROVED: LABEL_POSITIVE,
    OUTCOME_EDITED: LABEL_CORRECTION,
    OUTCOME_REJECTED: LABEL_NEGATIVE,
}

ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "labels.json"


@dataclass(frozen=True)
class FeedbackRecord:
    """`ClinicalModelFeedback` satırının mahremiyet-güvenli, sağlayıcı-bağımsız görünümü.

    Ham hasta metni içermez — taşınması yasak. Yalnızca eğitilebilir sinyal alanları.
    """
    review_id: int
    intent: str
    confidence: float
    outcome: str          # approved | edited | rejected
    training_status: str  # pending_redaction | redaction_approved | ...
    has_correction: bool = False


@dataclass(frozen=True)
class LabelExample:
    review_id: int
    intent: str
    label_type: str       # positive_confirm | correction | negative
    weight: float
    source_outcome: str

    def as_dict(self) -> dict:
        return {
            "review_id": self.review_id,
            "intent": self.intent,
            "label_type": self.label_type,
            "weight": self.weight,
            "source_outcome": self.source_outcome,
        }


def is_training_ready(record: FeedbackRecord) -> bool:
    """Mahremiyet kapısı — pending_redaction ve bilinmeyen statüler ASLA geçmez."""
    return record.training_status in READY_STATUSES


def _weight_for(outcome: str, confidence: float) -> float:
    """Etiket ağırlığı [0,1]. Şimdilik tüm kararlara eşit güçlü sinyal (1.0)."""
    return 1.0


def _partition(records: Iterable[FeedbackRecord]) -> tuple[dict[int, FeedbackRecord], int, int]:
    """Kayıtları eğitilebilir / mahremiyet-tutulan / geçersiz olarak ayırır.

    Eğitilebilir küme review_id ile tekilleştirilir (son kayıt kazanır;
    `ClinicalModelFeedback` UniqueConstraint'ine uyumlu). Hem etiket üretimi hem
    istatistik aynı tekil küme üzerinden çalışır → `trainable == etiket sayısı`.
    """
    ready: dict[int, FeedbackRecord] = {}
    held = 0
    invalid = 0
    for r in records:
        if r.outcome not in VALID_OUTCOMES:
            invalid += 1
            continue
        if not is_training_ready(r):
            held += 1
            continue
        ready[r.review_id] = r  # son kayıt kazanır
    return ready, held, invalid


def build_label_dataset(records: Iterable[FeedbackRecord]) -> tuple[list[LabelExample], dict]:
    """Hekim kararlarından mahremiyet-güvenli, tekilleştirilmiş etiket seti üretir."""
    ready, held, skipped_invalid = _partition(records)
    examples = sorted(
        (
            LabelExample(
                review_id=r.review_id,
                intent=r.intent,
                label_type=OUTCOME_TO_LABEL[r.outcome],
                weight=_weight_for(r.outcome, r.confidence),
                source_outcome=r.outcome,
            )
            for r in ready.values()
        ),
        key=lambda e: e.review_id,
    )
    meta = {"privacy_held": held, "skipped_invalid": skipped_invalid}
    return examples, meta


def dataset_stats(records: Iterable[FeedbackRecord]) -> dict:
    """Sinyal kalitesi istatistikleri (tekilleştirilmiş eğitilebilir kayıtlar)."""
    records = list(records)
    total = len(records)
    ready, held, invalid = _partition(records)
    by_outcome: Counter = Counter(r.outcome for r in ready.values())
    by_intent: Counter = Counter(r.intent for r in ready.values())

    decided = len(ready)

    def rate(n: int) -> float:
        return round(n / decided, 4) if decided else 0.0

    return {
        "total_records": total,
        "trainable": decided,
        "privacy_held": held,
        "invalid_outcome": invalid,
        "by_outcome": dict(sorted(by_outcome.items())),
        "by_intent": dict(sorted(by_intent.items())),
        "approval_rate": rate(by_outcome[OUTCOME_APPROVED]),
        "edit_rate": rate(by_outcome[OUTCOME_EDITED]),
        "rejection_rate": rate(by_outcome[OUTCOME_REJECTED]),
        # Model↔hekim uyumu = niyetin düzeltmesiz onaylanma oranı.
        "agreement_rate": rate(by_outcome[OUTCOME_APPROVED]),
    }


def build_report(records: Iterable[FeedbackRecord]) -> dict:
    """Denetlenebilir etiket-üretim panosu; her kapı kendi `pass` bayrağını taşır."""
    records = list(records)
    examples, meta = build_label_dataset(records)
    stats = dataset_stats(records)

    ready_ids = {r.review_id for r in records if r.outcome in VALID_OUTCOMES and is_training_ready(r)}
    # Mahremiyet kapısı: hiçbir pending/bilinmeyen kayıt örnek setine sızmamalı.
    privacy_leak = sum(1 for e in examples if e.review_id not in ready_ids)
    # Bütünlük: etiket tipleri geçerli, ağırlık [0,1], review_id tekil.
    valid_types = {LABEL_POSITIVE, LABEL_CORRECTION, LABEL_NEGATIVE}
    bad_type = sum(1 for e in examples if e.label_type not in valid_types)
    bad_weight = sum(1 for e in examples if not (0.0 <= e.weight <= 1.0))
    unique_ids = len({e.review_id for e in examples}) == len(examples)

    privacy_pass = privacy_leak == 0 and meta["privacy_held"] == stats["privacy_held"]
    integrity_pass = bad_type == 0 and bad_weight == 0 and unique_ids

    report = {
        "name": "rlhf_label_dataset",
        "ip": "4.2",
        "collection": stats,
        "labels": {
            "count": len(examples),
            "by_label_type": dict(sorted(Counter(e.label_type for e in examples).items())),
            "examples": [e.as_dict() for e in examples],
        },
        "gates": {
            "privacy_gate": {
                "pending_leak": privacy_leak,
                "privacy_held": meta["privacy_held"],
                "target": "pending_redaction sızıntısı = 0",
                "pass": privacy_pass,
            },
            "integrity_gate": {
                "bad_label_type": bad_type,
                "bad_weight": bad_weight,
                "unique_review_ids": unique_ids,
                "target": "geçerli tip + ağırlık∈[0,1] + tekil review_id",
                "pass": integrity_pass,
            },
        },
    }
    report["overall_pass"] = bool(privacy_pass and integrity_pass)
    return report


def render(report: dict) -> str:
    """İnsan-okunur konsol panosu."""
    c = report["collection"]
    g = report["gates"]
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    lines = [
        "İP-4.2 — Hekim-döngülü RLHF etiket üretimi",
        "=" * 48,
        f"Toplam karar kaydı : {c['total_records']}",
        f"Eğitilebilir       : {c['trainable']}  (onay {c['by_outcome'].get('approved', 0)} · "
        f"düzeltme {c['by_outcome'].get('edited', 0)} · ret {c['by_outcome'].get('rejected', 0)})",
        f"Mahremiyet tutulan : {c['privacy_held']}  (pending_redaction)",
        f"Geçersiz outcome   : {c['invalid_outcome']}",
        f"Uyum (onay) oranı  : {c['agreement_rate']:.4f}  ·  düzeltme {c['edit_rate']:.4f}  ·  ret {c['rejection_rate']:.4f}",
        f"Üretilen etiket    : {report['labels']['count']}  {report['labels']['by_label_type']}",
        "-" * 48,
        f"{ok(g['privacy_gate']['pass'])} Mahremiyet kapısı  (sızıntı={g['privacy_gate']['pending_leak']})",
        f"{ok(g['integrity_gate']['pass'])} Bütünlük kapısı",
        "=" * 48,
        f"{ok(report['overall_pass'])} GENEL: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}",
    ]
    return "\n".join(lines)


def synthetic_feedback() -> list[FeedbackRecord]:
    """Hattı sergileyen ve davranışı kilitleyen deterministik örnek karar seti.

    Kapsam: onay/düzeltme/ret + mahremiyet-tutulan (pending) + geçersiz outcome
    + tekrar eden review_id (dedup testi).
    """
    return [
        FeedbackRecord(101, "book_appointment", 0.93, OUTCOME_APPROVED, TRAINING_READY),
        FeedbackRecord(102, "ask_price", 0.88, OUTCOME_APPROVED, TRAINING_READY),
        FeedbackRecord(103, "book_appointment", 0.71, OUTCOME_EDITED, TRAINING_READY, has_correction=True),
        FeedbackRecord(104, "medical_emergency", 0.64, OUTCOME_REJECTED, TRAINING_READY),
        FeedbackRecord(105, "reschedule_appointment", 0.82, OUTCOME_APPROVED, TRAINING_READY),
        FeedbackRecord(106, "ask_price", 0.55, OUTCOME_EDITED, TRAINING_READY, has_correction=True),
        FeedbackRecord(107, "cancel_appointment", 0.90, OUTCOME_APPROVED, TRAINING_READY),
        # Mahremiyet kapısında tutulanlar (redaksiyon onayı yok) → etikete GİRMEZ:
        FeedbackRecord(108, "book_appointment", 0.77, OUTCOME_APPROVED, PENDING_REDACTION),
        FeedbackRecord(109, "ask_insurance", 0.40, OUTCOME_REJECTED, PENDING_REDACTION),
        # Geçersiz outcome (henüz karar verilmemiş 'pending' shadow) → atlanır:
        FeedbackRecord(110, "unknown", 0.30, "pending", TRAINING_READY),
        # Tekrar eden review_id (son kayıt kazanır: edited):
        FeedbackRecord(102, "ask_price", 0.88, OUTCOME_EDITED, TRAINING_READY, has_correction=True),
    ]


# ── Opsiyonel DB adaptörü (gerçek döngü) — import yalnızca burada ────────────
def feedback_records_from_db(db, clinic_id: int | None = None) -> list[FeedbackRecord]:
    """`ClinicalModelFeedback` + `ShadowReview` join'inden FeedbackRecord listesi.

    Niyet/güven ShadowReview'da, karar/training_status feedback'te. Ham metin taşınmaz.
    """
    from sqlalchemy import select
    from app.models import ClinicalModelFeedback, ShadowReview

    q = select(ClinicalModelFeedback, ShadowReview).join(
        ShadowReview, ShadowReview.id == ClinicalModelFeedback.review_id
    )
    if clinic_id is not None:
        q = q.where(ClinicalModelFeedback.clinic_id == clinic_id)

    out: list[FeedbackRecord] = []
    for fb, review in db.execute(q).all():
        intent = review.intent.value if hasattr(review.intent, "value") else str(review.intent)
        out.append(
            FeedbackRecord(
                review_id=fb.review_id,
                intent=intent,
                confidence=float(review.confidence_score or 0.0),
                outcome=fb.outcome,
                training_status=fb.training_status,
                has_correction=fb.corrected_reply is not None,
            )
        )
    return out


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    """Deterministik artefakt (timestamp yok, sıralı anahtarlar)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="İP-4.2 RLHF etiket üretim panosu")
    parser.add_argument("--no-save", action="store_true", help="artefakt yazma")
    parser.add_argument("--json", action="store_true", help="JSON çıktısı")
    args = parser.parse_args(argv)

    report = build_report(synthetic_feedback())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render(report))
    if not args.no_save:
        path = write_artifact(report)
        if not args.json:
            print(f"\nArtefakt: {path}")
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
