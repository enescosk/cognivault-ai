"""İP-R1 — API öncesi karşılama (reception) motoru. (v2 — çeşitlilik + insancıllık)

Hasta klinikle ilk temas kurduğunda, daha *yapısal API / klinik triyaj katmanına
inmeden* devreye giren karşılama katmanıdır. Görevi: HER karşılama biçimini
(resmî, samimi, argo, dinî, zaman-temelli, İngilizce, karışık, isimle, soru ekli,
emoji'li, yazım-sapmalı) sadık biçimde tanımak, üsluba/dile/resmiyete AYNALANAN
**çeşitli ve doğal** bir karşılık üretmek, **insancıl bir yanıt gecikmesi**
önermek ve gerçek bir talep varsa onu yutmadan aşağı katmana DEVRETMEK.

Tasarım ilkeleri:
- **Saf Python**, **deterministik** (varyant seçimi girdinin kararlı hash'iyle →
  farklı hastalara farklı doğal cümleler, aynı girdiye hep aynı cümle; artefakt
  diff'lenebilir kalır).
- **Yutmama kuralı:** karşılama + gerçek talep ASLA selamla geçiştirilmez.
- **Güvenlik kuralı:** selamla gelen acil sinyali asla sıradan karşılamaya düşmez.
- **KVKK:** karşılıkta ham kimlik (telefon/TC/e-posta) asla yankılanmaz.
- **İnsancıllık:** `response_delay_ms` — okuma + düşünme + "yazma" süresini modelleyen,
  cevap uzunluğuna duyarlı, jitter'lı ama deterministik bekleme önerisi (robot gibi
  ışık hızında değil; gerçek bir resepsiyonist gibi).

CLI: python -m app.reception.greeting          (kanıt panosu)
     python -m app.reception.greeting --demo   (örnek karşılamalar)
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Sequence

from app.services.customer_understanding import (
    detect_instruction_attack,
    understand_primary_intent,
)

ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "greeting.json"
DEFAULT_ASSISTANT = "Selin"
DEFAULT_CLINIC = "kliniğimiz"

# İnsancıl gecikme modeli (ms). Robotik anındalık yerine gerçek bir resepsiyonist
# temposu: küçük bir düşünme tabanı + cevap uzunluğuna oranlı "yazma" süresi.
DELAY_MIN_MS = 450
DELAY_MAX_MS = 2600
DELAY_BASE_MS = 350
READ_CPS = 30.0          # gelen mesajı "okuma" hızı (karakter/sn)
TYPE_CPS = 45.0          # cevabı "yazma" hızı (karakter/sn)

# Aşağı katmana devri zorunlu kılan (gerçek talep) niyetler — ASLA yutulmaz.
ACTIONABLE_INTENTS = frozenset(
    {
        "book_appointment", "reschedule_appointment", "cancel_appointment",
        "ask_price", "ask_insurance", "ask_location", "ask_working_hours",
        "symptom_triage", "medical_emergency",
    }
)

# Karşılama sinyali taşıyan emoji'ler (normalize bunları atmadan önce taranır).
_GREETING_EMOJI = ("👋", "🙋", "🙂", "😊", "🤝", "🙏", "😀", "😃", "✋")

# Saldırgan/küfürlü içerik sinyalleri. Bu sinyaller geldiğinde motor sıcak bir
# karşılamayla ASLA "ödüllendirmez"; gerçek bir tıbbi/idari talep yoksa sakin,
# sınır koyan bir devre döner. KVKK-sınıfı tutuculuk: yanlış-pozitifi en aza
# indirmek için yalnızca BÜTÜN-JETON, kesin hakaret kökleri kullanılır (klinik
# bağlamında çift anlamlı "mal/got/sik" gibi kelimeler bilerek DIŞARIDA bırakıldı).
_ABUSE_EMOJI = ("🤬", "🖕", "💢")
_PROFANITY = frozenset(
    {
        # Türkçe (normalize edilmiş bütün-jeton kökler)
        "salak", "aptal", "gerizekali", "ahmak", "embesil", "denyo", "dangalak",
        "yavsak", "orospu", "serefsiz", "pust", "kahpe", "pezevenk", "siktir",
        "amk", "amina",
        # İngilizce
        "idiot", "moron", "stupid", "dumb", "fuck", "shit", "asshole", "bitch",
        "bastard", "jerk",
    }
)
_VOWELS = frozenset("aeiou")

# ── Normalizasyon (customer_understanding ile birebir aynı kurallar) ─────────
_CHAR_MAP = str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"})


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "").casefold()
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).translate(_CHAR_MAP)
    value = re.sub(r"(.)\1{2,}", r"\1\1", value)          # "selaaaam" → "selaam"
    value = re.sub(r"[^a-z0-9:+ ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


# ── Karşılama biçim sözlüğü (genişletilmiş) ──────────────────────────────────
GreetingPhrases = tuple[str, ...]

_RELIGIOUS: GreetingPhrases = (
    "selamun aleykum", "selamunaleykum", "selamun aleyqum", "esselamu aleykum",
    "aleykum selam", "aleykumselam", "aleykum esselam", "s a", "selamun",
)
_WELLWISH: GreetingPhrases = (
    "kolay gelsin", "kolaygelsin", "hayirli isler", "hayirli olsun",
    "bereketli olsun", "allaha emanet", "allah razi olsun", "allah kolaylik versin",
    "selametle", "eyvallah",
)
_TIME_OF_DAY: GreetingPhrases = (
    "gunaydin", "gunaydinlar", "tunaydin", "iyi sabahlar", "iyi sabah",
    "hayirli sabahlar", "iyi gunler", "iyi gunlar", "iyi oglenler", "iyi oglen",
    "iyi aksamlar", "hayirli aksamlar", "iyi geceler", "hayirli geceler",
)
_STANDARD: GreetingPhrases = (
    "merhaba", "merhabalar", "merhabe", "meraba", "mrhaba", "merabalar",
    "selam", "selamlar", "selamcim", "selammlar", "selamlarrr",
)
_INFORMAL: GreetingPhrases = (
    "naber", "n aber", "nbr", "nbrr", "napiyorsun", "napiyon", "naptin",
    "ne yapiyorsun", "ne yapiyosun", "slm", "slmm", "mrb", "mrhb", "mrbb",
    "heyy", "hey", "heyo", "selocan", "kanka", "moruk", "hocam selam",
)
_POLITE_INQUIRY: GreetingPhrases = (
    "nasilsiniz", "nasilsin", "iyi misiniz", "iyi misin", "ne haber",
    "ne var ne yok", "nasil gidiyor", "naparsiniz", "keyifler nasil",
    "iyilik saglik", "nasilsinizdir",
)
_ENGLISH: GreetingPhrases = (
    "hello", "helo", "hi", "hiya", "hey", "heya", "hey there", "howdy",
    "good morning", "good afternoon", "good evening", "good night", "good day",
    "greetings", "whats up", "sup", "how are you", "hows it going", "how do you do",
)
_FAREWELL: GreetingPhrases = (
    "gorusuruz", "gorusmek uzere", "hoscakalin", "hosca kalin", "hosca kal",
    "kendine iyi bak", "kendinize iyi bakin", "allaha ismarladik",
    "iyi gunler dilerim", "bye", "goodbye", "see you", "see ya", "take care",
    "have a good day", "catch you later",
)

# (stil etiketi, ifadeler, resmiyet ipucu) — öncelik sırasıyla (özelden genele).
_STYLE_TABLE: tuple[tuple[str, GreetingPhrases, str], ...] = (
    ("farewell", _FAREWELL, "neutral"),
    ("religious", _RELIGIOUS, "formal"),
    ("wellwish", _WELLWISH, "formal"),
    ("time_of_day", _TIME_OF_DAY, "formal"),
    ("polite_inquiry", _POLITE_INQUIRY, "formal"),
    ("english", _ENGLISH, "neutral"),
    ("informal", _INFORMAL, "informal"),
    ("standard", _STANDARD, "neutral"),
)

# Dil tespiti eşleşen ifadenin diline göre yapılır (satır ipucu değil).
_ENGLISH_PHRASES = frozenset(_ENGLISH) | {
    "bye", "goodbye", "see you", "see ya", "take care", "have a good day", "catch you later",
}

# Tek-kelime kısaltma/argolar için fuzzy eşleşme adayları.
_FUZZY_TOKENS: dict[str, str] = {
    "slm": "informal", "mrb": "informal", "mrhb": "informal", "nbr": "informal",
    "merhaba": "standard", "selam": "standard", "gunaydin": "time_of_day",
    "meraba": "standard", "mrhaba": "standard",
}

# Zaman-temelli selamın kanonik (aynalanan) Türkçe karşılığı.
_TIME_CANON_TR = {
    "gunaydin": "Günaydın", "gunaydinlar": "Günaydın", "iyi sabahlar": "Günaydın",
    "iyi sabah": "Günaydın", "hayirli sabahlar": "Günaydın", "tunaydin": "Tünaydın",
    "iyi gunler": "İyi günler", "iyi gunlar": "İyi günler", "iyi oglenler": "İyi günler",
    "iyi oglen": "İyi günler", "iyi aksamlar": "İyi akşamlar", "hayirli aksamlar": "İyi akşamlar",
    "iyi geceler": "İyi geceler", "hayirli geceler": "İyi geceler",
}
_TIME_CANON_EN = {
    "good morning": "Good morning", "good afternoon": "Good afternoon",
    "good evening": "Good evening", "good night": "Good night", "good day": "Good day",
}

# Resmiyeti yukarı/aşağı çeken ek sinyaller.
_FORMAL_MARKERS = frozenset({"hanim", "bey", "efendim", "merhabalar", "selamlar", "rica", "ederim", "lutfen"})
_INFORMAL_MARKERS = frozenset({"kanka", "dostum", "abi", "abla", "kardes", "moruk", "lan", "ya", "knk"})

# Karşılığa katkı saymayan, "artık içerik" sayılmaması gereken jetonlar.
_GREETING_FILLER = frozenset(
    {
        "ben", "bir", "acaba", "ya", "da", "de", "ki", "efendim", "rica", "ederim",
        "ederiz", "lutfen", "size", "sizi", "ile", "su", "the", "a", "an", "please",
        "hanim", "bey", "canim", "dostum", "abi", "abla", "selin", "arzu", "can",
        "asistan", "asistani", "hocam", "merhaba", "selam", "iyi", "gunler",
    }
)

_DIGIT_RE = re.compile(r"\d")


# ── Çeşitlilik & insancıllık yardımcıları ────────────────────────────────────
def _stable_unit(seed: str) -> float:
    """Tohumdan [0,1) aralığında kararlı (deterministik) bir değer üretir."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _pick(pool: Sequence[str], *, seed: str) -> str:
    """Havuzdan girdiye göre deterministik ama çeşitlenen bir seçim yapar."""
    if len(pool) == 1:
        return pool[0]
    idx = int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:4], "big") % len(pool)
    return pool[idx]


