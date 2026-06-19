"""Korpus veri modeli, JSONL G/Ç ve doğrulama — İP-1.2.

Her korpus kaydı, anonim bir Türkçe diş şikâyeti metnini ontoloji
(`app.clinical.ontology`) kodlarına bağlı yer-doğruluğu (ground-truth)
etiketleriyle taşır. Etiketler şablon yazarının/küratörün niyetinden gelir;
kural-tabanlı `match_specialty` çıktısından DEĞİL — böylece korpus, mevcut
yönlendiriciyi bağımsız olarak ölçmek için kullanılabilir.

KVKK: Korpus tamamen sentetik/anonimdir. Gerçek hasta verisi içermez.
`scan_pii` her kaydı kişisel-veri sızıntısına karşı denetler.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from app.clinical.ontology import SPECIALTY_BY_CODE, UrgencyLevel

# İzin verilen kanallar (klinik çok-kanallı temas noktaları).
VALID_CHANNELS: frozenset[str] = frozenset({"whatsapp", "phone", "web", "form"})

# İzin verilen kaynak etiketleri.
VALID_SOURCES: frozenset[str] = frozenset({"synthetic_template", "golden_curated"})

# Metin uzunluk sınırları (anlamlı bir şikâyet için).
MIN_TEXT_LEN = 3
MAX_TEXT_LEN = 400


# ─────────────────────────────────────────────────────────────────────────────
# PII tarama — korpusa kişisel veri sızmasını engeller.
# ─────────────────────────────────────────────────────────────────────────────

# 11 haneli TCKN, 13–19 haneli kart, e-posta, 7+ haneli telefon dizisi.
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("tckn", re.compile(r"\b\d{11}\b")),
    ("card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("phone", re.compile(r"\+?\d[\d\s()\-]{6,}\d")),
)


def scan_pii(text: str) -> list[str]:
    """Metinde olası PII desenlerini bulur; eşleşen desen adlarını döndürür.

    Boş liste = temiz. Korpus üretiminde ve testlerde sızıntı kapısı olarak
    kullanılır.
    """
    return [name for name, pattern in _PII_PATTERNS if pattern.search(text)]


# ─────────────────────────────────────────────────────────────────────────────
# Korpus kaydı
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CorpusEntry:
    """Tek bir etiketli şikâyet senaryosu.

    id:             Kararlı kimlik (örn. "dtr-0001").
    text:           Anonim Türkçe şikâyet (orijinal büyük/küçük + aksanlı hâl).
    specialty_code: Yer-doğruluğu branş kodu (ontoloji SPECIALTY_BY_CODE içinde).
    urgency:        Yer-doğruluğu aciliyet ("routine"/"priority"/"emergency").
    channel:        Temas kanalı (whatsapp/phone/web/form).
    source:         "synthetic_template" | "golden_curated".
    lang:           Dil kodu (şimdilik "tr").
    """

    id: str
    text: str
    specialty_code: str
    urgency: str
    channel: str
    source: str
    lang: str = "tr"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, raw: dict) -> "CorpusEntry":
        return cls(
            id=str(raw["id"]),
            text=str(raw["text"]),
            specialty_code=str(raw["specialty_code"]),
            urgency=str(raw["urgency"]),
            channel=str(raw["channel"]),
            source=str(raw["source"]),
            lang=str(raw.get("lang", "tr")),
        )


def validate_entry(entry: CorpusEntry) -> list[str]:
    """Bir kaydı doğrular; insan-okunur hata listesi döndürür (boş = geçerli)."""
    errors: list[str] = []
    if not entry.id:
        errors.append("id boş")
    if entry.specialty_code not in SPECIALTY_BY_CODE:
        errors.append(f"bilinmeyen specialty_code: {entry.specialty_code!r}")
    valid_urgencies = {level.value for level in UrgencyLevel}
    if entry.urgency not in valid_urgencies:
        errors.append(f"bilinmeyen urgency: {entry.urgency!r}")
    if entry.channel not in VALID_CHANNELS:
        errors.append(f"bilinmeyen channel: {entry.channel!r}")
    if entry.source not in VALID_SOURCES:
        errors.append(f"bilinmeyen source: {entry.source!r}")
    text_len = len(entry.text.strip())
    if text_len < MIN_TEXT_LEN:
        errors.append(f"metin çok kısa ({text_len})")
    if text_len > MAX_TEXT_LEN:
        errors.append(f"metin çok uzun ({text_len})")
    pii_hits = scan_pii(entry.text)
    if pii_hits:
        errors.append(f"olası PII: {', '.join(pii_hits)}")
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# JSONL G/Ç
# ─────────────────────────────────────────────────────────────────────────────

def corpus_data_dir() -> Path:
    """Korpus JSONL dosyalarının bulunduğu dizin (`.../corpus/data`)."""
    return Path(__file__).resolve().parent / "data"


def load_corpus(path: Path) -> list[CorpusEntry]:
    """Bir JSONL korpus dosyasını okuyup CorpusEntry listesine çevirir."""
    entries: list[CorpusEntry] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:  # pragma: no cover - bozuk satır
                raise ValueError(f"{path.name}:{line_no} geçersiz JSON: {exc}") from exc
            entries.append(CorpusEntry.from_dict(raw))
    return entries


def save_corpus(entries: Iterable[CorpusEntry], path: Path) -> int:
    """CorpusEntry listesini JSONL olarak yazar; yazılan kayıt sayısını döndürür."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(entry.to_json() + "\n")
            count += 1
    return count
