"""İP-1.5 — Güven kalibrasyon raporu + üretim artefaktı üretici.

Sentetik korpusta (`dental_tr.jsonl`) her senaryoyu triyajdan geçirir, eşleşme
gücünden ham güven sinyali çıkarır ve isotonic regresyonla kalibre eder.
Sızıntısız ECE ölçümü için train/test böler; üretim artefaktını ise tüm veriyle
yeniden eğitip `data/calibration.json`'a yazar. Golden set zorlu bir teşhis
(stres) olarak ayrıca raporlanır.

Başarı ölçütü (İP-1.5): TEST setinde ECE < 0,05.

Çalıştırma:
    python -m app.clinical.calibrate            # rapor + artefakt kaydet
    python -m app.clinical.calibrate --no-save  # sadece rapor (yazma yok)
"""

from __future__ import annotations

import argparse
import random

from app.clinical.calibration import (
    CALIBRATION_ARTIFACT,
    IsotonicCalibrator,
    expected_calibration_error,
    raw_confidence_signal,
)
from app.clinical.corpus.schema import corpus_data_dir, load_corpus
from app.clinical.normalizer import triage

SEED = 42
TRAIN_FRACTION = 0.6
ECE_TARGET = 0.05


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


def main() -> None:
    parser = argparse.ArgumentParser(description="İP-1.5 güven kalibrasyon raporu")
    parser.add_argument(
        "--no-save", action="store_true", help="Artefaktı diske yazma, sadece raporla"
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

    print("=" * 64)
    print("İP-1.5 — Güven Kalibrasyon Raporu (branş yönlendirici)")
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

    # Golden set — zorlu teşhis (kasıtlı anahtar-kelimesiz parafraz)
    golden = build_pairs("golden.jsonl")
    golden_calibrated = [(calibrator.predict_one(r), ok) for r, ok in golden]
    golden_acc = sum(1 for _, ok in golden if ok) / len(golden)
    print(
        f"\nGolden set (teşhis): {len(golden)} senaryo · doğruluk {golden_acc * 100:.1f}% · "
        f"ECE {expected_calibration_error(golden_calibrated):.4f}"
    )
    print("  → düşük-güven kaçışları İP-1.6 çekimser tahmin (insana yükseltme) hedefidir.")

    # Üretim artefaktı: tüm sentetik veriyle yeniden eğit (daha çok veri = daha iyi).
    if not args.no_save:
        IsotonicCalibrator.fit(pairs).save()
        print(f"\n💾 Üretim kalibratörü kaydedildi: {CALIBRATION_ARTIFACT}")


if __name__ == "__main__":
    main()