def _is_gibberish(token: str) -> bool:
    """Klavye-ezmesi / anlamsız bir jeton mu? (Sözlük yok; tutucu fonotaktik sezgi.)

    Yanlış-pozitif riski bilerek düşük tutulur: gerçek bir hasta talebini
    reddetmektense nadiren tuhaf bir jetonu geçirmek yeğdir. Yalnızca açık
    klavye-ezmesi yakalanır: 4+ harf hiç sesli içermiyorsa ya da 4+ ardışık
    sessiz harf varsa. (Gerçek TR/EN kelimeler ve isimler bu eşikleri geçmez.)
    """
    if len(token) < 4 or any(ch.isdigit() for ch in token):
        return False
    if not any(ch in _VOWELS for ch in token):
        return True
    run = 0
    for ch in token:
        if ch in _VOWELS:
            run = 0
        else:
            run += 1
            if run >= 4:
                return True
    return False


def _abuse_signal(raw: str, tokens: Sequence[str]) -> bool:
    """Saldırgan/küfürlü içerik sinyali (emoji veya bütün-jeton hakaret)."""
    if any(sym in raw for sym in _ABUSE_EMOJI):
        return True
    return any(tok in _PROFANITY for tok in tokens)


def human_delay_ms(patient_text: str, reply: str, *, seed: str = "") -> int:
    """İnsancıl yanıt gecikmesi (ms): okuma + düşünme + yazma + hafif jitter.

    Robotik anındalık yerine gerçek bir resepsiyonist temposu modellenir; süre
    cevap uzunluğuyla büyür, [DELAY_MIN_MS, DELAY_MAX_MS] aralığına kelepçelenir.
    Deterministiktir (aynı girdi → aynı süre).
    """
    read_ms = (len(patient_text or "") / READ_CPS) * 1000 * 0.5
    type_ms = (len(reply or "") / TYPE_CPS) * 1000
    raw = DELAY_BASE_MS + read_ms + type_ms
    jitter = 0.85 + 0.30 * _stable_unit(seed or f"{patient_text}|{reply}")
    raw *= jitter
    return int(max(DELAY_MIN_MS, min(DELAY_MAX_MS, round(raw))))


