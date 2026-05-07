from __future__ import annotations

from dataclasses import dataclass
import json
import re

from anthropic import Anthropic

from app.core.config import get_settings
from app.models import Clinic, ClinicIntent
from app.services.clinical_persona_service import ClinicalPersona, choose_persona
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


def detect_language(text: str, default: str = "tr") -> str:
    lowered = text.lower()
    if any(char in lowered for char in "çğıöşü"):
        return "tr"
    if any(marker in lowered for marker in TURKISH_MARKERS):
        return "tr"
    english_hits = sum(1 for token in ("hello", "appointment", "price", "insurance", "where", "hours") if token in lowered)
    return "en" if english_hits >= 1 else default


def classify_intent(text: str) -> tuple[ClinicIntent, float]:
    normalized = text.lower()
    for intent, keywords in INTENT_KEYWORDS:
        hits = [keyword for keyword in keywords if keyword in normalized]
        if hits:
            confidence = min(0.94, 0.74 + (0.07 * len(hits)))
            if intent == ClinicIntent.MEDICAL_EMERGENCY:
                confidence = 0.99
            return intent, confidence
    if len(re.findall(r"\w+", normalized)) <= 2:
        return ClinicIntent.UNKNOWN, 0.48
    return ClinicIntent.GENERAL_QUESTION, 0.68


def detect_frustration(text: str) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in FRUSTRATION_TERMS)


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


def _structured_prompt(clinic: Clinic, text: str, language: str, intent: ClinicIntent, persona: ClinicalPersona) -> str:
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
- Ask one concise follow-up question when data is missing.
- Return only valid JSON with keys: reply, confidence, intent, action, requires_human_review, risk_reason, data.

Patient message:
{text}
""".strip()


def _try_anthropic_reply(
    clinic: Clinic,
    text: str,
    language: str,
    intent: ClinicIntent,
    persona: ClinicalPersona,
) -> ClinicalAIResult | None:
    settings = get_settings()
    if not settings.clinical_ai_enabled or not settings.anthropic_api_key:
        return None

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=600,
        temperature=0.2,
        messages=[{"role": "user", "content": _structured_prompt(clinic, text, language, intent, persona)}],
    )
    raw = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None

    try:
        parsed_intent = ClinicIntent(payload.get("intent", intent.value))
    except ValueError:
        parsed_intent = intent

    return ClinicalAIResult(
        reply=str(payload.get("reply") or _safe_reply(parsed_intent, language, clinic, persona)),
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


def generate_clinical_reply(
    clinic: Clinic,
    text: str,
    language: str | None = None,
    requested_persona_id: str | None = None,
) -> ClinicalAIResult:
    resolved_language = language or detect_language(text, clinic.default_language)
    intent, intent_confidence = classify_intent(text)
    if intent == ClinicIntent.GENERAL_QUESTION and looks_medical(text):
        intent = ClinicIntent.SYMPTOM_TRIAGE
        intent_confidence = 0.78
    persona = choose_persona(intent, requested_persona_id)

    if intent in {ClinicIntent.SYMPTOM_TRIAGE, ClinicIntent.MEDICAL_EMERGENCY} or looks_medical(text):
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

    anthropic_reply = _try_anthropic_reply(clinic, text, resolved_language, intent, persona)
    if anthropic_reply is not None:
        return anthropic_reply

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

    return ClinicalAIResult(
        reply=_safe_reply(intent, resolved_language, clinic, persona),
        confidence=round(intent_confidence, 2),
        intent=intent,
        action="emergency_guidance" if intent == ClinicIntent.MEDICAL_EMERGENCY else "collect_info",
        persona_id=persona.id,
        persona_name=persona.display_name,
        voice=persona.voice,
        requires_human_review=requires_review,
        risk_reason=risk_reason,
        data={},
        triage_assessment=None,
    )
