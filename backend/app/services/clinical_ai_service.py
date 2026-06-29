from __future__ import annotations

from dataclasses import dataclass
import math
import re

from app.ai.ai_factory import OpenAIProvider, get_llm_provider, parse_model_json
from app.ai.runtime import complete_json
from app.core.config import get_settings
from app.clinical.normalizer import triage
from app.clinical.ontology import normalize_tr
from app.models import Clinic, ClinicIntent
from app.services.clinical_compliance_service import build_governance_context, mask_identifiers
from app.services.clinical_persona_service import ClinicalPersona, choose_persona
from app.services.clinical_slot_service import build_slot_decision
from app.services.customer_understanding import rank_intents, understand_primary_intent
from app.services.medical_triage_service import MedicalUrgency, assess_medical_triage, looks_medical


@dataclass(frozen=True)
class ClinicalAIResult:
    reply: str
    confidence: float
    intent: ClinicIntent
    action: str
    persona_id: str
    persona_name: str
    voice: str
    requires_human_review: bool
    risk_reason: str | None = None
    data: dict | None = None
    triage_assessment: dict | None = None


TURKISH_MARKERS = {
    "merhaba",
    "selam",
    "randevu",
    "fiyat",
    "ucret",
    "ücret",
    "sigorta",
    "sgk",
    "adres",
    "saat",
    "yarin",
    "yarın",
    "iptal",
}

INTENT_KEYWORDS: list[tuple[ClinicIntent, set[str]]] = [
    (ClinicIntent.MEDICAL_EMERGENCY, {"acil", "kanama", "bayildi", "bayıldı", "nefes", "gogus", "göğüs", "kalp", "112"}),
    (ClinicIntent.SYMPTOM_TRIAGE, {"ağrı", "agri", "sızı", "sizi", "şişlik", "sislik", "apse", "ateş", "ates", "implant", "diş", "dis", "kanal", "dolgu", "diş eti", "dis eti", "döküntü", "dokuntu"}),
    (ClinicIntent.RESCHEDULE_APPOINTMENT, {"ertelemek", "degistirmek", "değiştirmek", "reschedule", "baska saat", "başka saat"}),
    (ClinicIntent.CANCEL_APPOINTMENT, {"iptal", "cancel"}),
    (ClinicIntent.BOOK_APPOINTMENT, {"randevu", "appointment", "musait", "müsait", "yarin", "yarın", "bugun", "bugün"}),
    (ClinicIntent.ASK_PRICE, {"fiyat", "ucret", "ücret", "price", "ne kadar"}),
    (ClinicIntent.ASK_INSURANCE, {"sgk", "sigorta", "insurance", "tamamlayici", "tamamlayıcı"}),
    (ClinicIntent.ASK_LOCATION, {"adres", "konum", "nerede", "location"}),
    (ClinicIntent.ASK_WORKING_HOURS, {"saat", "kacta", "kaçta", "working hours", "acik", "açık"}),
]

FRUSTRATION_TERMS = {"sinir", "kizgin", "kızgın", "şikayet", "sikayet", "cevap vermiyorsunuz", "rezalet", "bekliyorum"}

DENTAL_APPOINTMENT_TERMS = {
    "diş",
    "dis",
    "dişim",
    "disim",
    "ağrı",
    "agri",
    "ağrıyor",
    "agriyor",
    "zonkluyor",
    "dolgu",
    "dolgum",
    "kanal",
    "implant",
    "diş eti",
    "dis eti",
    "braket",
    "tel",
    "ortodonti",
    "çekim",
    "cekim",
    "beyazlatma",
    "çocuğum",
    "cocugum",
    "akne",
    "sivilce",
    "leke",
    "ben",
    "egzama",
    "saç",
    "sac",
    "botoks",
    "dudak dolgusu",
    "lazer",
    "cilt bakımı",
    "cilt bakimi",
    "muayene",
    "kontrol",
}