# ── Doğal yanıt havuzları (deterministik seçim) ──────────────────────────────
# Doğal, düz (devrik olmayan) Türkçe tanıtımlar. Klinik adına ek getirmeyiz
# (özel ada uygun ek/kesme işareti adın sonuna göre değişir → "Demo'ten" gibi
# hataları önlemek için ad çıplak niteleyici olarak bırakılır).
_INTRO_TR_FORMAL = (
    "Ben {a}, {c} dijital asistanıyım.",
    "Adım {a}, {c} dijital asistanıyım.",
    "Ben {a}, {c} dijital asistanı olarak buradayım.",
)
_INTRO_TR_INFORMAL = (
    "Ben {a}, {c} asistanıyım.",
    "Adım {a}, {c} asistanıyım.",
    "Ben {a}, {c} asistanı olarak buradayım.",
)
_INTRO_EN = (
    "I'm {a}, the digital assistant at {c}.",
    "{a} here, {c}'s digital assistant.",
    "I'm {a} from {c}, your digital assistant.",
)
_OFFER_TR_FORMAL = (
    "Size nasıl yardımcı olabilirim?",
    "Bugün size nasıl yardımcı olabilirim?",
    "Sizin için ne yapabilirim?",
    "Nasıl yardımcı olmamı istersiniz?",
)
_OFFER_TR_INFORMAL = (
    "Nasıl yardımcı olabilirim?",
    "Nasıl yardımcı olayım?",
    "Senin için ne yapabilirim?",
)
_OFFER_EN = (
    "How may I help you today?",
    "How can I help you?",
    "What can I do for you today?",
)
_ACK_TR = (
    "Çok iyiyim, teşekkür ederim. ",
    "Teşekkür ederim, gayet iyiyim. ",
    "İyiyim, sorduğunuz için teşekkürler. ",
)
_ACK_EN = (
    "I'm doing well, thank you. ",
    "I'm great, thanks for asking. ",
)
_LIGHT_TR = (
    "Buradayım, nasıl yardımcı olabilirim?",
    "Sizi dinliyorum, nasıl yardımcı olabilirim?",
    "Buyurun, nasıl yardımcı olabilirim?",
    "Dinliyorum, sizin için ne yapabilirim?",
)
_LIGHT_EN = (
    "I'm right here — how can I help?",
    "I'm listening, how can I help?",
)
_FAREWELL_TR_FORMAL = (
    "Bizi tercih ettiğiniz için teşekkürler. Sağlıklı günler dilerim!",
    "Görüştüğümüze sevindim, sağlıklı günler dilerim!",
    "Teşekkür ederiz, kendinize iyi bakın!",
)
_FAREWELL_TR_INFORMAL = (
    "Görüşürüz, kendine iyi bak!",
    "Hoşça kal, sağlıklı günler!",
)
_FAREWELL_EN = (
    "Thank you for reaching out. Take care and stay healthy!",
    "Glad to help — take care!",
)
_PREFIX_TR = ("{o}, hoş geldiniz", "{o}", "{o}, buyurun")
_PREFIX_EN = ("{o}, welcome", "{o}")
_PREFIX_EMERGENCY_TR = (
    "{o}. Sizi hemen yetkili ekibe aktarıyorum",
    "{o}. Hemen ekibimize bağlıyorum sizi",
)
_PREFIX_EMERGENCY_EN = ("{o}. I'm connecting you to our team right away",)
_WELLWISH_OPENER = ("Teşekkür ederim", "Sağ olun", "Çok teşekkürler")
# Saldırgan içeriğe sakin, profesyonel, sınır koyan karşılık (selam aynalanmaz).
_DEESCALATE_TR = (
    "Size yardımcı olmak isterim, talebinizi paylaşır mısınız",
    "Yardımcı olmak için buradayım, lütfen ne istediğinizi yazabilir misiniz",
)
_DEESCALATE_EN = (
    "I'm here to help, please share your request",
    "I'd like to help, could you tell me what you need",
)


