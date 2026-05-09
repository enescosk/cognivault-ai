from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

from openai import OpenAI
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.models import Clinic


class MedicalUrgency(str, Enum):
    EMERGENCY = "emergency"
    SAME_DAY = "same_day"
    SOON = "soon"
    ROUTINE = "routine"
    ADMIN = "admin"


class PossibleCondition(BaseModel):
    label: str = Field(max_length=120)
    rationale: str = Field(max_length=300)
    urgency: MedicalUrgency
    confidence: float = Field(ge=0.0, le=1.0)


class TriagePayload(BaseModel):
    urgency: MedicalUrgency
    red_flags: list[str] = Field(default_factory=list, max_length=8)
    possible_conditions: list[PossibleCondition] = Field(default_factory=list, max_length=5)
    recommended_action: str = Field(max_length=500)
    patient_safe_reply: str = Field(max_length=900)
    doctor_summary: str = Field(max_length=900)
    follow_up_questions: list[str] = Field(default_factory=list, max_length=5)
    safety_disclaimer: str = Field(max_length=300)
    requires_doctor_review: bool


@dataclass(frozen=True)
class MedicalTriageAssessment:
    urgency: MedicalUrgency
    red_flags: list[str]
    possible_conditions: list[dict]
    recommended_action: str
    patient_safe_reply: str
    doctor_summary: str
    follow_up_questions: list[str]
    safety_disclaimer: str
    requires_doctor_review: bool
    source: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["urgency"] = self.urgency.value
        return payload


EMERGENCY_TERMS = {
    "nefes alamıyorum": "nefes darlığı",
    "nefes alamiyorum": "nefes darlığı",
    "nefes darlığı": "nefes darlığı",
    "nefes darligi": "nefes darlığı",
    "göğüs": "göğüs ağrısı",
    "gogus": "göğüs ağrısı",
    "göğsüm": "göğüs ağrısı",
    "gogsum": "göğüs ağrısı",
    "şiddetli kanama": "şiddetli kanama",
    "siddetli kanama": "şiddetli kanama",
    "bayıldı": "bayılma",
    "bayildi": "bayılma",
    "felç": "felç belirtisi",
    "felc": "felç belirtisi",
    "yüz kayması": "inme belirtisi",
    "yuz kaymasi": "inme belirtisi",
    "112": "acil yardım ihtiyacı",
}

SAME_DAY_TERMS = {
    "şişlik": "enfeksiyon veya apse şüphesi",
    "sislik": "enfeksiyon veya apse şüphesi",
    "apse": "diş apsesi olasılığı",
    "ateş": "enfeksiyon belirtisi",
    "ates": "enfeksiyon belirtisi",
    "yutamıyorum": "yutma güçlüğü",
    "yutamiyorum": "yutma güçlüğü",
    "travma": "travma",
    "kırıldı": "diş kırığı",
    "kirildi": "diş kırığı",
    "implant ağrısı": "implant çevresi inflamasyon olasılığı",
    "implant agrisi": "implant çevresi inflamasyon olasılığı",
}

DENTAL_TERMS = {
    "diş ağrısı": ("Diş çürüğü, pulpa iltihabı veya diş eti kaynaklı ağrı olabilir.", "same_day"),
    "dis agrisi": ("Diş çürüğü, pulpa iltihabı veya diş eti kaynaklı ağrı olabilir.", "same_day"),
    "kanal": ("Kanal tedavisi ihtiyacı veya mevcut tedavi sonrası hassasiyet olabilir.", "soon"),
    "diş eti": ("Diş eti iltihabı veya periodontal hassasiyet olabilir.", "soon"),
    "dis eti": ("Diş eti iltihabı veya periodontal hassasiyet olabilir.", "soon"),
    "implant": ("İmplant çevresi doku hassasiyeti veya protez uyumu sorunu olabilir.", "soon"),
    "dolgu": ("Dolgu yüksekliği, hassasiyet veya çürük tekrarı olabilir.", "soon"),
    "20lik": ("Gömülü/yirmilik diş iltihabı veya baskı ağrısı olabilir.", "same_day"),
}

