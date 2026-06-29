"""İP-1.5 / İP-1.6 / İP-1.8 — Güven kalibrasyon raporu + üretim artefaktı üretici.

Sentetik korpusta (`dental_tr.jsonl`) her senaryoyu triyajdan geçirir, eşleşme
gücünden ham güven sinyali çıkarır ve isotonic regresyonla kalibre eder.
Sızıntısız ECE ölçümü için train/test böler; üretim artefaktını ise tüm veriyle
yeniden eğitip `data/calibration.json`'a yazar. Golden set zorlu bir teşhis
(stres) olarak ayrıca raporlanır.

İP-1.6: Test seti üzerinden conformal abstention eşiği hesaplanır ve artefakta
yazılır. Güveni bu eşiğin altında kalan tahminler çekimser (abstain=True) →
otomatik insan yükseltme.

İP-1.8: JSON rapor (`data/calibration_report.json`) — ECE, doğruluk, branş
başarımı, acil-recall, conformal eşik istatistikleri.

Başarı ölçütü (İP-1.5): TEST setinde ECE < 0,05.

Çalıştırma:
    python -m app.clinical.calibrate            # rapor + artefakt + JSON rapor kaydet
    python -m app.clinical.calibrate --no-save  # sadece ekran raporu (yazma yok)
"""

from __future__ import annotations

import argparse
import json
import random

from app.clinical.calibration import (
    CALIBRATION_ARTIFACT,
    IsotonicCalibrator,
    compute_abstain_threshold,
    expected_calibration_error,
    raw_confidence_signal,
)
from app.clinical.corpus.schema import corpus_data_dir, load_corpus
from app.clinical.normalizer import triage

SEED = 42
TRAIN_FRACTION = 0.6
ECE_TARGET = 0.05
ABSTAIN_COVERAGE = 0.90  # İP-1.6: %90 doğruluk garantisi

REPORT_PATH = CALIBRATION_ARTIFACT.parent / "calibration_report.json"


def build_pairs(filename: str) -> list[tuple[float, bool]]:
    """Korpus dosyasından ``(ham_güven_sinyali, tahmin_doğru_mu)`` ikilileri.

    Sinyal, kararın verildiği zenginleştirilmiş metin üzerinden hesaplanır
    (triyajla bire bir tutarlı).
    """
    pairs: list[tuple[float, bool]] = []
    for entry in load_corpus(corpus_data_dir() / filename):
        result = triage(entry.text)
        raw = raw_confidence_signal(result.enriched_text)
        pairs.append((raw, result.specialty_code == entry.specialty_code))
    return pairs


def split(
    pairs: list[tuple[float, bool]], fraction: float = TRAIN_FRACTION, seed: int = SEED
) -> tuple[list[tuple[float, bool]], list[tuple[float, bool]]]:
    """Deterministik (tohumlu) train/test bölmesi."""
    order = list(range(len(pairs)))
    random.Random(seed).shuffle(order)
    cut = int(len(order) * fraction)
    return [pairs[i] for i in order[:cut]], [pairs[i] for i in order[cut:]]


def reliability_table(pairs: list[tuple[float, bool]], n_bins: int = 10) -> str:
    """Kalibre güven binlerini güven/doğruluk/adet olarak tablolar."""
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for conf, correct in pairs:
        bins[min(int(conf * n_bins), n_bins - 1)].append((conf, correct))
    lines = ["  bin           n   ort.güven  doğruluk   |fark|"]
    for i, b in enumerate(bins):
        if not b:
            continue
        avg_conf = sum(c for c, _ in b) / len(b)
        acc = sum(1 for _, ok in b if ok) / len(b)
        lines.append(
            f"  [{i / n_bins:.1f}-{(i + 1) / n_bins:.1f})  {len(b):>4}    "
            f"{avg_conf * 100:5.1f}%    {acc * 100:5.1f}%    {abs(acc - avg_conf) * 100:4.1f}%"
        )
    return "\n".join(lines)


def branch_accuracy_breakdown(filename: str, calibrator: IsotonicCalibrator) -> dict[str, dict]:
    """Branş bazında doğruluk, abstain oranı ve örnek sayısı."""
    breakdown: dict[str, dict] = {}
    for entry in load_corpus(corpus_data_dir() / filename):
        result = triage(entry.text)
        raw = raw_confidence_signal(result.enriched_text)
        conf = calibrator.predict_one(raw)
        correct = result.specialty_code == entry.specialty_code
        abstain = conf < calibrator.abstain_threshold
        b = breakdown.setdefault(entry.specialty_code, {"total": 0, "correct": 0, "abstained": 0})
        b["total"] += 1
        b["correct"] += int(correct)
        b["abstained"] += int(abstain)
    for b in breakdown.values():
        b["accuracy"] = round(b["correct"] / b["total"], 4) if b["total"] else 0.0
        b["abstain_rate"] = round(b["abstained"] / b["total"], 4) if b["total"] else 0.0
    return breakdown