@dataclass(frozen=True)
class GreetingAnalysis:
    matched_greeting: bool
    primary_style: str
    styles: tuple[str, ...]
    formality: str                # formal|informal|neutral
    language: str                 # tr|en
    polite_inquiry: bool
    has_followup_intent: bool
    followup_intent: str | None
    requires_human_review: bool
    instruction_attack: bool
    abusive: bool
    confidence: float
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "matched_greeting": self.matched_greeting,
            "primary_style": self.primary_style,
            "styles": list(self.styles),
            "formality": self.formality,
            "language": self.language,
            "polite_inquiry": self.polite_inquiry,
            "has_followup_intent": self.has_followup_intent,
            "followup_intent": self.followup_intent,
            "requires_human_review": self.requires_human_review,
            "instruction_attack": self.instruction_attack,
            "abusive": self.abusive,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ReceptionTurn:
    reply: str
    prefix: str
    handled: bool
    should_handoff: bool
    handoff_reason: str | None
    requires_human_review: bool
    response_delay_ms: int
    analysis: GreetingAnalysis

    def as_dict(self) -> dict:
        return {
            "reply": self.reply,
            "prefix": self.prefix,
            "handled": self.handled,
            "should_handoff": self.should_handoff,
            "handoff_reason": self.handoff_reason,
            "requires_human_review": self.requires_human_review,
            "response_delay_ms": self.response_delay_ms,
            "analysis": self.analysis.as_dict(),
        }


def _fuzzy_token_style(token: str) -> str | None:
    for cand, style in _FUZZY_TOKENS.items():
        if token == cand:
            return style
        if len(token) >= 4 and len(cand) >= 4 and SequenceMatcher(None, token, cand).ratio() >= 0.86:
            return style
    return None


def _is_greeting_token(token: str) -> bool:
    for _style, phrases, _f in _STYLE_TABLE:
        for phrase in phrases:
            if " " not in phrase and token == phrase:
                return True
    return _fuzzy_token_style(token) is not None


