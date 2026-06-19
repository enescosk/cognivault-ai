"""Deterministic, auditable customer-language understanding for clinic intake.

This layer intentionally sits before the generative model. It handles common
Turkish/English phrasing, spelling variation and multiple intents without
allowing a model to downgrade emergency signals or invent an action.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata


@dataclass(frozen=True)
class IntentEvidence:
    intent: str
    score: float
    confidence: float
    evidence: tuple[str, ...]


_CHAR_MAP = str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"})


def normalize_customer_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "").casefold()
    value = "".join(char for char in value if not unicodedata.combining(char)).translate(_CHAR_MAP)
    value = re.sub(r"(.)\1{2,}", r"\1\1", value)
    value = re.sub(r"[^a-z0-9:+ ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


# Phrases carry more meaning than isolated words. Scores are deliberately
# transparent so a reviewer can reconstruct why an intent won.
_PHRASES: dict[str, tuple[str, ...]] = {
    "medical_emergency": (
        "nefes alamiyorum", "nefes almakta zorlaniyorum", "bilincini kaybetti",
        "bayildi", "durmayan kanama", "kanama durmuyor", "kontrol edilemeyen kanama",
        "cok kan kaybediyorum", "kanamayi durduramiyorum", "yutamiyorum",
        "bogazim kapaniyor", "nefesim daraliyor", "dilim sisti", "yuzum hizla sisiyor",
        "cenem kirildi", "cene kirigi", "ciddi travma",
    ),
    "reschedule_appointment": (
        "randevumu degistir", "randevuyu degistir", "baska saate al", "baska gune al",
        "ileri tarihe al", "geri tarihe al", "randevumu ertele", "randevuyu ertele",
        "randevumu oteki", "randevuyu kaydir", "yetisemeyecegim", "gelemeyecegim ama",
        "saatimi degistir", "gununu degistir", "persembeye al", "haftaya al",
        "ileri tarihe kaydir",
        "change my appointment", "move my appointment", "reschedule",
    ),
    "cancel_appointment": (
        "randevumu iptal", "randevuyu iptal", "gelemeyecegim iptal", "kaydi sil",
        "randevuyu sil", "randevuya gelemiyorum", "cancel my appointment", "cancel appointment",
    ),
    "book_appointment": (
        "randevu almak", "randevu alcam", "randevu istiyorum", "randevu alabilir", "musait misiniz",
        "musaitlik durumu", "appointment pls",
        "boslugunuz var", "bosluk var", "bos yer var", "gelebilir miyim", "muayene olmak",
        "bakabilir mi", "kontrole gelmek", "kayit olustur", "sira almak", "doktorla gorusmek",
        "appointment please", "book appointment", "see a doctor", "available slot",
    ),
    "ask_price": (
        "ne kadar", "kac para", "fiyat bilgisi", "ucreti nedir", "ucret bilgisi", "kaca olur",
        "maliyeti ne", "butcesi nedir", "price", "how much", "cost",
    ),
    "ask_insurance": (
        "sigorta karsilar", "sigortam karsilar", "sgk gecer", "sigortam gecer", "anlasmali misiniz",
        "anlasmaniz var mi", "allianz", "axa", "mapfre", "tamamlayici saglik", "ozel sigorta", "insurance", "coverage",
    ),
    "ask_location": (
        "adres nerede", "adresiniz nerede", "konum at", "konum gonder", "haritadan gonder", "nasil gelirim", "hangi semt",
        "sube nerede", "sube nerde", "yol tarifi", "where are you", "location", "address",
    ),
    "ask_working_hours": (
        "kacta aciliyor", "kacta kapaniyor", "calisma saat", "mesai saat",
        "bugun acik", "hafta sonu acik", "pazar calisiyor", "cumartesi calisiyor", "mesainiz kacta",
        "working hours", "when do you open",
    ),
}

_TERMS: dict[str, tuple[str, ...]] = {
    "reschedule_appointment": ("ertele", "degistir", "kaydir", "oteleme"),
    "cancel_appointment": ("iptal", "vazgectim", "sil", "cancel"),
    "book_appointment": ("randevu", "randvu", "randewu", "musait", "muayene", "kontrol"),
    "ask_price": ("fiyat", "ucret", "tutar", "fiyati"),
    "ask_insurance": ("sgk", "sigorta", "provizyon"),
    "ask_location": ("adres", "konum", "lokasyon"),
    "ask_working_hours": ("saatler", "acik", "kapali", "mesai"),
}

_APPOINTMENT_CONTEXT = {"randevu", "randvu", "randewu", "saat", "saatim", "saatimi", "gun", "gunu", "tarih"}
_MEDICAL_EXACT = {
    "dis", "dolgu", "kanal", "implant", "diseti", "tel", "braket", "cekim",
    "sisme", "sislik", "kanama", "akne", "sivilce", "egzama", "botoks",
    "muayene", "kontrol", "ortodonti", "yirmilik",
}
_MEDICAL_PREFIXES = ("disim", "agri", "zonklu", "implant", "diseti", "sisli", "kani", "sivilce", "egzama")
_NEGATED_INTENTS: dict[str, tuple[str, ...]] = {
    "book_appointment": ("randevu istemiyorum", "randevu almayacagim", "randevu gerek yok"),
    "cancel_appointment": ("iptal etmeyin", "iptal istemiyorum", "iptal degil", "cancel etme"),
    "reschedule_appointment": ("degistirmek istemiyorum", "erteleme istemiyorum", "saatimi degistirmeyin"),
    "ask_price": ("fiyat sormuyorum", "ucret sormuyorum"),
    "ask_insurance": ("sigorta sormuyorum", "sgk sormuyorum"),
}
_NON_MEDICAL_PHRASES = ("kontrol panel", "kontrol sistemi", "kontrol uygulamasi", "hesap kontrol")


def _token_match(token: str, candidate: str) -> bool:
    if token == candidate:
        return True
    if len(token) < 5 or len(candidate) < 5 or abs(len(token) - len(candidate)) > 2:
        return False
    return SequenceMatcher(None, token, candidate).ratio() >= 0.84


def rank_intents(text: str) -> list[IntentEvidence]:
    normalized = normalize_customer_text(text)
    tokens = normalized.split()
    token_set = set(tokens)
    scored: dict[str, tuple[float, list[str]]] = {}

    for intent, phrases in _PHRASES.items():
        for phrase in phrases:
            if phrase in normalized:
                score, evidence = scored.get(intent, (0.0, []))
                scored[intent] = (score + 4.0, [*evidence, phrase])

    for intent, terms in _TERMS.items():
        for term in terms:
            matching = next((token for token in tokens if _token_match(token, term)), None)
            if matching:
                score, evidence = scored.get(intent, (0.0, []))
                scored[intent] = (score + 1.25, [*evidence, matching])

    if any(phrase in normalized for phrase in _NON_MEDICAL_PHRASES):
        scored.pop("book_appointment", None)

    # Reschedule/cancel require appointment context; generic "değiştir" or
    # "vazgeçtim" must not mutate a booking by itself.
    has_appointment_context = (
        bool(token_set & _APPOINTMENT_CONTEXT)
        or "appointment" in token_set
        or any(token.startswith("randevu") for token in tokens)
    )
    for intent in ("reschedule_appointment", "cancel_appointment"):
        if intent in scored and not has_appointment_context and scored[intent][0] < 4:
            scored.pop(intent)

    # A complaint plus a request-like time expression is a booking signal even
    # when the customer never says the formal word "randevu".
    has_medical_context = not any(phrase in normalized for phrase in _NON_MEDICAL_PHRASES) and any(
        token in _MEDICAL_EXACT or any(token.startswith(root) for root in _MEDICAL_PREFIXES)
        for token in tokens
    )
    request_shape = bool(re.search(r"\b(bugun|yarin|hafta|pazartesi|sali|carsamba|persembe|cuma|gelebilir|bakabilir|istiyorum)\b", normalized))
    if has_medical_context:
        score, evidence = scored.get("book_appointment", (0.0, []))
        scored["book_appointment"] = (score + 2.75, [*evidence, "medical_request_context"])
        if request_shape:
            score, evidence = scored["book_appointment"]
            scored["book_appointment"] = (score + 1.5, [*evidence, "request_time_context"])

    for intent, negations in _NEGATED_INTENTS.items():
        if any(phrase in normalized for phrase in negations):
            scored.pop(intent, None)

    if "book_appointment" in scored and scored["book_appointment"][0] <= 1.25 and (
        "cancel_appointment" in scored or "reschedule_appointment" in scored
    ):
        scored.pop("book_appointment")

    # Safety intent always wins, but only high-specificity phrases can create it.
    output: list[IntentEvidence] = []
    for intent, (score, evidence) in scored.items():
        confidence = min(0.99, 0.50 + score * 0.09)
        if intent == "medical_emergency":
            confidence = max(0.97, confidence)
        output.append(IntentEvidence(intent, round(score, 2), round(confidence, 2), tuple(dict.fromkeys(evidence))))

    priority = {"cancel_appointment": 0, "reschedule_appointment": 1}
    return sorted(output, key=lambda item: (0 if item.intent == "medical_emergency" else 1, -item.score, priority.get(item.intent, 10)))


def understand_primary_intent(text: str) -> IntentEvidence:
    ranked = rank_intents(text)
    if ranked:
        emergency = next((item for item in ranked if item.intent == "medical_emergency"), None)
        if emergency:
            return emergency
        return ranked[0]
    word_count = len(normalize_customer_text(text).split())
    if word_count <= 2:
        return IntentEvidence("unknown", 0.0, 0.42, ())
    return IntentEvidence("general_question", 0.0, 0.66, ())


_CONTEXT_CONTINUATIONS = {
    "evet", "hayir", "olur", "uygun", "tamam", "peki", "yarin", "bugun",
    "sabah", "ogle", "aksam", "sonra", "once", "adim", "telefonum",
}


def understand_with_context(text: str, previous_intent: str | None) -> IntentEvidence:
    """Carry an active workflow through short follow-up answers.

    Explicit new evidence always wins; context is used only for otherwise
    unknown/general short replies such as "evet yarın 14 olur".
    """
    current = understand_primary_intent(text)
    if current.intent not in {"unknown", "general_question"} or not previous_intent:
        return current
    if previous_intent not in {
        "book_appointment", "reschedule_appointment", "cancel_appointment",
        "ask_price", "ask_insurance", "ask_location", "ask_working_hours",
    }:
        return current
    normalized = normalize_customer_text(text)
    tokens = set(normalized.split())
    has_time = bool(re.search(r"\b([01]?\d|2[0-3])[:.]?[0-5]?\d\b", normalized))
    if tokens & _CONTEXT_CONTINUATIONS or has_time or len(tokens) <= 3:
        return IntentEvidence(previous_intent, 1.5, 0.78, ("conversation_context",))
    return current


_INSTRUCTION_ATTACK_PATTERNS = (
    r"\b(ignore|disregard|forget) (all |the )?(previous|prior|system) (instructions?|prompt)",
    r"\b(onceki|yukaridaki|sistem) (talimatlari|promptu) (unut|yoksay|yok say|gorme)",
    r"\bsystem prompt", r"\bdeveloper message", r"\bgizli prompt",
    r"\bintent(?:ini)? (medical emergency|book appointment|general question) yap",
    r"\bjson (olarak )?(sunlari|bunu) dondur",
    r"</?patient_message>",
)


def detect_instruction_attack(text: str) -> bool:
    normalized = normalize_customer_text(text)
    return any(re.search(pattern, normalized) for pattern in _INSTRUCTION_ATTACK_PATTERNS)
