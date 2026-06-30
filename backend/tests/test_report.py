"""İP-1.8 — konsolide metrik panosu testleri.

Kapsam: (1) panonun dört metrik bloğunu da içermesi; (2) her bloğun standalone
üreticiyle tutarlı olması (pano değer üretmez, orkestre eder); (3) İP-1 kabul
hedeflerinin (kapıların) karşılanması; (4) JSON serileştirilebilirlik/round-trip;
(5) determinizm; (6) genel pass.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.clinical.calibrate import build_pairs, split
from app.clinical.calibration import IsotonicCalibrator, expected_calibration_error
from app.clinical.corpus.schema import corpus_data_dir, load_corpus
from app.clinical.emergency_report import CORPUS_FILES, evaluate_recall
from app.clinical.evaluate import evaluate_file
from app.clinical.report import (
    ECE_TARGET,
    EMERGENCY_RECALL_TARGET,
    METRICS_ARTIFACT,
    SELECTIVE_RISK_TARGET,
    SPECIALTY_ACCURACY_TARGET,
    SYNTHETIC_FILE,
    build_dashboard,
    overall_pass,
    render,
    save_dashboard,
)
from app.clinical.selective import evaluate_selective, load_threshold

# backend/ kökü — CLI smoke testi `python -m app.clinical.report`'u buradan koşar.
BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def dashboard() -> dict:
    return build_dashboard()


# ── Yapı: dört metrik bloğu da mevcut ────────────────────────────────────────


def test_dashboard_has_all_metric_blocks(dashboard):
    metrics = dashboard["metrics"]
    assert set(metrics) == {
        "specialty_accuracy",
        "calibration_ece",
        "emergency_recall",
        "selective",
    }
    for block in metrics.values():
        assert "pass" in block


def test_dashboard_identity_fields(dashboard):
    assert dashboard["ip"] == "1.8"
    assert dashboard["corpus"]["synthetic"] == SYNTHETIC_FILE


# ── Tutarlılık: pano == standalone üretici ───────────────────────────────────


def test_specialty_matches_evaluate(dashboard):
    synth = evaluate_file(corpus_data_dir() / SYNTHETIC_FILE)
    block = dashboard["metrics"]["specialty_accuracy"]["synthetic"]
    assert block["correct"] == synth.correct
    assert block["total"] == synth.total
    assert block["accuracy"] == pytest.approx(synth.accuracy)


def test_calibration_matches_calibrate(dashboard):
    pairs = build_pairs(SYNTHETIC_FILE)
    train, test = split(pairs)
    calibrator = IsotonicCalibrator.fit(train)
    test_calibrated = [(calibrator.predict_one(r), ok) for r, ok in test]
    expected_ece = expected_calibration_error(test_calibrated)
    assert dashboard["metrics"]["calibration_ece"]["test_ece"] == pytest.approx(expected_ece)


def test_emergency_matches_report(dashboard):
    tot_emg = tot_detected = 0
    for fname in CORPUS_FILES:
        rep = evaluate_recall(load_corpus(corpus_data_dir() / fname), fname)
        tot_emg += rep.emergencies
        tot_detected += rep.detected
    block = dashboard["metrics"]["emergency_recall"]
    assert block["emergencies"] == tot_emg
    assert block["detected"] == tot_detected


def test_selective_matches_evaluate_selective(dashboard):
    threshold = load_threshold()
    synth = [
        (e.text, e.specialty_code)
        for e in load_corpus(corpus_data_dir() / SYNTHETIC_FILE)
    ]
    m = evaluate_selective(synth, threshold=threshold)
    block = dashboard["metrics"]["selective"]["synthetic"]
    assert block["accepted"] == m.accepted
    assert block["selective_risk"] == pytest.approx(m.selective_risk)


# ── Kabul hedefleri (kapılar) ────────────────────────────────────────────────


def test_specialty_accuracy_gate(dashboard):
    block = dashboard["metrics"]["specialty_accuracy"]
    assert block["synthetic"]["accuracy"] >= SPECIALTY_ACCURACY_TARGET
    assert block["pass"] is True


def test_ece_gate(dashboard):
    block = dashboard["metrics"]["calibration_ece"]
    assert block["test_ece"] < ECE_TARGET
    assert block["pass"] is True


def test_emergency_recall_gate(dashboard):
    block = dashboard["metrics"]["emergency_recall"]
    assert block["recall"] >= EMERGENCY_RECALL_TARGET
    assert block["missed"] == 0
    assert block["pass"] is True


def test_selective_risk_gate(dashboard):
    block = dashboard["metrics"]["selective"]
    assert block["synthetic"]["selective_risk"] <= SELECTIVE_RISK_TARGET
    assert block["pass"] is True


def test_overall_pass(dashboard):
    assert dashboard["overall_pass"] is True


# ── Serileştirme / determinizm ───────────────────────────────────────────────


def test_dashboard_is_json_serializable_and_roundtrips(dashboard):
    text = json.dumps(dashboard, ensure_ascii=False)
    assert json.loads(text) == dashboard


def test_dashboard_is_deterministic():
    assert build_dashboard() == build_dashboard()


def test_save_dashboard_writes_valid_json(dashboard, tmp_path):
    path = tmp_path / "metrics_report.json"
    save_dashboard(dashboard, path=path)
    assert json.loads(path.read_text(encoding="utf-8")) == dashboard


# ── Render ───────────────────────────────────────────────────────────────────


def test_render_contains_all_sections(dashboard):
    text = render(dashboard)
    assert "Branş doğruluğu" in text
    assert "Kalibrasyon ECE" in text
    assert "Acil-recall" in text
    assert "Selektif risk" in text
    assert "GENEL" in text


# ── Negatif / kapı mantığı (gerçek veriden bağımsız) ─────────────────────────


BLOCK_NAMES = ["specialty_accuracy", "calibration_ece", "emergency_recall", "selective"]


def test_overall_pass_true_when_all_blocks_pass():
    metrics = {name: {"pass": True} for name in BLOCK_NAMES}
    assert overall_pass(metrics) is True


@pytest.mark.parametrize("failing", BLOCK_NAMES)
def test_overall_pass_false_when_any_block_fails(failing):
    """Tek bir hedef bile karşılanmazsa pano bütün olarak başarısız olmalı."""
    metrics = {name: {"pass": True} for name in BLOCK_NAMES}
    metrics[failing] = {"pass": False}
    assert overall_pass(metrics) is False


def test_render_shows_failure_marker(dashboard):
    """Bir blok başarısızsa render ❌ ve başarısızlık mesajı göstermeli."""
    broken = copy.deepcopy(dashboard)
    broken["metrics"]["emergency_recall"]["pass"] = False
    broken["overall_pass"] = overall_pass(broken["metrics"])
    text = render(broken)
    assert broken["overall_pass"] is False
    assert "❌" in text
    assert "karşılanmadı" in text


# ── CLI smoke (subprocess) ───────────────────────────────────────────────────


def test_cli_json_runs_and_emits_valid_json():
    proc = subprocess.run(
        [sys.executable, "-m", "app.clinical.report", "--no-save", "--json"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ip"] == "1.8"
    assert "overall_pass" in payload


def test_cli_no_save_does_not_write_artifact(tmp_path, monkeypatch):
    """--no-save artefakta dokunmamalı (mtime değişmez / dosya oluşmaz)."""
    before = METRICS_ARTIFACT.stat().st_mtime_ns if METRICS_ARTIFACT.exists() else None
    proc = subprocess.run(
        [sys.executable, "-m", "app.clinical.report", "--no-save"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    after = METRICS_ARTIFACT.stat().st_mtime_ns if METRICS_ARTIFACT.exists() else None
    assert after == before


# ── Sayısal değişmezler (invariants) ─────────────────────────────────────────


def test_rate_fields_within_unit_interval(dashboard):
    sp = dashboard["metrics"]["specialty_accuracy"]
    emg = dashboard["metrics"]["emergency_recall"]
    sel = dashboard["metrics"]["selective"]
    rates = [
        sp["synthetic"]["accuracy"],
        sp["golden"]["accuracy"],
        emg["recall"],
        emg["false_positive_rate"],
        sel["synthetic"]["coverage"],
        sel["synthetic"]["selective_accuracy"],
        sel["synthetic"]["selective_risk"],
        sel["golden"]["coverage"],
    ]
    for r in rates:
        assert 0.0 <= r <= 1.0


def test_count_relationships(dashboard):
    sp = dashboard["metrics"]["specialty_accuracy"]["synthetic"]
    emg = dashboard["metrics"]["emergency_recall"]
    sel = dashboard["metrics"]["selective"]["synthetic"]
    assert sp["correct"] <= sp["total"]
    assert emg["detected"] <= emg["emergencies"]
    assert emg["missed"] >= 0
    assert sel["accepted"] <= sel["total"]
    assert sel["accepted"] + sel["abstained"] == sel["total"]


# ── Artefakt tazelik kapısı (commit'lenen JSON ↔ üretici) ────────────────────


def test_committed_artifact_matches_builder(dashboard):
    """data/metrics_report.json bayatlamamalı — üretici çıktısıyla eşleşmeli."""
    if not METRICS_ARTIFACT.exists():
        pytest.skip("metrics_report.json artefaktı yok (henüz üretilmedi)")
    committed = json.loads(METRICS_ARTIFACT.read_text(encoding="utf-8"))
    assert committed == dashboard