def detect_language(text: str, default: str = "tr") -> str:
    lowered = text.lower()
    if any(char in lowered for char in "çğıöşü"):
        return "tr"
    if any(marker in lowered for marker in TURKISH_MARKERS):
        return "tr"
    english_hits = sum(1 for token in ("hello", "appointment", "price", "insurance", "where", "hours") if token in lowered)
    return "en" if english_hits >= 1 else default


def classify_intent(text: str) -> tuple[ClinicIntent, float]:
    understanding = understand_primary_intent(text)
    return ClinicIntent(understanding.intent), understanding.confidence


def detect_frustration(text: str) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in FRUSTRATION_TERMS)


# ─────────────────────────────────────────────────────────────────────────────
# Faz 2 — Research-driven AI signals (Gemini Deep Research 2026-05-25)
# ConversationDetailPage.tsx'in beklediği metadata sinyallerini üretir.
# Referans: docs/research/gemini-deep-research-2026-05-25.md
# ─────────────────────────────────────────────────────────────────────────────

# Bölüm F#9 — sentiment trajectory. Hafif kural tabanlı lexicon; LLM ekleyince
# bu fonksiyon yerine modelin döndüğü skor kullanılır.
SENTIMENT_VERY_NEGATIVE_TERMS: set[str] = {
    "tüküreyim", "tukureyim", "rezalet", "rezil", "berbat", "iğrenç", "igrenc",
    "saçmalık", "sacmalik", "intihar", "öldüreceğim", "oldurecegim",
    "şikayet edeceğim", "sikayet edecegim", "dava açacağım", "dava acacagim",
}
SENTIMENT_NEGATIVE_TERMS: set[str] = {
    "kızgın", "kizgin", "sinir", "öfke", "ofke", "çok kötü", "cok kotu",
    "memnun değilim", "memnun degilim", "yetersiz", "yavaş", "yavas",
    "geç kaldınız", "gec kaldiniz", "cevap vermiyorsunuz", "bekliyorum",
    "ilgilenmiyor", "ağrım", "agrim", "ağrıyor", "agriyor", "şikayet", "sikayet",
    "üzgünüm", "uzgunum", "korkuyorum",
}
SENTIMENT_POSITIVE_TERMS: set[str] = {
    "teşekkür", "tesekkur", "sağolun", "sagolun", "harika", "süper", "super",
    "memnunum", "iyi", "güzel", "guzel", "anladım", "anladim", "tamam",
    "olur", "uygun", "evet", "lütfen", "lutfen", "rica", "elinize sağlık",
    "elinize saglik",
}


def analyze_sentiment(text: str) -> float:
    """
    Hasta mesajının duygu skorunu -1..1 aralığında döndürür.
    Çok negatif kelimeler 2 katı ağırlık taşır. Lexicon temelli — LLM
    eklendiğinde modelden gelen skorla değiştirilir.
    """
    if not text:
        return 0.0
    normalized = text.lower()
    score = 0.0
    weight_total = 0
    for term in SENTIMENT_VERY_NEGATIVE_TERMS:
        if term in normalized:
            score -= 2.0
            weight_total += 2
    for term in SENTIMENT_NEGATIVE_TERMS:
        if term in normalized:
            score -= 1.0
            weight_total += 1
    for term in SENTIMENT_POSITIVE_TERMS:
        if term in normalized:
            score += 1.0
            weight_total += 1
    if weight_total == 0:
        return 0.0
    # Normalize ve clamp
    normalized_score = score / max(weight_total, 1)
    return max(-1.0, min(1.0, round(normalized_score, 2)))


def detect_multi_intents(text: str, primary: ClinicIntent | None = None) -> list[str]:
    """
    Bölüm A8 — multi-intent yönetimi. Tek bir mesajda birden fazla niyet
    olabilir ("randevuyu erteleyelim, fiyatı sorayım, sigorta geçer mi").
    Primary haricinde tespit edilen ikincil niyetleri döndürür.
    """
    detected = [item.intent for item in rank_intents(text)]
    # primary intent zaten conversation/message üst seviyesinde gösteriliyor;
    # ikincilleri ayrı alanda göstermek için ondan çıkar.
    if primary is not None and primary.value in detected:
        detected.remove(primary.value)
    return detected


