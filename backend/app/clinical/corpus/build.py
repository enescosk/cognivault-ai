"""Deterministik korpus üreticisi — İP-1.2.

Şablonları (`templates.py`) sabit tohumlu (seed) bir RNG ile doldurarak
dengeli, tekrarsız ve PII-temiz bir Türkçe diş şikâyeti korpusu üretir ve
`data/dental_tr.jsonl` dosyasına yazar.

Çalıştırma:
    python -m app.clinical.corpus.build          # yaz + istatistik
    python -m app.clinical.corpus.build --check   # yazmadan istatistik

Aynı tohumla yeniden üretim aynı dosyayı verir (sürüm kontrolü için kararlı).
"""

from __future__ import annotations

import argparse
import random
import re
from collections import Counter

from app.clinical.corpus.schema import (
    CorpusEntry,
    corpus_data_dir,
    save_corpus,
    scan_pii,
    validate_entry,
)
from app.clinical.corpus.templates import (
    CHANNELS,
    EMERGENCY_TEMPLATES,
    FILLERS,
    INTENSIFIERS,
    REQUESTS,
    TEETH,
    TEMPLATES,
    TIME_AGO,
)
from app.clinical.ontology import UrgencyLevel, normalize_tr

# Üretim parametreleri.
SEED = 1812  # BiGG 1812 — kararlı tohum.
PER_SPECIALTY_QUOTA = 46
EMERGENCY_QUOTA = 40
ROUTINE_RATIO = 0.6  # Hem routine hem priority şablonu olan branşlarda.
MIN_TOTAL = 500  # İş planı başarı ölçütü: ≥500 anonim senaryo.

_WS = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?])")


def _cleanup(text: str) -> str:
    """Slot doldurma sonrası fazla boşlukları toparlar."""
    text = _WS.sub(" ", text).strip()
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    return text


def _fill(template: str, rng: random.Random) -> str:
    """Şablondaki tüm slotları RNG ile doldurur (kullanılmayan slotlar yok sayılır)."""
    return _cleanup(
        template.format(
            filler=rng.choice(FILLERS),
            intensifier=rng.choice(INTENSIFIERS),
            time=rng.choice(TIME_AGO),
            tooth=rng.choice(TEETH),
            request=rng.choice(REQUESTS),
        )
    )


def _generate_bucket(
    templates: tuple[str, ...],
    quota: int,
    rng: random.Random,
    seen: set[str],
) -> list[str]:
    """Bir şablon kümesinden, küresel `seen` ile tekrarsız, `quota` adet metin üretir."""
    produced: list[str] = []
    attempts = 0
    max_attempts = max(quota * 300, 1000)
    while len(produced) < quota and attempts < max_attempts:
        attempts += 1
        text = _fill(rng.choice(templates), rng)
        norm = normalize_tr(text)
        if norm in seen:
            continue
        if scan_pii(text):  # pragma: no cover - şablonlar PII içermez
            continue
        seen.add(norm)
        produced.append(text)
    return produced


def build_corpus(seed: int = SEED) -> list[CorpusEntry]:
    """Korpusu üretir ve doğrulanmış CorpusEntry listesi döndürür (yazmaz)."""
    rng = random.Random(seed)
    seen: set[str] = set()
    rows: list[tuple[str, str, str]] = []  # (text, specialty_code, urgency)

    for code in sorted(TEMPLATES):
        buckets = TEMPLATES[code]
        routine = buckets.get(UrgencyLevel.ROUTINE, ())
        priority = buckets.get(UrgencyLevel.PRIORITY, ())

        if routine and priority:
            routine_quota = round(PER_SPECIALTY_QUOTA * ROUTINE_RATIO)
            priority_quota = PER_SPECIALTY_QUOTA - routine_quota
        elif routine:
            routine_quota, priority_quota = PER_SPECIALTY_QUOTA, 0
        else:
            routine_quota, priority_quota = 0, PER_SPECIALTY_QUOTA

        for text in _generate_bucket(routine, routine_quota, rng, seen):
            rows.append((text, code, UrgencyLevel.ROUTINE.value))
        for text in _generate_bucket(priority, priority_quota, rng, seen):
            rows.append((text, code, UrgencyLevel.PRIORITY.value))

    # Acil durum kümesi (branştan bağımsız).
    emergency_templates = tuple(t for _, t in EMERGENCY_TEMPLATES)
    code_by_template = {t: c for c, t in EMERGENCY_TEMPLATES}
    emergency_produced = 0
    attempts = 0
    while emergency_produced < EMERGENCY_QUOTA and attempts < EMERGENCY_QUOTA * 300:
        attempts += 1
        template = rng.choice(emergency_templates)
        text = _fill(template, rng)
        norm = normalize_tr(text)
        if norm in seen:
            continue
        if scan_pii(text):  # pragma: no cover
            continue
        seen.add(norm)
        rows.append((text, code_by_template[template], UrgencyLevel.EMERGENCY.value))
        emergency_produced += 1

    # Kararlı sıralama → kararlı id ataması (yeniden üretim aynı dosyayı verir).
    rows.sort(key=lambda r: (r[1], r[2], normalize_tr(r[0])))

    entries: list[CorpusEntry] = []
    for index, (text, code, urgency) in enumerate(rows, start=1):
        entry = CorpusEntry(
            id=f"dtr-{index:04d}",
            text=text,
            specialty_code=code,
            urgency=urgency,
            channel=rng.choice(CHANNELS),
            source="synthetic_template",
            lang="tr",
        )
        errors = validate_entry(entry)
        if errors:  # pragma: no cover - üretim hatası
            raise ValueError(f"{entry.id} doğrulama hatası: {errors}")
        entries.append(entry)

    if len(entries) < MIN_TOTAL:  # pragma: no cover - kota yetersizliği
        raise RuntimeError(
            f"Korpus hedefin altında: {len(entries)} < {MIN_TOTAL}. Kotaları artır."
        )
    return entries


def _print_stats(entries: list[CorpusEntry]) -> None:
    by_specialty = Counter(e.specialty_code for e in entries)
    by_urgency = Counter(e.urgency for e in entries)
    by_channel = Counter(e.channel for e in entries)
    print(f"Toplam senaryo: {len(entries)}")
    print("\nBranşa göre:")
    for code, count in sorted(by_specialty.items()):
        print(f"  {code:<18} {count}")
    print("\nAciliyete göre:")
    for urgency, count in sorted(by_urgency.items()):
        print(f"  {urgency:<12} {count}")
    print("\nKanala göre:")
    for channel, count in sorted(by_channel.items()):
        print(f"  {channel:<10} {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Türkçe diş şikâyeti korpusu üreticisi")
    parser.add_argument("--check", action="store_true", help="Dosyaya yazma, sadece istatistik")
    args = parser.parse_args()

    entries = build_corpus()
    _print_stats(entries)

    if not args.check:
        out_path = corpus_data_dir() / "dental_tr.jsonl"
        count = save_corpus(entries, out_path)
        print(f"\nYazıldı: {count} kayıt → {out_path}")


if __name__ == "__main__":
    main()