def emergency_recall(filename: str) -> dict:
    """Acil senaryolarda triage() recall + abstain istatistikleri."""
    total = correct = abstained = 0
    calibrator = IsotonicCalibrator.load()
    for entry in load_corpus(corpus_data_dir() / filename):
        if entry.urgency != "emergency":
            continue
        result = triage(entry.text)
        total += 1
        correct += int(result.urgency.value == "emergency")
        if calibrator:
            raw = raw_confidence_signal(result.enriched_text)
            conf = calibrator.predict_one(raw)
            abstained += int(conf < calibrator.abstain_threshold)
    return {
        "total": total,
        "recalled": correct,
        "recall": round(correct / total, 4) if total else 0.0,
        "abstained": abstained,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="İP-1.5/1.6/1.8 güven kalibrasyon raporu")
    parser.add_argument(
        "--no-save", action="store_true", help="Artefakt + JSON raporu diske yazma"
    )
    args = parser.parse_args()

    pairs = build_pairs("dental_tr.jsonl")
    train, test = split(pairs)
    calibrator = IsotonicCalibrator.fit(train)

    test_calibrated = [(calibrator.predict_one(r), ok) for r, ok in test]
    max_raw = max((r for r, _ in pairs), default=1.0) or 1.0
    test_naive = [(min(r / max_raw, 1.0), ok) for r, ok in test]

    ece_before = expected_calibration_error(test_naive)
    ece_after = expected_calibration_error(test_calibrated)

    # İP-1.6 — Conformal abstention eşiği (test seti üzerinden)
    abstain_t = compute_abstain_threshold(test_calibrated, coverage=ABSTAIN_COVERAGE)
    n_abstain = sum(1 for c, _ in test_calibrated if c < abstain_t)
    above_t = [(c, ok) for c, ok in test_calibrated if c >= abstain_t]
    above_acc = sum(ok for _, ok in above_t) / len(above_t) if above_t else 0.0

    print("=" * 64)
    print("İP-1.5/1.6/1.8 — Güven Kalibrasyon Raporu (branş yönlendirici)")
    print("=" * 64)
    accuracy = sum(1 for _, ok in pairs if ok) / len(pairs)
    print(
        f"Sentetik korpus: {len(pairs)} senaryo · doğruluk {accuracy * 100:.1f}% · "
        f"train {len(train)} / test {len(test)} (tohum={SEED})"
    )
    print(f"\nTEST seti ECE (kalibrasyon öncesi, naif norm): {ece_before:.4f}")
    status = "✅ HEDEF KARŞILANDI" if ece_after < ECE_TARGET else "❌ HEDEF KARŞILANMADI"
    print(f"TEST seti ECE (isotonic sonrası):              {ece_after:.4f}  "
          f"(hedef <{ECE_TARGET}) {status}")
    print("\nGüvenilirlik tablosu (TEST, kalibrasyon sonrası):")
    print(reliability_table(test_calibrated))

    print(f"\n── İP-1.6 Conformal Abstention (coverage≥{ABSTAIN_COVERAGE:.0%}) ──")
    print(f"  Abstention eşiği: {abstain_t:.4f}")
    print(f"  Test'te çekimser: {n_abstain}/{len(test)} (%{n_abstain / len(test) * 100:.1f})")
    print(f"  Eşik üstü doğruluk: {above_acc * 100:.1f}%  (hedef ≥{ABSTAIN_COVERAGE:.0%})")

    # Golden set
    golden = build_pairs("golden.jsonl")
    golden_calibrated = [(calibrator.predict_one(r), ok) for r, ok in golden]
    golden_acc = sum(1 for _, ok in golden if ok) / len(golden)
    golden_abstain = sum(1 for c, _ in golden_calibrated if c < abstain_t)
    print(
        f"\nGolden set (teşhis): {len(golden)} senaryo · doğruluk {golden_acc * 100:.1f}% · "
        f"ECE {expected_calibration_error(golden_calibrated):.4f} · "
        f"çekimser {golden_abstain}/{len(golden)}"
    )

    # Üretim artefaktı: tüm sentetik veriyle yeniden eğit, eşiği ekle.
    if not args.no_save:
        prod_calibrator = IsotonicCalibrator.fit(pairs)
        # Abstain threshold'u prod kalibratörüne ekle (test setiyle hesaplandı)
        prod_pairs_calibrated = [(prod_calibrator.predict_one(r), ok) for r, ok in test]
        prod_threshold = compute_abstain_threshold(prod_pairs_calibrated, coverage=ABSTAIN_COVERAGE)
        from dataclasses import replace as dc_replace
        prod_calibrator = dc_replace(
            prod_calibrator,
            abstain_threshold=prod_threshold,
            abstain_coverage=ABSTAIN_COVERAGE,
        )
        prod_calibrator.save()
        print(f"\n💾 Üretim kalibratörü kaydedildi: {CALIBRATION_ARTIFACT}")
        print(f"   abstain_threshold={prod_threshold:.4f}  coverage≥{ABSTAIN_COVERAGE:.0%}")

        # İP-1.8 — JSON rapor
        breakdown = branch_accuracy_breakdown("dental_tr.jsonl", prod_calibrator)
        emer_stats = emergency_recall("dental_tr.jsonl")
        report = {
            "generated": "calibrate.py",
            "corpus": "dental_tr.jsonl",
            "n_total": len(pairs),
            "n_train": len(train),
            "n_test": len(test),
            "seed": SEED,
            "overall_accuracy": round(accuracy, 4),
            "ece_naive": round(ece_before, 4),
            "ece_calibrated": round(ece_after, 4),
            "ece_target": ECE_TARGET,
            "ece_ok": ece_after < ECE_TARGET,
            "abstain_threshold": round(prod_threshold, 4),
            "abstain_coverage_target": ABSTAIN_COVERAGE,
            "abstain_rate_test": round(n_abstain / len(test), 4) if test else 0.0,
            "accuracy_above_threshold": round(above_acc, 4),
            "golden_accuracy": round(golden_acc, 4),
            "golden_ece": round(expected_calibration_error(golden_calibrated), 4),
            "golden_abstain_rate": round(golden_abstain / len(golden), 4) if golden else 0.0,
            "emergency_recall": emer_stats,
            "branch_accuracy": breakdown,
        }
        REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"📊 JSON rapor kaydedildi: {REPORT_PATH}")


if __name__ == "__main__":
    main()