def assess_hallucination_risk(
    reply: str,
    intent: ClinicIntent,
    slot_decision: dict | None,
) -> tuple[bool, str | None]:
    """
    Bölüm B#1 — hallucinated availability.
    AI cevabı içerisinde net bir saat veya gün öneriyor mu? Eğer öneriyor ama
    `slot_decision` `ok`/`offered` statüsünde değilse hayali slot riski var demektir.

    Returns:
        (risk, reason)
    """
    if not reply:
        return False, None
    if intent != ClinicIntent.BOOK_APPOINTMENT:
        # Sadece randevu önerme akışında anlamlı bir risktir
        return False, None

    # Saat içerimi: "14:30", "saat 14", "yarın 11'de"
    has_specific_time = bool(
        re.search(r"\b\d{1,2}[:.]\d{2}\b", reply)
        or re.search(r"\bsaat\s*\d{1,2}\b", reply.lower())
        or re.search(r"\b\d{1,2}['’]?(de|da|te|ta)\b", reply.lower())
    )
    if not has_specific_time:
        return False, None

    status = (slot_decision or {}).get("status")
    # ok / offered / suggested → slot service gerçek bir teklif üretti.
    # full / waitlist / doctor_review / fallback → gerçek müsait slot yok ama AI saat verdi.
    if status in {"ok", "offered", "suggested"}:
        return False, None
    return True, f"specific_time_without_real_slot:{status or 'unknown'}"


def derive_consent_signal(governance: dict) -> dict[str, str | bool]:
    """
    Bölüm C — KVKK consent ispatlanabilirliği.
    Şu an gerçek bir consent flow yok (Faz 3 işi); ama compliance katmanından
    "yurt dışı aktarım kapalı mı, hangi processor'lar açık mı" sinyalini
    UI için yapılandırılmış bir nesneye çeviriyoruz. Gerçek IVR/buton onayı
    geldiğinde bu fonksiyon onu birlikte ele alacak.
    """
    auto_send_allowed = bool(governance.get("auto_send_allowed"))
    residency = governance.get("data_residency_mode") or "unknown"
    # Onay henüz alınmadı → pending. Local-first mode + auto_send_allowed → "pending"
    # External processor aktif ve auto_send değil → "rejected" benzeri yüksek risk
    if not auto_send_allowed:
        status: str = "rejected"
    else:
        status = "pending"
    return {
        "status": status,
        "residency": residency,
        "granted_via": "notice_only_local_processing" if status == "pending" else "blocked_by_compliance",
        "version": "v1-explicit-gate",
    }


def extract_clinical_intake(text: str) -> dict:
    # İP-1 klinik motoru üzerinden tek yol: normalizer.triage() argo genişletme +
    # branş eşleme + aciliyet değerlendirmeyi birlikte yapar. Böylece İP-1.7'nin
    # yüksek-recall acil tespiti (kanonik ACİL terimleri + assess_urgency) bu
    # servis yolundan da geçerli; sabit-kodlu override'lara gerek kalmaz.
    result = triage(text)
    specialty = result.specialty.specialty
    normalized = normalize_tr(text)

    preferred_time = None
    if "bugun" in normalized:
        preferred_time = "bugün"
    elif "yarin" in normalized:
        preferred_time = "yarın"
    else:
        weekday_match = re.search(r"\b(pazartesi|sali|sali|carsamba|persembe|cuma|cumartesi|pazar)\b", normalized)
        if weekday_match:
            preferred_time = weekday_match.group(1)

    return {
        "specialty": specialty.display_tr,
        "specialty_code": specialty.code,
        "routing_reason": specialty.routing_reason,
        "preferred_time": preferred_time,
        "urgency": result.urgency.value,
        "complaint_summary": text.strip()[:240],
    }


def _looks_like_planning_reply(reply: str) -> bool:
    normalized = normalize_tr(reply)
    planning_markers = [
        "su anki plan goruntuleniyor",
        "neleri degistirmek istersiniz",
        "brainstorming raporu",
        "benzeri yapay zeka randevu sistemleri",
        "(1)",
        "(2)",
        "(3)",
    ]
    return any(marker in normalized for marker in planning_markers)


