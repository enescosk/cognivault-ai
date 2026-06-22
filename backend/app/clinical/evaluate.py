"""Branş yönlendirme doğruluğu değerlendirme harness'ı — İP-1.4.

Korpusu (sentetik + golden) yükler, her senaryoda `normalizer.triage()`
yönlendiricisini çalıştırır ve branş eşleme doğruluğunu raporlar:
genel doğruluk, branş bazlı doğruluk ve en sık karışma çiftleri.

İş planı başarı ölçütü: branş eşlemede ≥%90 (≥500 senaryoluk sentetik set).
Golden set kasıtlı olarak daha zordur (anahtar-kelimesiz parafraz,
kod-değiştirme); oradaki düşük-güven kaçışları İP-1.6 çekimser tahmin
katmanının (insana yükseltme) hedefidir, kurala zorla uydurulmaz.

Çalıştırma:
    python -m app.clinical.evaluate              # her iki seti raporla
    python -m app.clinical.evaluate --file golden.jsonl
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.clinical.corpus.schema import CorpusEntry, corpus_data_dir, load_corpus
from app.clinical.normalizer import triage


@dataclass(frozen=True)
class SpecialtyScore:
    """Tek branşın doğruluk özeti."""

    code: str
    total: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass(frozen=True)
class EvalReport:
    """Bir korpus dosyasının tam değerlendirme raporu."""

    name: str
    total: int
    correct: int
    per_specialty: dict[str, SpecialtyScore]
    confusion: Counter = field(default_factory=Counter)  # (gerçek, tahmin) -> sayı

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def meets_target(self, target: float = 0.90) -> bool:
        return self.accuracy >= target


def evaluate_entries(entries: list[CorpusEntry], name: str) -> EvalReport:
    """Verilen kayıtlarda yönlendiriciyi koşturup rapor üretir."""
    total = len(entries)
    correct = 0
    per_total: Counter = Counter()
    per_correct: Counter = Counter()
    confusion: Counter = Counter()

    for entry in entries:
        predicted = triage(entry.text).specialty_code
        per_total[entry.specialty_code] += 1
        if predicted == entry.specialty_code:
            correct += 1
            per_correct[entry.specialty_code] += 1
        else:
            confusion[(entry.specialty_code, predicted)] += 1

    per_specialty = {
        code: SpecialtyScore(code=code, total=per_total[code], correct=per_correct[code])
        for code in sorted(per_total)
    }
    return EvalReport(
        name=name,
        total=total,
        correct=correct,
        per_specialty=per_specialty,
        confusion=confusion,
    )


def evaluate_file(path: Path) -> EvalReport:
    """Bir JSONL korpus dosyasını yükleyip değerlendirir."""
    return evaluate_entries(load_corpus(path), path.name)


def format_report(report: EvalReport, target: float = 0.90) -> str:
    """Raporu insan-okunur metne çevirir."""
    lines: list[str] = []
    status = "✅" if report.meets_target(target) else "❌"
    lines.append(
        f"{status} {report.name}: {report.correct}/{report.total} "
        f"= {report.accuracy * 100:.1f}% (hedef ≥{target * 100:.0f}%)"
    )
    lines.append("  Branşa göre:")
    for code, score in report.per_specialty.items():
        lines.append(
            f"    {code:<18} {score.correct}/{score.total} = {score.accuracy * 100:.0f}%"
        )
    if report.confusion:
        lines.append("  En sık karışmalar (gerçek → tahmin):")
        for (gt, pred), count in report.confusion.most_common(8):
            lines.append(f"    {gt} → {pred}: {count}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Branş yönlendirme doğruluğu değerlendirmesi")
    parser.add_argument(
        "--file",
        action="append",
        help="Değerlendirilecek JSONL dosya adı (data/ altında). Varsayılan: her ikisi.",
    )
    parser.add_argument("--target", type=float, default=0.90, help="Doğruluk hedefi (0-1)")
    args = parser.parse_args()

    files = args.file or ["dental_tr.jsonl", "golden.jsonl"]
    for fname in files:
        report = evaluate_file(corpus_data_dir() / fname)
        print(format_report(report, target=args.target))
        print()


if __name__ == "__main__":
    main()
