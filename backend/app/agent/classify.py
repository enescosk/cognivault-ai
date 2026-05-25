"""Hafif/kural-tabanlı sınıflandırma + canned yanıt üretici.

API çağrısı YAPMAZ. Amaç: trivial mesajları (selamlaşma, teşekkür) ücretsiz
yanıtlamak ve sentiment'ı LLM prompt'una geçirilecek şekilde tespit etmek.

Daha karmaşık intent için `services/clinical_ai_service.classify_intent`
veya OpenAI tool-loop'unu kullan. Bu modül agent state'i taşımaz, salt fonksiyon.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# SENTIMENT DETECTION
# Lightweight rule-based — zero API cost. Used to adjust fallback tone.
# ─────────────────────────────────────────────────────────────────────────────

_SENTIMENT_RULES: list[tuple[str, list[str]]] = [
    ("frustrated", ["saçmalık", "hâlâ", "hala", "olmadı", "olmadi", "bir türlü", "bir turlu",
                    "yine aynı", "yine ayni", "çözülmedi", "cozulmedi", "rezalet",
                    "I'm frustrated", "still not", "ridiculous", "unacceptable", "terrible"]),
    ("urgent",     ["acil", "urgent", "asap", "şu an", "su an", "hemen", "right now",
                    "immediately", "as soon as possible"]),
    ("confused",   ["anlamadım", "anlamadim", "nasıl", "nasil", "ne demek", "I don't understand",
                    "confused", "what does", "how do i", "how to"]),
    ("happy",      ["teşekkürler", "tesekkurler", "mükemmel", "mukkemmel", "harika", "süper",
                    "thank you", "thanks", "great", "perfect", "excellent", "awesome"]),
]


def detect_sentiment(text: str) -> str:
    """Returns one of: frustrated | urgent | confused | happy | neutral"""
    lower = text.lower()
    for sentiment, keywords in _SENTIMENT_RULES:
        if any(kw in lower for kw in keywords):
            return sentiment
    return "neutral"


# ─────────────────────────────────────────────────────────────────────────────
# COST-AWARE INTENT CLASSIFIER
# Decides whether to route to AI API or handle locally.
# ─────────────────────────────────────────────────────────────────────────────

_SIMPLE_INTENTS: dict[str, list[str]] = {
    "greeting":    ["merhaba", "alo", "selam", "hi ", "hello", "hey ", "good morning", "iyi günler"],
    "smalltalk":   ["nasılsın", "nasilsin", "naber", "ne var ne yok", "how are you", "how's it going"],
    "thanks":      ["teşekkür", "tesekkur", "sağ ol", "sag ol", "thank you", "thanks", "cheers"],
    "farewell":    ["görüşürüz", "gorusuruz", "iyi günler", "bye", "goodbye", "see you", "hoşça kal"],
    "affirmative": ["evet", "tamam", "olur", "tabii", "yes", "sure", "ok", "okay", "yep"],
}

_SIMPLE_RESPONSES: dict[str, dict[str, str]] = {
    "greeting": {
        "tr": "Merhaba! 👋 Size nasıl yardımcı olabilirim?",
        "en": "Hello! 👋 How can I help you today?",
    },
    "smalltalk": {
        "tr": "İyiyim, teşekkürler! Sen nasılsın? Bugün sana nasıl yardımcı olabilirim?",
        "en": "I'm doing well, thanks! How are you? What can I help you with today?",
    },
    "thanks": {
        "tr": "Rica ederim! 😊 Başka yardımcı olabileceğim bir şey var mı?",
        "en": "You're welcome! 😊 Is there anything else I can help you with?",
    },
    "farewell": {
        "tr": "İyi günler! Tekrar görüşmek üzere. 👋",
        "en": "Take care! Talk to you soon. 👋",
    },
}


def classify_simple_intent(text: str) -> str | None:
    """Returns intent name if message is trivially simple, else None."""
    lower = text.lower().strip()
    if len(lower) > 120:
        return None
    for intent, keywords in _SIMPLE_INTENTS.items():
        if any(lower.startswith(kw) or f" {kw}" in lower for kw in keywords):
            return intent
    return None


def make_simple_reply(intent: str, language: str, sentiment: str, user_name: str | None) -> str | None:
    """Returns a canned reply for trivial intents — no API call needed."""
    template = _SIMPLE_RESPONSES.get(intent, {}).get(language)
    if not template:
        return None
    if user_name and intent == "greeting":
        first = user_name.split()[0]
        template = template.replace("Merhaba!", f"Merhaba, {first}!").replace("Hello!", f"Hello, {first}!")
    if sentiment == "frustrated" and intent not in ("thanks", "farewell"):
        prefix = "Üzgünüm duyduğuma. " if language == "tr" else "I'm sorry to hear that. "
        template = prefix + template
    return template


# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN BOUNDARY TERM SETS — policy modülü tarafından kullanılır
# ─────────────────────────────────────────────────────────────────────────────

CUSTOMER_MEDICAL_TERMS = [
    "diş", "dis", "doktor", "hekim", "muayene", "hastane", "klinik",
    "ağrı", "agri", "ağrısı", "agrisi", "hasta", "tedavi", "reçete", "recete",
]

ENTERPRISE_APPOINTMENT_TERMS = [
    "onboarding", "kurulum", "başlangıç", "baslangic", "devreye alma",
    "technical", "teknik", "support", "destek", "sap", "vpn",
    "fatura", "billing", "ödeme", "odeme",
    "uyum", "compliance", "gdpr", "kvk",
]