def _safe_reply(intent: ClinicIntent, language: str, clinic: Clinic, persona: ClinicalPersona) -> str:
    is_tr = language == "tr"
    if intent == ClinicIntent.MEDICAL_EMERGENCY:
        return (
            "Ben Can. Bu durum acil olabilir. Lütfen 112'yi arayın veya en yakın acil servise başvurun. Klinik ekibine de insan onayı için not düşüyorum."
            if is_tr
            else clinic.emergency_disclaimer
        )
    if intent == ClinicIntent.BOOK_APPOINTMENT:
        return (
            "Ben Selin. Tabii, randevu için size yardımcı olabilirim. Hangi bölüm ve hangi gün/saat aralığı sizin için uygun?"
            if is_tr
            else "Of course. Which department and date or time range would work for you?"
        )
    if intent == ClinicIntent.RESCHEDULE_APPOINTMENT:
        return (
            "Elbette. Mevcut randevu gününüzü ve tercih ettiğiniz yeni zamanı paylaşır mısınız?"
            if is_tr
            else "Sure. Please share your current appointment time and the new time you prefer."
        )
    if intent == ClinicIntent.CANCEL_APPOINTMENT:
        return (
            "Randevu iptali için yardımcı olurum. Doğrulama amacıyla randevu tarihini veya kayıtlı telefon numaranızı paylaşır mısınız?"
            if is_tr
            else "I can help with cancellation. Please share the appointment date or registered phone number for verification."
        )
    if intent == ClinicIntent.ASK_PRICE:
        return (
            "Ben Arzu. Fiyat bilgisi işlem ve hekime göre değişebilir. Size doğru bilgi verebilmem için hangi işlem veya bölüm için soruyorsunuz?"
            if is_tr
            else "Pricing can vary by procedure and clinician. Which service or department are you asking about?"
        )
    if intent == ClinicIntent.ASK_INSURANCE:
        return (
            "Ben Arzu. SGK veya özel sigorta durumunu kontrol edebiliriz. Hangi sigorta türünü kullanıyorsunuz?"
            if is_tr
            else "We can check insurance coverage. Which insurance type would you like to use?"
        )
    if intent == ClinicIntent.ASK_LOCATION:
        return (
            "Kliniğimizin konum bilgisini paylaşabilirim. Hangi şube için adres istiyorsunuz?"
            if is_tr
            else "I can share the clinic location. Which branch do you need?"
        )
    if intent == ClinicIntent.ASK_WORKING_HOURS:
        return (
            "Çalışma saatlerini paylaşabilirim. Hangi şube veya bölüm için öğrenmek istersiniz?"
            if is_tr
            else "I can share working hours. Which branch or department are you asking about?"
        )
    return (
        f"Ben {persona.display_name}. Mesajınızı aldım. Size doğru yardımcı olabilmem için talebinizi biraz daha detaylandırır mısınız?"
        if is_tr
        else "I received your message. Could you add a little more detail so I can help accurately?"
    )


def _appointment_reply(language: str, persona: ClinicalPersona, intake: dict, slot_decision: dict) -> str:
    specialty = intake["specialty"]
    preferred_time = intake.get("preferred_time")
    if language == "tr":
        slot_offer = slot_decision.get("patient_offer")
        if slot_decision.get("status") in {"full", "waitlist", "doctor_review"}:
            return (
                f"Ben {persona.display_name}. Şikayetinizi {specialty} için randevu talebi olarak aldım. "
                f"{slot_offer} "
                "Ağrı, şişlik, kanama veya hızlı kötüleşme varsa bunu doktor ekranına öncelikli not olarak düşüyorum."
            )
        time_part = f" {preferred_time} için" if preferred_time else ""
        return (
            f"Ben {persona.display_name}. Şikayetinizi {specialty} için randevu talebi olarak not aldım.{time_part} "
            f"{slot_offer} "
            "Randevuyu netleştirebilmem için tercih ettiğiniz saat aralığını ve hastanın ad-soyad bilgisini paylaşır mısınız? "
            "Ağrı, şişlik veya kanama hızla artıyorsa sizi insan operatöre de öncelikli aktaracağım."
        )
    time_part = f" for {preferred_time}" if preferred_time else ""
    return (
        f"This sounds like a {specialty} appointment request{time_part}. "
        "Please share the preferred time window and the patient's full name so I can check availability. "
        "If pain, swelling, or bleeding is rapidly worsening, I will escalate to a human operator."
    )


