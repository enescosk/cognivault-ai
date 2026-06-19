"""Türkçe diş şikâyeti korpusu — İP-1.2 (veri hendeği başlangıcı).

Alt modüller:
    schema    — CorpusEntry veri modeli + JSONL yükle/kaydet + doğrulama.
    templates — branş bazlı argo şikâyet şablonları ve slot doldurucuları.
    build     — deterministik üretici (dental_tr.jsonl üretir).

Korpus dosyaları (`data/`):
    dental_tr.jsonl — sentetik, şablondan üretilmiş, dengeli (≥500 senaryo).
    golden.jsonl    — elle küratörlü zor vakalar (değerlendirme seti).
"""

from app.clinical.corpus.schema import (
    CorpusEntry,
    corpus_data_dir,
    load_corpus,
    save_corpus,
    scan_pii,
    validate_entry,
)

__all__ = [
    "CorpusEntry",
    "corpus_data_dir",
    "load_corpus",
    "save_corpus",
    "scan_pii",
    "validate_entry",
]
