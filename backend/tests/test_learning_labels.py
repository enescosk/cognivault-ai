"""İP-4.2 — RLHF etiket üretimi testleri (saf-import, DB gerektirmez).

Koşum: pytest backend/tests/test_learning_labels.py --noconftest
"""

import json

import pytest

from app.learning.labels import (
    ARTIFACT_PATH,
    LABEL_CORRECTION,
    LABEL_NEGATIVE,
    LABEL_POSITIVE,
    PENDING_REDACTION,
    TRAINING_READY,
    FeedbackRecord,
    build_label_dataset,
    build_report,
    dataset_stats,
    is_training_ready,
    render,
    synthetic_feedback,
    write_artifact,
)


def _rec(review_id, intent="book_appointment", conf=0.9, outcome="approved", status=TRAINING_READY, corr=False):
    return FeedbackRecord(review_id, intent, conf, outcome, status, corr)


# ── Mahremiyet kapısı ───────────────────────────────────────────────────────
def test_pending_redaction_never_enters_labels():
    recs = [
        _rec(1, outcome="approved", status=TRAINING_READY),
        _rec(2, outcome="approved", status=PENDING_REDACTION),
        _rec(3, outcome="rejected", status=PENDING_REDACTION),
    ]
    examples, meta = build_label_dataset(recs)
    ids = {e.review_id for e in examples}
    assert ids == {1}
    assert meta["privacy_held"] == 2


def test_is_training_ready_rejects_unknown_status():
    assert is_training_ready(_rec(1, status=TRAINING_READY))
    assert not is_training_ready(_rec(1, status=PENDING_REDACTION))
    assert not is_training_ready(_rec(1, status="something_else"))


# ── Outcome → etiket eşlemesi ───────────────────────────────────────────────
def test_outcome_to_label_mapping():
    recs = [
        _rec(1, outcome="approved"),
        _rec(2, outcome="edited", corr=True),
        _rec(3, outcome="rejected"),
    ]
    examples, _ = build_label_dataset(recs)
    by_id = {e.review_id: e.label_type for e in examples}
    assert by_id == {1: LABEL_POSITIVE, 2: LABEL_CORRECTION, 3: LABEL_NEGATIVE}
    assert all(0.0 <= e.weight <= 1.0 for e in examples)


def test_invalid_outcome_skipped():
    recs = [_rec(1, outcome="approved"), _rec(2, outcome="pending")]
    examples, meta = build_label_dataset(recs)
    assert {e.review_id for e in examples} == {1}
    assert meta["skipped_invalid"] == 1


# ── Tekilleştirme (son kayıt kazanır) ───────────────────────────────────────
def test_dedup_last_wins():
    recs = [
        _rec(7, outcome="approved"),
        _rec(7, outcome="edited", corr=True),  # aynı review_id → bu kazanır
    ]
    examples, _ = build_label_dataset(recs)
    assert len(examples) == 1
    assert examples[0].label_type == LABEL_CORRECTION


# ── İstatistik tutarlılığı ──────────────────────────────────────────────────
def test_stats_consistent_with_labels():
    recs = synthetic_feedback()
    examples, _ = build_label_dataset(recs)
    stats = dataset_stats(recs)
    # değişmez: eğitilebilir kayıt sayısı = üretilen etiket sayısı
    assert stats["trainable"] == len(examples)
    assert stats["privacy_held"] == 2
    assert stats["invalid_outcome"] == 1
    # oranlar [0,1] ve onay+düzeltme+ret toplam eğitilebiliri verir
    n = stats["trainable"]
    counts = stats["by_outcome"]
    assert sum(counts.values()) == n
    assert 0.0 <= stats["agreement_rate"] <= 1.0


def test_synthetic_expected_label_counts():
    examples, _ = build_label_dataset(synthetic_feedback())
    types = sorted(e.label_type for e in examples)
    # 3 positive, 3 correction, 1 negative (dedup sonrası 7 etiket)
    assert types.count(LABEL_POSITIVE) == 3
    assert types.count(LABEL_CORRECTION) == 3
    assert types.count(LABEL_NEGATIVE) == 1
    assert len(examples) == 7


# ── Rapor kapıları ──────────────────────────────────────────────────────────
def test_report_gates_pass_on_synthetic():
    report = build_report(synthetic_feedback())
    assert report["overall_pass"] is True
    assert report["gates"]["privacy_gate"]["pass"] is True
    assert report["gates"]["privacy_gate"]["pending_leak"] == 0
    assert report["gates"]["integrity_gate"]["pass"] is True
    assert "GEÇTİ" in render(report)


def test_report_label_count_matches_collection():
    report = build_report(synthetic_feedback())
    assert report["labels"]["count"] == report["collection"]["trainable"]


# ── Determinizm + artefakt ──────────────────────────────────────────────────
def test_report_is_deterministic():
    a = build_report(synthetic_feedback())
    b = build_report(synthetic_feedback())
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_write_and_roundtrip(tmp_path):
    report = build_report(synthetic_feedback())
    path = write_artifact(report, tmp_path / "labels.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == report


def test_committed_artifact_is_fresh():
    """Commit'li labels.json ↔ üreticinin güncel çıktısı (bayatlama kapısı)."""
    if not ARTIFACT_PATH.exists():
        pytest.skip("artefakt henüz üretilmemiş")
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    fresh = build_report(synthetic_feedback())
    assert committed == fresh, "labels.json bayat — `python -m app.learning.labels` ile yenile"