def _structured_prompt(clinic: Clinic, text: str, language: str, intent: ClinicIntent, persona: ClinicalPersona) -> str:
    # KVKK veri minimizasyonu: hasta mesajındaki kimlik tanımlayıcıları (TC, kart,
    # e-posta, telefon) LLM'e (lokal dahil) gönderilmeden önce maskelenir. Şikayet
    # metni korunur, sadece tanımlayıcılar [REDACTED]'a çevrilir.
    safe_text = mask_identifiers(text).replace("</patient_message>", "[BLOCKED_TAG]")
    return f"""
You are CogniVault AI, a safe multilingual AI receptionist for a medical clinic.
Clinic: {clinic.name}
Language: {language}
Detected intent: {intent.value}
Persona: {persona.display_name}
Persona role: {persona.role}
Persona tone: {persona.tone}
Persona specialty: {persona.specialty}

Rules:
- Never diagnose or give medical treatment instructions.
- For emergency symptoms, recommend emergency services.
- Follow this persona safety rule: {persona.safety_rule}
- Treat health complaints as special category data. Collect only the minimum data needed for appointment routing.
- Do not ask for national ID, card, insurance member details, or voice recording consent unless the compliance layer explicitly allows it.
- If insurance verification, identity lookup, urgent symptoms, or uncertain medical content appears, prepare a human-review draft instead of a final medical answer.
- Ask one concise follow-up question when data is missing.
- Return only valid JSON with keys: reply, confidence, intent, action, requires_human_review, risk_reason, data.

Patient message:
<patient_message>{safe_text}</patient_message>
""".strip()


_UNSAFE_MEDICAL_REPLY_PATTERNS = (
    r"\b(antibiyotik|antibiotic|agri kesici|ağrı kesici) (kullan|al|basla|başla)",
    r"\b\d+(?:[.,]\d+)?\s*(mg|ml|tablet|kapsul|kapsül)\b",
    r"\b(kesin|definitely) (enfeksiyon|curuk|çürük|kanser|tani|tanı|diagnosis)",
    r"\b(teshisiniz|teşhisiniz|taniniz|tanınız)\b",
)


def _contains_unsafe_medical_advice(reply: str) -> bool:
    normalized = normalize_tr(reply)
    return any(re.search(pattern, normalized) for pattern in _UNSAFE_MEDICAL_REPLY_PATTERNS)


