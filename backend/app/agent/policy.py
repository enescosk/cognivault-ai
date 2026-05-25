"""Agent policy guards — kim ne sorabilir, hangi dış servis çağrılır.

Bu modülün amacı kural-tabanlı sınıflandırmayı (classify) ile LLM çağrısını
(llm) ayırırken aralarındaki "izin verilen mi" katmanını tek yerde tutmak:

  - `_is_customer_chat`: oturum sahibi rolü customer mı?
  - `_is_enterprise_context`: workflow_state["mode"] == "enterprise" mi?
  - `_external_outreach_allowed`: customer dışı + enterprise context'te dış
    arama yapılabilir mi? (Diğer durumlarda Google Places vb. kapalı.)
  - `handle_customer_domain_boundary`: customer tıbbi mesaj atarsa,
    LLM hiç çağrılmadan structured reddedici cevap.
"""

from __future__ import annotations

from app.agent.classify import CUSTOMER_MEDICAL_TERMS, ENTERPRISE_APPOINTMENT_TERMS
from app.agent.context import AgentContext
from app.agent.parsing import _normalize_tr, default_reply
from app.models import RoleName
from app.schemas.chat import AgentReply


def _is_customer_chat(context: AgentContext) -> bool:
    return context.user.role.name == RoleName.CUSTOMER


def _is_enterprise_context(context: AgentContext) -> bool:
    state = context.session.workflow_state or {}
    return state.get("mode") == "enterprise"


def _external_outreach_allowed(context: AgentContext) -> bool:
    """Customer'lar dış arama yapamaz; enterprise context'te açılır."""
    return not _is_customer_chat(context) or _is_enterprise_context(context)


def handle_customer_domain_boundary(
    context: AgentContext,
    user_message: str,
    language: str,
) -> AgentReply | None:
    """Customer scope dışı tıbbi/dental sorgu için kibar reddedici yanıt.

    LLM çağrılmadan döner — boş token harcamayız ve yanıt deterministic kalır.
    """
    if not _is_customer_chat(context) or _is_enterprise_context(context):
        return None

    normalized = _normalize_tr(user_message)
    has_medical_term = any(_normalize_tr(term) in normalized for term in CUSTOMER_MEDICAL_TERMS)
    has_enterprise_term = any(_normalize_tr(term) in normalized for term in ENTERPRISE_APPOINTMENT_TERMS)
    if not has_medical_term or has_enterprise_term:
        return None

    first_name = (context.user.full_name or "").split()[0]
    prefix_tr = f"{first_name} Hanım, " if first_name else ""
    prefix_en = f"{first_name}, " if first_name else ""
    return AgentReply(
        message=default_reply(
            language,
            (
                f"{prefix_tr}bu ekran kurumsal destek randevuları için tasarlandı; tıbbi veya dental randevu "
                "yönlendirmesi yapmıyorum. Size Onboarding Desk, Technical Support, Billing Operations veya "
                "Compliance Advisory ekipleri için güvenli bir randevu oluşturmada yardımcı olabilirim."
            ),
            (
                f"{prefix_en}this workspace is for enterprise support appointments, so I cannot route medical or "
                "dental appointment requests here. I can help you book a secure session with Onboarding Desk, "
                "Technical Support, Billing Operations, or Compliance Advisory."
            ),
        ),
        language=language,
        outcome="unsupported_domain",
        metadata_json={"intent": "unsupported_customer_domain", "domain": "medical"},
    )