def analyze_greeting(text: str) -> GreetingAnalysis:
    """Karşılama biçimini, dilini, resmiyetini ve devir gereksinimini çözümler."""
    raw = text or ""
    emoji_greeting = any(sym in raw for sym in _GREETING_EMOJI)
    normalized = normalize(raw)
    tokens = normalized.split()
    token_set = set(tokens)

    styles: list[str] = []
    evidence: list[str] = []
    formality_votes: list[str] = []
    language_votes: list[str] = []

    for style, phrases, formality_hint in _STYLE_TABLE:
        for phrase in phrases:
            if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", normalized):
                if style not in styles:
                    styles.append(style)
                evidence.append(phrase)
                formality_votes.append(formality_hint)
                language_votes.append("en" if phrase in _ENGLISH_PHRASES else "tr")
                break

    # Tek-kelime kısaltma/argo (yazım sapmalı) — fuzzy.
    if not styles:
        for tok in tokens:
            fs = _fuzzy_token_style(tok)
            if fs:
                styles.append(fs)
                evidence.append(tok)
                language_votes.append("tr")
                break

    # Yalnız emoji ile gelen "👋" gibi mesajlar da yumuşak bir selam sayılır.
    if not styles and emoji_greeting:
        styles.append("standard")
        evidence.append("emoji")
        language_votes.append("tr")

    polite_inquiry = "polite_inquiry" in styles
    matched_greeting = bool(styles)

    if token_set & _INFORMAL_MARKERS or "informal" in styles:
        formality = "informal"
    elif token_set & _FORMAL_MARKERS or any(v == "formal" for v in formality_votes):
        formality = "formal"
    else:
        formality = "neutral"

    tr_signal = any(v == "tr" for v in language_votes) or bool(token_set & {"merhaba", "selam"})
    en_signal = any(v == "en" for v in language_votes)
    language = "en" if (en_signal and not tr_signal) else "tr"

    # Niyet tespitini tek kaynağa devret.
    intent = understand_primary_intent(raw).intent
    actionable = intent in ACTIONABLE_INTENTS

    # Eşleşen (çok-kelimeli dahil) karşılama ifadelerinin jetonları tüketilmiş sayılır.
    consumed = {tok for phrase in evidence for tok in phrase.split()}
    content_tokens = [
        t
        for t in tokens
        if t not in _GREETING_FILLER
        and t not in consumed
        and not _is_greeting_token(t)
        and not _DIGIT_RE.search(t)
    ]
    # Saçma/anlamsız ek içerik (klavye-ezmesi) varsa, talep tek jeton olsa bile
    # selamla YUTULMAZ — açıklığa kavuşturmak için aşağı devredilir.
    has_gibberish_residual = any(_is_gibberish(t) for t in content_tokens)
    residual_general = (not actionable) and (len(content_tokens) >= 2 or has_gibberish_residual)

    has_followup_intent = actionable or residual_general
    followup_intent = intent if actionable else ("general_question" if residual_general else None)
    requires_human_review = intent in {"medical_emergency", "ask_insurance"}
    abusive = _abuse_signal(raw, tokens)

    base_conf = 0.9 if matched_greeting else 0.3
    if polite_inquiry:
        base_conf = min(0.95, base_conf + 0.03)

    return GreetingAnalysis(
        matched_greeting=matched_greeting,
        primary_style=styles[0] if styles else "none",
        styles=tuple(styles),
        formality=formality,
        language=language,
        polite_inquiry=polite_inquiry,
        has_followup_intent=has_followup_intent,
        followup_intent=followup_intent,
        requires_human_review=requires_human_review,
        instruction_attack=detect_instruction_attack(raw),
        abusive=abusive,
        confidence=round(base_conf, 2),
        evidence=tuple(dict.fromkeys(evidence)),
    )


# ── Zaman-temelli karşılama (deterministik; saat enjekte edilir) ─────────────
def time_greeting(hour: int | None, language: str) -> str:
    if hour is None:
        return "Merhaba" if language == "tr" else "Hello"
    hour %= 24
    if language == "en":
        if 5 <= hour < 12:
            return "Good morning"
        if 12 <= hour < 18:
            return "Good afternoon"
        if 18 <= hour < 22:
            return "Good evening"
        return "Hello"
    if 5 <= hour < 11:
        return "Günaydın"
    if 11 <= hour < 18:
        return "İyi günler"
    if 18 <= hour < 22:
        return "İyi akşamlar"
    return "İyi geceler"


def _mirror_opener(analysis: GreetingAnalysis, hour: int | None) -> str:
    """Girdinin biçimini aynalayan açılış selamı (kullanıcının dediğini yankılar)."""
    style, lang = analysis.primary_style, analysis.language
    if style == "religious":
        return "Aleykümselam"
    if style == "wellwish":
        return _pick(_WELLWISH_OPENER, seed="wellwish:" + "".join(analysis.evidence))
    if style == "time_of_day":
        for ev in analysis.evidence:
            if ev in _TIME_CANON_TR:
                return _TIME_CANON_TR[ev]
        return time_greeting(hour, "tr")
    if style == "english":
        for ev in analysis.evidence:
            if ev in _TIME_CANON_EN:
                return _TIME_CANON_EN[ev]
        return time_greeting(hour, "en")
    if style == "informal":
        return "Selam"
    # standard / polite_inquiry → zaman duyarlı sıcak açılış.
    return time_greeting(hour, "en" if lang == "en" else "tr")