def _validated_provider_result(
    payload: dict,
    *,
    deterministic_intent: ClinicIntent,
    deterministic_confidence: float,
    language: str,
    clinic: Clinic,
    persona: ClinicalPersona,
) -> ClinicalAIResult | None:
    if not isinstance(payload, dict):
        return None

    invalid_intent = False
    try:
        model_intent = ClinicIntent(payload.get("intent", deterministic_intent.value))
    except ValueError:
        invalid_intent = True
        model_intent = deterministic_intent

    intent_conflict = model_intent != deterministic_intent
    if deterministic_intent == ClinicIntent.MEDICAL_EMERGENCY or (
        deterministic_confidence >= 0.85 and intent_conflict
    ):
        final_intent = deterministic_intent
    else:
        final_intent = model_intent

    raw_reply = payload.get("reply")
    reply = raw_reply.strip() if isinstance(raw_reply, str) else ""
    if not reply or len(reply) > 1200 or _looks_like_planning_reply(reply):
        reply = _safe_reply(final_intent, language, clinic, persona)
    if deterministic_intent == ClinicIntent.MEDICAL_EMERGENCY and intent_conflict:
        reply = _safe_reply(ClinicIntent.MEDICAL_EMERGENCY, language, clinic, persona)

    unsafe_medical_reply = _contains_unsafe_medical_advice(reply)
    if unsafe_medical_reply:
        reply = _safe_reply(final_intent, language, clinic, persona)

    try:
        model_confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        model_confidence = 0.0
    if not math.isfinite(model_confidence):
        model_confidence = 0.0
    confidence = max(0.0, min(1.0, model_confidence))
    if final_intent == deterministic_intent:
        confidence = max(confidence, deterministic_confidence)

    requires_review = payload.get("requires_human_review") is True
    risk_reason = payload.get("risk_reason") if isinstance(payload.get("risk_reason"), str) else None
    if final_intent == ClinicIntent.MEDICAL_EMERGENCY:
        requires_review = True
        risk_reason = "medical_emergency_guardrail"
    elif unsafe_medical_reply:
        requires_review = True
        risk_reason = "unsafe_model_medical_advice"
    elif intent_conflict or invalid_intent:
        requires_review = True
        risk_reason = risk_reason or ("invalid_model_intent" if invalid_intent else "model_rule_intent_conflict")
    elif confidence < getattr(clinic, "ai_auto_reply_threshold", 0.9):
        requires_review = True
        risk_reason = risk_reason or "confidence_below_auto_reply_threshold"

    safe_actions = {
        ClinicIntent.MEDICAL_EMERGENCY: "emergency_guidance",
        ClinicIntent.BOOK_APPOINTMENT: "collect_appointment_details",
        ClinicIntent.RESCHEDULE_APPOINTMENT: "collect_reschedule_details",
        ClinicIntent.CANCEL_APPOINTMENT: "collect_cancellation_details",
        ClinicIntent.ASK_PRICE: "collect_service_for_price",
        ClinicIntent.ASK_INSURANCE: "collect_insurance_type",
        ClinicIntent.ASK_LOCATION: "collect_branch",
        ClinicIntent.ASK_WORKING_HOURS: "collect_branch",
        ClinicIntent.GENERAL_QUESTION: "collect_info",
        ClinicIntent.UNKNOWN: "clarify_request",
        ClinicIntent.SYMPTOM_TRIAGE: "medical_triage",
    }

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return ClinicalAIResult(
        reply=reply,
        confidence=round(confidence, 2),
        intent=final_intent,
        action=safe_actions[final_intent],
        persona_id=persona.id,
        persona_name=persona.display_name,
        voice=persona.voice,
        requires_human_review=requires_review,
        risk_reason=risk_reason,
        data=data,
    )


def _try_runtime_reply(
    clinic: Clinic,
    text: str,
    language: str,
    intent: ClinicIntent,
    persona: ClinicalPersona,
    governance: dict,
) -> ClinicalAIResult | None:
    settings = get_settings()
    if not settings.clinical_ai_enabled:
        return None
    if not settings.clinical_external_ai_allowed:
        return None
    if not governance.get("external_transfer_allowed", False):
        return None
    if "special_category_health_data" in governance.get("data_classes", []):
        return None
    if "financial_or_insurance_data" in governance.get("data_classes", []):
        return None

    try:
        payload = complete_json(
            system_prompt=(
                "You are CogniVault's clinical reception safety layer. "
                "Return strictly valid JSON and never diagnose, prescribe, or give treatment instructions."
            ),
            user_prompt=_structured_prompt(clinic, text, language, intent, persona),
            max_tokens=600,
            temperature=0.2,
        )
    except Exception:  # noqa: BLE001 - optional runtime must not block deterministic/provider fallback.
        return None
    if not payload:
        return None

    try:
        parsed_intent = ClinicIntent(payload.get("intent", intent.value))
    except ValueError:
        parsed_intent = intent

    reply = str(payload.get("reply") or _safe_reply(parsed_intent, language, clinic, persona))
    if _looks_like_planning_reply(reply):
        return None

    return ClinicalAIResult(
        reply=reply,
        confidence=float(payload.get("confidence") or 0.0),
        intent=parsed_intent,
        action=str(payload.get("action") or "collect_info"),
        persona_id=persona.id,
        persona_name=persona.display_name,
        voice=persona.voice,
        requires_human_review=bool(payload.get("requires_human_review", False)),
        risk_reason=payload.get("risk_reason"),
        data=payload.get("data") if isinstance(payload.get("data"), dict) else {},
        triage_assessment=None,
    )