SPECIALTY_TERMS = {
    "ben kontrol": ("Dermatolojik lezyon değerlendirmesi gerekebilir.", "soon"),
    "ben aldırma": ("Dermatolojik lezyon değerlendirmesi gerekebilir.", "routine"),
    "ben aldirm": ("Dermatolojik lezyon değerlendirmesi gerekebilir.", "routine"),
    "leke": ("Dermatolojik pigment veya cilt bariyeri sorunu olabilir.", "routine"),
    "döküntü": ("Alerjik, enfeksiyöz veya irritatif döküntü olabilir.", "soon"),
    "dokuntu": ("Alerjik, enfeksiyöz veya irritatif döküntü olabilir.", "soon"),
    "botoks": ("Estetik değerlendirme ve kontrendikasyon sorgusu gerekir.", "routine"),
    "estetik dolgu": ("Estetik dolgu değerlendirmesi ve uygunluk görüşmesi gerekir.", "routine"),
}


def looks_medical(text: str) -> bool:
    lowered = text.lower()
    keywords = set(EMERGENCY_TERMS) | set(SAME_DAY_TERMS) | set(DENTAL_TERMS) | set(SPECIALTY_TERMS)
    symptom_words = {"ağrı", "agri", "sızı", "sizi", "kanama", "şiş", "sis", "ateş", "ates", "kaşıntı", "kasinti"}
    return any(keyword in lowered for keyword in keywords) or any(word in lowered for word in symptom_words)


def _fallback_assessment(text: str, language: str) -> MedicalTriageAssessment:
    lowered = text.lower()
    red_flags = [label for term, label in EMERGENCY_TERMS.items() if term in lowered]
    same_day_flags = [label for term, label in SAME_DAY_TERMS.items() if term in lowered]

    possible: list[dict] = []
    for term, (rationale, urgency_value) in {**DENTAL_TERMS, **SPECIALTY_TERMS}.items():
        if term in lowered:
            possible.append(
                {
                    "label": term.title(),
                    "rationale": rationale,
                    "urgency": urgency_value,
                    "confidence": 0.58,
                }
            )
    for label in same_day_flags:
        possible.append(
            {
                "label": label,
                "rationale": "Hastanın anlattığı belirti aynı gün klinik değerlendirmesi gerektirebilir.",
                "urgency": MedicalUrgency.SAME_DAY.value,
                "confidence": 0.66,
            }
        )

    if red_flags:
        urgency = MedicalUrgency.EMERGENCY
    elif same_day_flags:
        urgency = MedicalUrgency.SAME_DAY
    elif possible:
        urgency = MedicalUrgency.SOON
    else:
        urgency = MedicalUrgency.ROUTINE

    if language == "tr":
        if urgency == MedicalUrgency.EMERGENCY:
            action = "Acil belirti olabilir. 112 veya en yakın acil servise yönlendirin; klinik ekibine de öncelikli not düşüldü."
        elif urgency == MedicalUrgency.SAME_DAY:
            action = "Aynı gün doktor/diş hekimi değerlendirmesi önerilir."
        elif urgency == MedicalUrgency.SOON:
            action = "Klinik değerlendirme için yakın randevu önerilir."
        else:
            action = "Rutin randevu veya resepsiyon takibi uygundur."
        safe_reply = (
            f"Anlattığınız durum {', '.join(item['label'] for item in possible[:2]) or 'birkaç farklı nedenle'} ilişkili olabilir; "
            "bu kesin teşhis değildir. Sizi doktor ekranına not olarak düşüyorum. "
            f"Önerilen aksiyon: {action}"
        )
        disclaimer = "Bu bilgi teşhis veya tedavi önerisi değildir; kesin değerlendirme doktor/diş hekimi tarafından yapılır."
    else:
        action = "Route to clinician review; emergency symptoms require emergency services."
        safe_reply = "Your symptoms may have several possible causes. This is not a diagnosis; I am routing this to the clinician."
        disclaimer = "This is not a diagnosis or treatment recommendation."

    return MedicalTriageAssessment(
        urgency=urgency,
        red_flags=red_flags,
        possible_conditions=possible[:5],
        recommended_action=action,
        patient_safe_reply=safe_reply,
        doctor_summary=f"Hasta ifadesi: {text[:500]}. Aciliyet: {urgency.value}. Olası kategoriler: {possible[:3]}.",
        follow_up_questions=[
            "Ağrı ne zamandır var?",
            "Şişlik, ateş veya kanama var mı?",
            "Daha önce aynı bölgeye işlem yapıldı mı?",
        ],
        safety_disclaimer=disclaimer,
        requires_doctor_review=urgency in {MedicalUrgency.EMERGENCY, MedicalUrgency.SAME_DAY, MedicalUrgency.SOON},
        source="rules",
    )