def compose_reception(
    text: str,
    *,
    clinic_name: str = DEFAULT_CLINIC,
    assistant_name: str = DEFAULT_ASSISTANT,
    hour: int | None = None,
    already_greeted: bool = False,
    analysis: GreetingAnalysis | None = None,
) -> ReceptionTurn:
    """Karşılama biçimini aynalayan, çeşitlenen, doğal bir yanıt üretir."""
    analysis = analysis or analyze_greeting(text)
    seed = normalize(text)
    lang = analysis.language
    is_en = lang == "en"

    def finish(reply: str, prefix: str, handled: bool, handoff: bool, reason: str | None) -> ReceptionTurn:
        emitted = reply or prefix
        delay = human_delay_ms(text, emitted, seed=seed) if emitted else DELAY_MIN_MS
        return ReceptionTurn(
            reply=reply,
            prefix=prefix,
            handled=handled,
            should_handoff=handoff,
            handoff_reason=reason,
            requires_human_review=analysis.requires_human_review,
            response_delay_ms=delay,
            analysis=analysis,
        )

    # Gerçek (tıbbi/idari) bir talep saldırgan üslupla bile gelse reddedilmez.
    actionable_request = analysis.followup_intent in ACTIONABLE_INTENTS

    # 1) Karşılama yok → katman sessiz, sadece devret.
    if not analysis.matched_greeting:
        if analysis.abusive and not actionable_request:
            reason = "abusive_language"
        elif analysis.has_followup_intent:
            reason = analysis.followup_intent
        else:
            reason = "no_greeting"
        return finish("", "", handled=False, handoff=True, reason=reason)

    opener = _mirror_opener(analysis, hour)

    # 2) Saldırgan/küfürlü içerik (gerçek talep YOK) → sıcak karşılama yerine
    #    sakin, profesyonel, sınır koyan bir devir. Selam ÖDÜL olarak aynalanmaz.
    if analysis.abusive and not actionable_request:
        prefix = _pick(_DEESCALATE_EN if is_en else _DEESCALATE_TR, seed="abuse:" + seed)
        return finish("", prefix, handled=False, handoff=True, reason="abusive_language")

    # 3) Karşılama + gerçek talep → kısa sıcak giriş + aşağı devret (talebi YUTMA).
    if analysis.has_followup_intent:
        if analysis.requires_human_review:
            pool = _PREFIX_EMERGENCY_EN if is_en else _PREFIX_EMERGENCY_TR
        else:
            pool = _PREFIX_EN if is_en else _PREFIX_TR
        prefix = _pick(pool, seed="prefix:" + seed).format(o=opener)
        return finish("", prefix, handled=False, handoff=True, reason=analysis.followup_intent)

    # 4) Veda → kapanış nezaketi, devir yok.
    if analysis.primary_style == "farewell":
        if is_en:
            pool = _FAREWELL_EN
        elif analysis.formality == "informal":
            pool = _FAREWELL_TR_INFORMAL
        else:
            pool = _FAREWELL_TR_FORMAL
        return finish(_pick(pool, seed="bye:" + seed), "", handled=True, handoff=False, reason=None)

    # 5) Saf karşılama / hâl-hatır → sıcak, üsluba aynalı, çeşitlenen reception.
    ack = ""
    if analysis.polite_inquiry:
        ack = _pick(_ACK_EN if is_en else _ACK_TR, seed="ack:" + seed)

    if already_greeted:
        light = _pick(_LIGHT_EN if is_en else _LIGHT_TR, seed="light:" + seed)
        reply = f"{ack}{light}"
        return finish(reply, "", handled=True, handoff=False, reason=None)

    if is_en:
        intro = _pick(_INTRO_EN, seed="intro:" + seed)
        offer = _pick(_OFFER_EN, seed="offer:" + seed)
    elif analysis.formality == "informal":
        intro = _pick(_INTRO_TR_INFORMAL, seed="intro:" + seed)
        offer = _pick(_OFFER_TR_INFORMAL, seed="offer:" + seed)
    else:
        intro = _pick(_INTRO_TR_FORMAL, seed="intro:" + seed)
        offer = _pick(_OFFER_TR_FORMAL, seed="offer:" + seed)

    intro = intro.format(a=assistant_name, c=clinic_name)
    reply = f"{opener}! {ack}{intro} {offer}"
    return finish(reply, "", handled=True, handoff=False, reason=None)


# ── Deterministik sentetik karşılama korpusu (etiketli) ──────────────────────
@dataclass(frozen=True)
class GreetingCase:
    text: str
    expect_style: str
    expect_formality: str
    expect_language: str
    expect_handoff: bool
    expect_human_review: bool = False
    note: str = ""


def synthetic_corpus() -> list[GreetingCase]:
    return [
        # Zaman-temelli
        GreetingCase("Günaydın", "time_of_day", "formal", "tr", False),
        GreetingCase("İyi günler", "time_of_day", "formal", "tr", False),
        GreetingCase("İyi akşamlar", "time_of_day", "formal", "tr", False),
        GreetingCase("Hayırlı sabahlar", "time_of_day", "formal", "tr", False),
        # Standart
        GreetingCase("Merhaba", "standard", "neutral", "tr", False),
        GreetingCase("Merhabalar", "standard", "formal", "tr", False),
        GreetingCase("Selam", "standard", "neutral", "tr", False),
        GreetingCase("Selamlar", "standard", "formal", "tr", False),
        GreetingCase("meraba", "standard", "neutral", "tr", False),
        # Dinî / kültürel
        GreetingCase("Selamün aleyküm", "religious", "formal", "tr", False),
        GreetingCase("Aleykümselam", "religious", "formal", "tr", False),
        GreetingCase("Kolay gelsin", "wellwish", "formal", "tr", False),
        GreetingCase("Hayırlı işler", "wellwish", "formal", "tr", False),
        # Samimi / argo / yazım sapmalı
        GreetingCase("Naber", "informal", "informal", "tr", False),
        GreetingCase("slm", "informal", "informal", "tr", False),
        GreetingCase("mrb", "informal", "informal", "tr", False),
        GreetingCase("Selaaaam", "standard", "neutral", "tr", False),
        GreetingCase("napıyorsun", "informal", "informal", "tr", False),
        # Hâl-hatır
        GreetingCase("Merhaba nasılsınız", "standard", "formal", "tr", False),
        GreetingCase("İyi misiniz", "polite_inquiry", "formal", "tr", False),
        # Emoji
        GreetingCase("👋", "standard", "neutral", "tr", False, note="emoji"),
        # İngilizce
        GreetingCase("Hello", "english", "neutral", "en", False),
        GreetingCase("Hi there", "english", "neutral", "en", False),
        GreetingCase("Good morning", "english", "neutral", "en", False),
        GreetingCase("How are you", "english", "neutral", "en", False),
        GreetingCase("Howdy", "english", "neutral", "en", False),
        # Veda
        GreetingCase("Görüşürüz", "farewell", "neutral", "tr", False),
        GreetingCase("Hoşça kalın", "farewell", "neutral", "tr", False),
        GreetingCase("Goodbye", "farewell", "neutral", "en", False),
        GreetingCase("See you", "farewell", "neutral", "en", False),
        # Karşılama + gerçek talep → DEVİR (yutma yok)
        GreetingCase("Merhaba randevu almak istiyorum", "standard", "neutral", "tr", True, note="book"),
        GreetingCase("İyi günler diş fiyatlarını öğrenebilir miyim", "time_of_day", "formal", "tr", True, note="price"),
        GreetingCase("Selam yarın randevumu iptal etmek istiyorum", "standard", "neutral", "tr", True, note="cancel"),
        GreetingCase("Hello can I book an appointment", "english", "neutral", "en", True, note="book_en"),
        # Karşılama + acil → DEVİR + insan onayı
        GreetingCase("Merhaba nefes alamıyorum", "standard", "neutral", "tr", True, True, note="emergency"),
        GreetingCase("Selam diş etimden kanama durmuyor", "standard", "neutral", "tr", True, True, note="bleeding"),
        # Karşılama + genel soru → DEVİR
        GreetingCase("Merhaba bir şey sormak istiyorum", "standard", "neutral", "tr", True, note="general"),
        # Saçma/anlamsız ek → YUTULMAZ, devredilir (klavye-ezmesi tek jeton olsa bile)
        GreetingCase("Merhaba asdkfjh", "standard", "neutral", "tr", True, note="gibberish"),
        # Saldırgan içerik → sıcak karşılama yok, sakin devir
        GreetingCase("Selam salak mısın", "standard", "neutral", "tr", True, note="abusive"),
    ]