def _attach_governance(result: ClinicalAIResult, governance: dict) -> ClinicalAIResult:
    """LLM cevabına gizlilik/yönetişim bağlamını ekler ve insan-inceleme bayrağını günceller."""
    data = {**(result.data or {}), "privacy_guardrail": governance}
    requires_human_review = result.requires_human_review or not governance["auto_send_allowed"]
    risk_reason = result.risk_reason
    if requires_human_review and risk_reason is None:
        risk_reason = (
            governance["human_review_reasons"][0]
            if governance["human_review_reasons"]
            else "requires_human_review"
        )
    return ClinicalAIResult(
        reply=result.reply,
        confidence=result.confidence,
        intent=result.intent,
        action=result.action,
        persona_id=result.persona_id,
        persona_name=result.persona_name,
        voice=result.voice,
        requires_human_review=requires_human_review,
        risk_reason=risk_reason,
        data=data,
    )


def generate_clinical_reply(
    clinic: Clinic,
    text: str,
    language: str | None = None,
    requested_persona_id: str | None = None,
    use_ai: bool = True,
    previous_intent: ClinicIntent | None = None,
    external_ai_consent: bool = False,
) -> ClinicalAIResult:
    """use_ai=False → LLM'i atla, kural-tabanlı (hızlı) yolu kullan.

    Hasta sayfası rehberli akışında LLM cevabı kullanılmıyor; sadece intent,
    intake (branş) ve slot_decision lazım. Bunlar kural-tabanlı üretildiği için
    use_ai=False ile çağrı ~anında döner (lokal LLM'in ~6 sn'si yerine).
    """
    resolved_language = language or detect_language(text, clinic.default_language)
    intent, intent_confidence = classify_intent(text)
    if intent == ClinicIntent.GENERAL_QUESTION and looks_medical(text):
        intent = ClinicIntent.SYMPTOM_TRIAGE
        intent_confidence = 0.78
    persona = choose_persona(intent, requested_persona_id)

    if intent in {ClinicIntent.SYMPTOM_TRIAGE, ClinicIntent.MEDICAL_EMERGENCY}:
        triage = assess_medical_triage(clinic, text, resolved_language)
        if triage.urgency == MedicalUrgency.EMERGENCY:
            intent = ClinicIntent.MEDICAL_EMERGENCY
            persona = choose_persona(intent, requested_persona_id)
        risk_reason = (
            "medical_emergency_guardrail"
            if triage.urgency == MedicalUrgency.EMERGENCY
            else f"medical_triage_{triage.urgency.value}"
        )
        return ClinicalAIResult(
            reply=triage.patient_safe_reply,
            confidence=0.93 if triage.urgency == MedicalUrgency.EMERGENCY else max(intent_confidence, 0.82),
            intent=intent,
            action="medical_triage",
            persona_id=persona.id,
            persona_name=persona.display_name,
            voice=persona.voice,
            requires_human_review=triage.requires_doctor_review,
            risk_reason=risk_reason,
            data={
                "recommended_action": triage.recommended_action,
                "doctor_summary": triage.doctor_summary,
                "follow_up_questions": triage.follow_up_questions,
                "red_flags": triage.red_flags,
                "possible_conditions": triage.possible_conditions,
            },
            triage_assessment=triage.to_dict(),
        )

    governance = build_governance_context(clinic, text, intent, resolved_language).as_dict()
    intake = extract_clinical_intake(text)
    slot_decision = build_slot_decision(intake)

    if use_ai:
        runtime_reply = _try_runtime_reply(clinic, text, resolved_language, intent, persona, governance)
        if runtime_reply is not None:
            return runtime_reply

    settings = get_settings()
    if use_ai and settings.clinical_ai_enabled:
        effective_external_transfer = bool(governance["external_transfer_allowed"] and external_ai_consent)
        provider = get_llm_provider(governance["data_residency_mode"], effective_external_transfer)
        system_prompt = (
            "You are a JSON-only clinical receptionist API. "
            "Always return valid JSON with keys: reply (string, Turkish unless lang says otherwise), "
            "confidence (0-1 float), intent (one of: "
            "book_appointment, reschedule_appointment, cancel_appointment, ask_price, "
            "ask_insurance, ask_location, ask_working_hours, medical_emergency, "
            "general_question, unknown), action (snake_case string), "
            "requires_human_review (bool), risk_reason (string|null), data (object)."
        )
        prompt = _structured_prompt(clinic, text, resolved_language, intent, persona)
        payload = provider.generate_chat_reply(
            prompt,
            system_prompt,
            organization_id=getattr(clinic, "organization_id", None)
        )
        provider_trace: list[dict[str, str]] = []
        if payload is not None:
            provider_source = str(payload.pop("_provider_source", "unknown"))
            if (
                provider_source == "deterministic_local_fallback"
                and effective_external_transfer
                and settings.clinical_external_ai_allowed
                and settings.openai_api_key
            ):
                provider_trace.append({"provider": provider_source, "status": "held_as_safe_fallback"})
                openai_payload = OpenAIProvider().generate_chat_reply(
                    prompt,
                    system_prompt,
                    organization_id=getattr(clinic, "organization_id", None),
                )
                if openai_payload is not None:
                    payload = openai_payload
                    provider_source = str(payload.pop("_provider_source", "openai"))
            provider_trace.append({"provider": provider_source, "status": "selected"})
            ai_result = _validated_provider_result(
                payload,
                deterministic_intent=intent,
                deterministic_confidence=intent_confidence,
                language=resolved_language,
                clinic=clinic,
                persona=persona,
            )
            if ai_result is not None:
                ai_result = ClinicalAIResult(
                    reply=ai_result.reply,
                    confidence=ai_result.confidence,
                    intent=ai_result.intent,
                    action=ai_result.action,
                    persona_id=ai_result.persona_id,
                    persona_name=ai_result.persona_name,
                    voice=ai_result.voice,
                    requires_human_review=ai_result.requires_human_review,
                    risk_reason=ai_result.risk_reason,
                    data={
                        **(ai_result.data or {}),
                        "provider_source": provider_source,
                        "provider_trace": provider_trace,
                        "external_ai_consent_verified": external_ai_consent,
                    },
                )
                return _attach_governance(ai_result, governance)

    # Rule-based fallback
    risk_reason = None
    requires_review = False
    if intent == ClinicIntent.MEDICAL_EMERGENCY:
        risk_reason = "medical_emergency_guardrail"
        requires_review = True
    elif detect_frustration(text):
        risk_reason = "patient_frustration_detected"
        requires_review = True
        intent_confidence = min(intent_confidence, 0.72)
    elif intent_confidence < clinic.ai_auto_reply_threshold:
        risk_reason = "confidence_below_auto_reply_threshold"
        requires_review = True

    action = "emergency_guidance" if intent == ClinicIntent.MEDICAL_EMERGENCY else "collect_info"
    reply = _safe_reply(intent, resolved_language, clinic, persona)
    if intent == ClinicIntent.BOOK_APPOINTMENT:
        action = "collect_appointment_details"
        reply = _appointment_reply(resolved_language, persona, intake, slot_decision)
        requires_review = requires_review or intake["urgency"] == "priority" or slot_decision["status"] == "doctor_review"
        risk_reason = risk_reason or ("priority_dental_symptom" if intake["urgency"] == "priority" else None)
    if not governance["auto_send_allowed"]:
        requires_review = True
        risk_reason = risk_reason or governance["human_review_reasons"][0]

    return ClinicalAIResult(
        reply=reply,
        confidence=round(intent_confidence, 2),
        intent=intent,
        action=action,
        persona_id=persona.id,
        persona_name=persona.display_name,
        voice=persona.voice,
        requires_human_review=requires_review,
        risk_reason=risk_reason,
        data={"intake": intake, "slot_decision": slot_decision},
        triage_assessment=None,
    )
