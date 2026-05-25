"""Saf parsing yardımcıları — herhangi bir agent state'i taşımaz.

Bir string + bazı parametre → string/dict/None. AgentContext, DB veya HTTP'ye
bağımlılık yok. Unit test'leri trivial.

Aynı parser'ı tekrar yazmak yerine bu modülü import et — kural-tabanlı
fallback agent, orchestrator ve outreach pipeline aynı parser'ları kullanır.
"""

from __future__ import annotations

import re
from datetime import date, timedelta


def detect_language(text: str, fallback: str = "en") -> str:
    """Türkçe karakter veya kelime varsa 'tr', fallback'e göre default."""
    turkish_markers = ["ş", "ğ", "ı", "ç", "ö", "ü", "randevu", "merhaba", "yardım", "bugün", "yarın"]
    return "tr" if any(marker in text.lower() for marker in turkish_markers) or fallback == "tr" else "en"


def parse_preferred_date(text: str) -> str | None:
    """Türkçe/kısa tarih ifadelerini YYYY-MM-DD'ye çevirir."""
    today = date.today()
    lower = text.lower()

    if "bugün" in lower or "today" in lower:
        return today.isoformat()
    if "yarın" in lower or "tomorrow" in lower:
        return (today + timedelta(days=1)).isoformat()

    # "Gün.Ay" veya "Gün/Ay" formatları → bu yıl
    match = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", text)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass

    # Gün adları
    days_tr = {"pazartesi": 0, "salı": 1, "çarşamba": 2, "perşembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6}
    for name, weekday in days_tr.items():
        if name in lower:
            delta = (weekday - today.weekday()) % 7 or 7
            return (today + timedelta(days=delta)).isoformat()
    return None


def parse_phone(text: str) -> str | None:
    match = re.search(r"(\+?\d[\d\s()-]{8,}\d)", text)
    return match.group(1).strip() if match else None


def parse_department(text: str) -> str | None:
    normalized = text.lower()
    candidates = {
        "onboarding desk": ["onboarding", "kurulum", "başlangıç", "devreye alma"],
        "technical support": ["technical", "support", "teknik", "destek", "issue", "arıza"],
        "billing operations": ["billing", "invoice", "payment", "fatura", "ödeme"],
        "compliance advisory": ["compliance", "legal", "uyum", "denetim", "policy"],
    }
    for department, keywords in candidates.items():
        if any(keyword in normalized for keyword in keywords):
            return department.title()
    return None


def parse_slot_selection(text: str, suggested_slots: list[dict]) -> dict | None:
    """`1`/`2`/`3` seçimi veya slot ID/timestamp eşleşmesi."""
    choice = re.search(r"\b([1-3])\b", text)
    if choice:
        index = int(choice.group(1)) - 1
        if 0 <= index < len(suggested_slots):
            return suggested_slots[index]
    for slot in suggested_slots:
        if str(slot["id"]) in text:
            return slot
        stamp = slot["start_time"][:16].replace("T", " ")
        if stamp in text:
            return slot
    return None


_PLACE_CATEGORIES: list[tuple[list[str], str]] = [
    (["diş", "dis", "dentist", "ortodonti"], "diş doktoru"),
    (["göz", "goz", "oftalmoloji"], "göz doktoru"),
    (["fizik tedavi", "fizyoterapi"], "fizik tedavi merkezi"),
    (["psikolog", "psikiyatri", "terapi"], "psikolog"),
    (["sağlık", "saglik", "hastane", "klinik", "doktor", "hekim", "muayene"], "sağlık merkezi"),
    (["veteriner"], "veteriner kliniği"),
    (["spor salonu", "fitness", "gym", "macfit"], "spor salonu"),
    (["banka", "kredi", "akbank"], "banka"),
    (["ihracat", "danışmanlık", "danismanlik"], "ihracat danışmanlığı"),
]


def _normalize_tr(value: str) -> str:
    return (
        value.lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def infer_place_category(text: str) -> str | None:
    normalized = _normalize_tr(text)
    for keywords, category in _PLACE_CATEGORIES:
        if any(_normalize_tr(keyword) in normalized for keyword in keywords):
            return category
    return None


def _clean_term(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip(" .,!?:;"))
    cleaned = re.sub(r"^(ben|biz|şimdi|simdi|bir|bu)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def default_reply(language: str, message_tr: str, message_en: str) -> str:
    """Tek satırlık language switch."""
    return message_tr if language == "tr" else message_en
