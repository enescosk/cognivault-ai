"""İP-1.7 — Acil-recall kapsama raporu (kaçan acil ≈ 0).

Tüm korpus dosyalarında (sentetik + golden + adversarial) aciliyet motorunu
(`normalizer.triage` → `assess_urgency`) koşturur ve acil tespiti için
recall (kaçan acil ≈ 0 hedefi) ile yanlış-pozitif oranını raporlar.

Başarı ölçütü (İP-1.7): acil-recall ≈ %100 (kaçan acil ≈ 0). Yanlış-pozitif
(rutin/öncelik → acil) düşük tutulur ama recall önceliklidir: kaçan bir acil,
gereksiz bir insan-yükseltmesinden çok daha maliyetlidir.

Çalıştırma:
    python -m app.clinical.emergency_report
"""

from __future__ import annotations

from dataclasses import dataclass

from app.clinical.corpus.schema import CorpusEntry, corpus_data_dir, load_corpus
from app.clinical.normalizer import triage
from app.clinical.ontology import UrgencyLevel

CORPUS_FILES = ("dental_tr.jsonl", "golden.jsonl", "emergency_adversarial.jsonl")


@dataclass(frozen=True)
class RecallReport:
    """Bir korpusun acil-recall özeti."""

    name: str
    emergencies: int          # gerçek (etiketli) acil sayısı
    detected: int             # doğru tespit edilen acil
    false_positives: int      # acil olmayanı acil sanma
    non_emergencies: int      # acil olmayan toplam
    missed: tuple[CorpusEntry, ...]

    @property
    def recall(self) -> float:
        return self.detected / self.emergencies if self.emergencies else 1.0

    @property
    def false_positive_rate(self) -> float:
        return self.false_positives / self.non_emergencies if self.non_emergencies else 0.0


def evaluate_recall(entries: list[CorpusEntry], name: str) -> RecallReport:
    """Bir korpusta acil tespitinin recall ve yanlış-pozitifini ölçer."""
    emergencies = detected = false_positives = non_emergencies = 0
    missed: list[CorpusEntry] = []
    for e in entries:
        predicted = triage(e.text).urgency
        is_emergency_truth = e.urgency == UrgencyLevel.EMERGENCY.value
        is_emergency_pred = predicted == UrgencyLevel.EMERGENCY
        if is_emergency_truth:
            emergencies += 1
            if is_emergency_pred:
                detected += 1
            else:
                missed.append(e)
        else:
            non_emergencies += 1
            if is_emergency_pred:
                false_positives += 1
    return RecallReport(
        name=name,
        emergencies=emergencies,
        detected=detected,
        false_positives=false_positives,
        non_emergencies=non_emergencies,
        missed=tuple(missed),
    )


def main() -> None:
    print("=" * 70)
    print("İP-1.7 — Acil-Recall Kapsama Raporu (kaçan acil ≈ 0)")
    print("=" * 70)
    tot_emg = tot_detected = tot_fp = tot_non = 0
    for fname in CORPUS_FILES:
        report = evaluate_recall(load_corpus(corpus_data_dir() / fname), fname)
        tot_emg += report.emergencies
        tot_detected += report.detected
        tot_fp += report.false_positives
        tot_non += report.non_emergencies
        status = "✅" if not report.missed else "❌"
        print(
            f"{status} {fname:32} acil {report.detected}/{report.emergencies} "
            f"(recall {report.recall * 100:.1f}%) · "
            f"yanlış-pozitif {report.false_positives}/{report.non_emergencies} "
            f"({report.false_positive_rate * 100:.1f}%)"
        )
        for m in report.missed:
            print(f"     KAÇAN ACİL: {m.text!r}")

    recall = tot_detected / tot_emg if tot_emg else 1.0
    fpr = tot_fp / tot_non if tot_non else 0.0
    print("-" * 70)
    final = "✅ HEDEF KARŞILANDI" if tot_detected == tot_emg else "❌ KAÇAN ACİL VAR"
    print(
        f"TOPLAM: acil {tot_detected}/{tot_emg} · recall {recall * 100:.1f}% · "
        f"kaçan {tot_emg - tot_detected} · yanlış-pozitif {fpr * 100:.1f}%  {final}"
    )


if __name__ == "__main__":
    main()
