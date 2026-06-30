"""İP-1.6 — Çekimser tahmin risk-kapsam raporu + eşik artefaktı üretici.

Sentetik korpusta (`dental_tr.jsonl`) konformal risk-kontrollü güven eşiğini
seçer (kabul edilen tahminlerde hata ≤ hedef risk), sonra hem sentetik hem de
zorlu golden sette çekimser katmanın kapsamını (coverage) ve selektif
doğruluğunu (kabul edilenlerde doğruluk) raporlar. Üretim eşiğini
`data/selective.json`'a yazar.

Başarı fikri: golden sette ham doğruluk %62,9 iken, kanıtsız/çelişkili vakaları
insana yükselterek KABUL edilen tahminlerde doğruluğu hedef riske çeker — kaçan
yanlış-yönlendirmeyi azaltır.

Çalıştırma:
    python -m app.clinical.select_report             # rapor + artefakt kaydet
    python -m app.clinical.select_report --no-save   # sadece rapor
"""

from __future__ import annotations

import argparse

from app.clinical.calibration import raw_confidence_signal
from app.clinical.corpus.schema import corpus_data_dir, load_corpus
from app.clinical.normalizer import triage
from app.clinical.selective import (
    DEFAULT_TARGET_RISK,
    SELECTIVE_ARTIFACT,
    SelectiveMetrics,
    decide,
    evaluate_selective,
    fit_threshold,
    save_threshold,
)


def _items(filename: str) -> list[tuple[str, str]]:
    return [(e.text, e.specialty_code) for e in load_corpus(corpus_data_dir() / filename)]


def _calibration_pairs(items: list[tuple[str, str]]) -> list[tuple[float, bool]]:
    """``(kalibre_güven, doğru_mu)`` ikilileri — eşik seçimi için."""
    pairs: list[tuple[float, bool]] = []
    for text, truth in items:
        result = triage(text)
        pairs.append((result.confidence, result.specialty_code == truth))
    return pairs


def _baseline_accuracy(items: list[tuple[str, str]]) -> float:
    correct = sum(1 for text, truth in items if triage(text).specialty_code == truth)
    return correct / len(items) if items else 0.0


def _format(name: str, base_acc: float, metrics: SelectiveMetrics) -> str:
    return (
        f"{name}: ham doğruluk {base_acc * 100:.1f}%  →  "
        f"kapsam {metrics.coverage * 100:.1f}% ({metrics.accepted}/{metrics.total}), "
        f"selektif doğruluk {metrics.selective_accuracy * 100:.1f}% "
        f"(risk {metrics.selective_risk * 100:.1f}%), "
        f"insana yükseltilen {metrics.abstained}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="İP-1.6 çekimser tahmin raporu")
    parser.add_argument("--no-save", action="store_true", help="Artefaktı yazma")
    parser.add_argument(
        "--target-risk", type=float, default=DEFAULT_TARGET_RISK,
        help="Kabul edilen tahminlerde hedef azami hata (varsayılan 0,05)",
    )
    args = parser.parse_args()

    synth = _items("dental_tr.jsonl")
    golden = _items("golden.jsonl")

    threshold = fit_threshold(_calibration_pairs(synth), target_risk=args.target_risk)

    print("=" * 70)
    print("İP-1.6 — Çekimser Tahmin (Selective Prediction) Risk-Kapsam Raporu")
    print("=" * 70)
    print(
        f"Konformal güven eşiği: {threshold:.4f}  "
        f"(hedef risk ≤ {args.target_risk * 100:.0f}%, sentetikte seçildi)\n"
    )

    synth_metrics = evaluate_selective(synth, threshold=threshold)
    golden_metrics = evaluate_selective(golden, threshold=threshold)
    print(_format("Sentetik", _baseline_accuracy(synth), synth_metrics))
    print(_format("Golden  ", _baseline_accuracy(golden), golden_metrics))

    # Çekimser gerekçe dağılımı (golden — asıl kazanç burada).
    from collections import Counter

    reasons: Counter = Counter()
    for text, _ in golden:
        for r in decide(text, threshold=threshold).abstain_reasons:
            reasons[r] += 1
    if reasons:
        print("\nGolden çekimser gerekçeleri:")
        for reason, count in reasons.most_common():
            print(f"  {reason:<20} {count}")

    if not args.no_save:
        save_threshold(threshold, args.target_risk)
        print(f"\n💾 Üretim eşiği kaydedildi: {SELECTIVE_ARTIFACT}")


if __name__ == "__main__":
    main()