# Saçma/saldırgan girdi denetim probları — motor bunları ASLA sıcak bir saf
# karşılamayla yanıtlamamalı (devreder ya da sakin sınır koyar).
_NONSENSE_PROBES: tuple[str, ...] = (
    "Merhaba asdkfjh",        # selam + klavye-ezmesi (sessiz dizi)
    "Selam zxcvbnm",          # selam + sesli harf içermeyen ezme
    "İyi günler hjklmnp",     # zaman selamı + anlamsız jeton
    "Merhaba 🤬",             # selam + küfür emoji'si
    "Selam salak mısın",      # selam + hakaret
    "Hello you idiot",        # İngilizce selam + hakaret
)


# ── Doğallık denetimi ────────────────────────────────────────────────────────
def _is_natural(reply: str) -> bool:
    """Üretilen nihai metnin biçimsel olarak temiz/doğal olduğunu doğrular."""
    if not reply:
        return True
    if reply != reply.strip() or "  " in reply:
        return False
    if any(bad in reply for bad in (" .", " !", " ?", " ,", "!!", "??", "..", " :")):
        return False
    if "{" in reply or "}" in reply:        # doldurulmamış şablon yuvası
        return False
    return reply[-1] in ".!?"


# ── Denetlenebilir rapor + kapılar ───────────────────────────────────────────
def build_report(corpus: Sequence[GreetingCase] | None = None) -> dict:
    """Karşılama motorunun kapı durumunu denetlenebilir JSON panoya toplar."""
    corpus = list(corpus if corpus is not None else synthetic_corpus())

    results = []
    cov_fail, style_fail, formality_fail, language_fail = [], [], [], []
    handoff_fail, swallow_fail, safety_fail, pii_fail = [], [], [], []
    natural_fail, delay_fail = [], []
    handled_replies: list[str] = []
    delays: list[tuple[int, int]] = []  # (emitted_len, delay)

    for case in corpus:
        analysis = analyze_greeting(case.text)
        turn = compose_reception(case.text, clinic_name="Demo Klinik", hour=14, analysis=analysis)

        cov_ok = analysis.matched_greeting
        style_ok = case.expect_style in analysis.styles
        formality_ok = analysis.formality == case.expect_formality
        language_ok = analysis.language == case.expect_language
        handoff_ok = turn.should_handoff == case.expect_handoff
        swallow_ok = (not turn.handled) if case.expect_handoff else turn.handled
        safety_ok = turn.requires_human_review == case.expect_human_review
        emitted = f"{turn.prefix} {turn.reply}"
        pii_ok = not (_DIGIT_RE.search(case.text) and _DIGIT_RE.search(emitted))
        natural_ok = _is_natural(turn.reply) and _is_natural(turn.prefix.rstrip() + "." if turn.prefix else "")
        delay_ok = DELAY_MIN_MS <= turn.response_delay_ms <= DELAY_MAX_MS

        if turn.handled and turn.reply:
            handled_replies.append(turn.reply)
        emitted_text = turn.reply or turn.prefix
        delays.append((len(emitted_text), turn.response_delay_ms))

        for ok, bucket in (
            (cov_ok, cov_fail), (style_ok, style_fail), (formality_ok, formality_fail),
            (language_ok, language_fail), (handoff_ok, handoff_fail),
            (swallow_ok, swallow_fail), (safety_ok, safety_fail), (pii_ok, pii_fail),
            (natural_ok, natural_fail), (delay_ok, delay_fail),
        ):
            if not ok:
                bucket.append(case.text)

        results.append(
            {
                "text": case.text,
                "primary_style": analysis.primary_style,
                "styles": list(analysis.styles),
                "formality": analysis.formality,
                "language": analysis.language,
                "should_handoff": turn.should_handoff,
                "handoff_reason": turn.handoff_reason,
                "handled": turn.handled,
                "requires_human_review": turn.requires_human_review,
                "response_delay_ms": turn.response_delay_ms,
                "reply": turn.reply,
                "prefix": turn.prefix,
            }
        )

    # Saçma/saldırgan girdi koruması: hiçbir prob sıcak saf-karşılama almamalı.
    guard_fail: list[str] = []
    for probe in _NONSENSE_PROBES:
        t = compose_reception(probe, clinic_name="Demo Klinik", hour=14)
        answered_warmly = t.handled and bool(t.reply) and not t.should_handoff
        if answered_warmly:
            guard_fail.append(probe)

    # Çeşitlilik: saf-karşılama yanıtları yeterince farklı mı?
    distinct = len(set(handled_replies))
    variety_ratio = round(distinct / len(handled_replies), 3) if handled_replies else 1.0
    variety_pass = variety_ratio >= 0.6
    # İnsancıllık: en uzun emitted metnin gecikmesi en kısadan büyük-eşit olmalı.
    by_len = sorted(delays)
    monotone_pass = (not by_len) or (by_len[-1][1] >= by_len[0][1])

    def gate(target: str, fails: list[str]) -> dict:
        return {"target": target, "pass": len(fails) == 0, "failures": fails}

    gates = {
        "coverage": gate("her karşılama biçimi tanınır", cov_fail),
        "style_recognition": gate("beklenen stil tespit edilir", style_fail),
        "formality_mirror": gate("resmiyet doğru çıkarılır", formality_fail),
        "language_mirror": gate("dil doğru aynalanır", language_fail),
        "intent_handoff": gate("talepli selam aşağı devredilir", handoff_fail),
        "no_swallow": gate("gerçek talep yutulmaz / saf selam kapatılır", swallow_fail),
        "safety_escalation": gate("acil/sigorta insan onayına yükseltilir", safety_fail),
        "no_pii_echo": gate("karşılıkta ham kimlik yankılanmaz", pii_fail),
        "naturalness": gate("yanıt biçimsel olarak doğal/temiz", natural_fail),
        "humane_delay": gate("yanıt gecikmesi insancıl aralıkta", delay_fail),
        "nonsense_guard": gate("anlamsız/saldırgan girdi sıcak karşılamayla yanıtlanmaz", guard_fail),
        "response_variety": {
            "target": "saf-karşılama yanıtları çeşitli (≥%60 farklı)",
            "distinct": distinct,
            "total": len(handled_replies),
            "ratio": variety_ratio,
            "pass": bool(variety_pass and monotone_pass),
        },
    }
    overall = all(g["pass"] for g in gates.values())

    return {
        "name": "reception_greeting_engine",
        "ip": "R1",
        "input": {
            "n_cases": len(corpus),
            "styles_covered": sorted({c.expect_style for c in corpus}),
            "handoff_cases": sum(1 for c in corpus if c.expect_handoff),
            "emergency_cases": sum(1 for c in corpus if c.expect_human_review),
            "delay_bounds_ms": [DELAY_MIN_MS, DELAY_MAX_MS],
        },
        "cases": results,
        "gates": gates,
        "overall_pass": bool(overall),
    }


