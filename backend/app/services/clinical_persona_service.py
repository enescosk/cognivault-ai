from __future__ import annotations

from dataclasses import dataclass

from app.models import ClinicIntent


@dataclass(frozen=True)
class ClinicalPersona:
    id: str
    display_name: str
    role: str
    voice: str
    tone: str
    specialty: str
    safety_rule: str


PERSONAS: dict[str, ClinicalPersona] = {
    "selin": ClinicalPersona(
        id="selin",
        display_name="Selin",
        role="Multilingual medical receptionist",
        voice="nova",
        tone="warm, fast, calm and appointment-oriented",
        specialty="appointment booking, rescheduling, intake, location and working-hours questions",
        safety_rule="Collect missing appointment details without giving medical advice.",
    ),
    "arzu": ClinicalPersona(
        id="arzu",
        display_name="Arzu",
        role="Insurance and clinic operations specialist",
        voice="shimmer",
        tone="precise, reassuring and policy-aware",
        specialty="pricing, SGK/private insurance, branch operations and administrative follow-up",
        safety_rule="Avoid final financial promises unless clinic policy data is explicit.",
    ),
    "can": ClinicalPersona(
        id="can",
        display_name="Can",
        role="Clinical safety and escalation guardian",
        voice="onyx",
        tone="serious, concise and safety-first",
        specialty="medical emergency detection, risky medical questions, frustration and human escalation",
        safety_rule="Never diagnose; emergency symptoms must be routed to emergency care and human review.",
    ),
}

DEFAULT_PERSONA_ID = "selin"

PERSONA_BY_INTENT: dict[ClinicIntent, str] = {
    ClinicIntent.BOOK_APPOINTMENT: "selin",
    ClinicIntent.RESCHEDULE_APPOINTMENT: "selin",
    ClinicIntent.CANCEL_APPOINTMENT: "selin",
    ClinicIntent.ASK_LOCATION: "selin",
    ClinicIntent.ASK_WORKING_HOURS: "selin",
    ClinicIntent.ASK_PRICE: "arzu",
    ClinicIntent.ASK_INSURANCE: "arzu",
    ClinicIntent.SYMPTOM_TRIAGE: "can",
    ClinicIntent.MEDICAL_EMERGENCY: "can",
    ClinicIntent.UNKNOWN: "can",
}


def list_personas() -> list[ClinicalPersona]:
    return list(PERSONAS.values())


def get_persona(persona_id: str | None) -> ClinicalPersona:
    return PERSONAS.get(persona_id or DEFAULT_PERSONA_ID, PERSONAS[DEFAULT_PERSONA_ID])


def choose_persona(intent: ClinicIntent, requested_persona_id: str | None = None) -> ClinicalPersona:
    if requested_persona_id in PERSONAS:
        return PERSONAS[requested_persona_id]
    return get_persona(PERSONA_BY_INTENT.get(intent, DEFAULT_PERSONA_ID))