TRIAGE_JSON_SCHEMA = {
    "name": "medical_triage_payload",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "urgency": {"type": "string", "enum": [item.value for item in MedicalUrgency]},
            "red_flags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            "possible_conditions": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string"},
                        "rationale": {"type": "string"},
                        "urgency": {"type": "string", "enum": [item.value for item in MedicalUrgency]},
                        "confidence": {"type": "number"},
                    },
                    "required": ["label", "rationale", "urgency", "confidence"],
                },
            },
            "recommended_action": {"type": "string"},
            "patient_safe_reply": {"type": "string"},
            "doctor_summary": {"type": "string"},
            "follow_up_questions": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "safety_disclaimer": {"type": "string"},
            "requires_doctor_review": {"type": "boolean"},
        },
        "required": [
            "urgency",
            "red_flags",
            "possible_conditions",
            "recommended_action",
            "patient_safe_reply",
            "doctor_summary",
            "follow_up_questions",
            "safety_disclaimer",
            "requires_doctor_review",
        ],
    },
}


def _triage_prompt(clinic: Clinic, text: str, language: str) -> str:
    return f"""
You are a medical triage assistant for a boutique private clinic / dental clinic.
Clinic: {clinic.name}
Language: {language}

You must not diagnose. You may provide non-definitive possible condition categories that match symptoms.
Use phrasing like "may be compatible with", "could be related to", or Turkish "ilişkili olabilir".
Never say the patient has a disease. Never prescribe medication, dosage, or treatment.
Always identify red flags and urgency. Route uncertain or medical content to clinician review.

Return valid JSON that follows the schema exactly.

Patient message:
{text}
""".strip()


def _try_openai_triage(clinic: Clinic, text: str, language: str) -> MedicalTriageAssessment | None:
    settings = get_settings()
    if not settings.clinical_ai_enabled or not settings.openai_api_key:
        return None

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": "Return only JSON. You are safe clinical triage support, not a diagnosing physician.",
                },
                {"role": "user", "content": _triage_prompt(clinic, text, language)},
            ],
            response_format={"type": "json_schema", "json_schema": TRIAGE_JSON_SCHEMA},
        )
        content = response.choices[0].message.content or ""
        payload = TriagePayload.model_validate_json(content)
    except Exception:
        return None

    return MedicalTriageAssessment(
        urgency=payload.urgency,
        red_flags=payload.red_flags,
        possible_conditions=[item.model_dump() for item in payload.possible_conditions],
        recommended_action=payload.recommended_action,
        patient_safe_reply=payload.patient_safe_reply,
        doctor_summary=payload.doctor_summary,
        follow_up_questions=payload.follow_up_questions,
        safety_disclaimer=payload.safety_disclaimer,
        requires_doctor_review=payload.requires_doctor_review,
        source="openai_structured",
    )


def assess_medical_triage(clinic: Clinic, text: str, language: str) -> MedicalTriageAssessment:
    if not looks_medical(text):
        return _fallback_assessment(text, language)
    return _try_openai_triage(clinic, text, language) or _fallback_assessment(text, language)