def render(report: dict) -> str:
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    inp = report["input"]
    lines = [
        "İP-R1 — API öncesi karşılama (reception) motoru",
        "=" * 52,
        f"Senaryo: {inp['n_cases']}  (devir {inp['handoff_cases']} · acil {inp['emergency_cases']})",
        f"Kapsanan biçimler: {', '.join(inp['styles_covered'])}",
        "-" * 52,
    ]
    for key, g in report["gates"].items():
        suffix = "" if g["pass"] else f"  → {g.get('failures', g)}"
        extra = f"  ({g['distinct']}/{g['total']} farklı)" if key == "response_variety" else ""
        lines.append(f"{ok(g['pass'])} {key}: {g['target']}{extra}{suffix}")
    lines += [
        "=" * 52,
        f"{ok(report['overall_pass'])} GENEL: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}",
    ]
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="İP-R1 karşılama motoru kanıt panosu")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--demo", action="store_true", help="Örnek karşılamaları göster")
    args = parser.parse_args(argv)

    if args.demo:
        samples = (
            "Günaydın", "İyi akşamlar", "Selamün aleyküm", "Kolay gelsin", "naber",
            "Merhaba", "Selam", "Hello", "Good morning", "👋",
            "Merhaba nasılsınız", "Merhaba randevu almak istiyorum",
            "Merhaba nefes alamıyorum", "Görüşürüz",
        )
        for sample in samples:
            turn = compose_reception(sample, clinic_name="Demo Klinik", hour=10)
            out = turn.reply or f"[devir → {turn.handoff_reason}] {turn.prefix}"
            print(f"  {sample!r:38} ({turn.response_delay_ms:>4} ms) → {out}")
        return 0

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render(report))
    if not args.no_save:
        path = write_artifact(report)
        if not args.json:
            print(f"\nArtefakt: {path}")
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
