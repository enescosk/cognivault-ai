from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.anthropic_runtime import (
    anthropic_enabled,
    build_cached_system,
    convert_history_to_anthropic,
    get_anthropic_runtime,
    stream_anthropic_agent,
    tool_specs_anthropic,
)
from app.ai.runtime import select_llm_runtime
from app.ai.text_understanding import fuzzy_contains, normalize_for_intent
from app.agent.agents import (
    escalation_offer_message,
    should_auto_escalate,
    update_frustration_counter,
)
from app.agent.context import AgentContext
from app.agent.policy import (
    _external_outreach_allowed,
    _is_customer_chat,
    _is_enterprise_context,
    handle_customer_domain_boundary,
)
from app.agent.parsing import (
    _clean_term,
    _normalize_tr,
    default_reply,
    detect_language,
    infer_place_category,
    parse_department,
    parse_phone,
    parse_preferred_date,
    parse_slot_selection,
)
from app.agent.prompts import build_system_prompt
from app.core.config import get_settings
from app.models import AuditResultStatus, ChatSession, MessageSender, User
from app.schemas.chat import AgentReply
from app.schemas.appointment import AppointmentConfirmationCard
from app.services.appointment_service import format_slot_label
from app.services.audit_service import log_action
from app.services.chat_service import add_message, update_workflow_state
from app.schemas.validation import safe_outreach_terms
from app.services.external_intent_service import extract_external_request_terms
from app.services.intelligence_service import discover_company_contact_for_agent
from app.services.llm_usage import extract_openai_usage, record_llm_usage
from app.services.notification_service import send_appointment_confirmation
from app.tools.registry import execute_tool, tool_specs


settings = get_settings()
logger = logging.getLogger(__name__)
MAX_TOOL_ITERATIONS = 6


def _record_openai_usage(context: AgentContext, response, model: str, agent_type: str) -> None:
    """Non-streaming OpenAI completion → usage kaydı. Telemetri başarısızlığı request'i bozmamalı."""
    prompt_t, completion_t = extract_openai_usage(response)
    if prompt_t == 0 and completion_t == 0:
        return
    record_llm_usage(
        context.db,
        model=model,
        prompt_tokens=prompt_t,
        completion_tokens=completion_t,
        agent_type=agent_type,
        organization_id=getattr(context.user, "organization_id", None),
        user_id=context.user.id,
    )


# Sentiment, simple intent classifier ve boundary term'leri `agent/classify.py`
# içine taşındı — orchestrator artık sadece bunları import edip dispatch eder.


# detect_sentiment / classify_simple_intent / make_simple_reply ve ilgili
# kural tabloları `agent/classify.py` içine taşındı. Orchestrator bunları
# import edip dispatch eder (geri uyumluluk için isimler aynı).
from app.agent.classify import (  # noqa: E402
    classify_simple_intent,
    detect_sentiment,
    make_simple_reply,
)


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT COMPRESSION
# Summarises old messages to avoid sending full history to the API.
# Keeps last N messages verbatim + a compressed summary of everything older.
# This halves token cost for long conversations.
# ─────────────────────────────────────────────────────────────────────────────

_VERBATIM_TAIL = 8   # always keep last N messages as-is
_COMPRESS_THRESHOLD = 16  # only compress when history exceeds this


def _compress_history(messages: list) -> list[dict]:
    """
    Returns an OpenAI-style message list.
    If conversation is long, older messages are summarised into a single
    system message to reduce token usage.
    """
    user_assistant = [
        m for m in messages
        if m.sender in (MessageSender.USER, MessageSender.ASSISTANT)
    ]

    if len(user_assistant) <= _COMPRESS_THRESHOLD:
        return [
            {"role": "user" if m.sender == MessageSender.USER else "assistant", "content": m.content}
            for m in user_assistant
        ]

    # Split: older (to summarise) + recent tail (verbatim)
    older  = user_assistant[:-_VERBATIM_TAIL]
    recent = user_assistant[-_VERBATIM_TAIL:]

    summary_lines = []
    for m in older:
        role = "Kullanıcı" if m.sender == MessageSender.USER else "Asistan"
        # Truncate very long messages in the summary
        content = m.content[:200] + "…" if len(m.content) > 200 else m.content
        summary_lines.append(f"{role}: {content}")

    summary_block = {
        "role": "system",
        "content": (
            "[Önceki konuşma özeti — token tasarrufu için sıkıştırıldı]\n"
            + "\n".join(summary_lines)
        ),
    }

    verbatim = [
        {"role": "user" if m.sender == MessageSender.USER else "assistant", "content": m.content}
        for m in recent
    ]

    return [summary_block] + verbatim


def detect_language(text: str, fallback: str = "en") -> str:
    normalized = normalize_for_intent(text)
    turkish_markers = [
        "ş", "ğ", "ı", "ç", "ö", "ü",
        "randevu", "merhaba", "yardim", "bugun", "yarin", "icin",
        "destek", "baglanti", "baglan", "calismiyor", "calismio",
        "cozulmeli", "fatura", "odeme", "ucret", "uyum",
    ]
    return "tr" if any(marker in text.lower() or marker in normalized for marker in turkish_markers) or fallback == "tr" else "en"


def parse_preferred_date(text: str) -> str | None:
    """Türkçe/kısa tarih ifadelerini YYYY-MM-DD'ye çevirir."""
    from datetime import date, timedelta
    today = date.today()
    lower = text.lower()

    if "bugün" in lower or "today" in lower:
        return today.isoformat()
    normalized = normalize_for_intent(text)
    if "bugun" in normalized or "today" in normalized:
        return today.isoformat()
    if "yarın" in lower or "tomorrow" in lower or "yarin" in normalized:
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
        if name in lower or normalize_for_intent(name) in normalized:
            delta = (weekday - today.weekday()) % 7 or 7
            return (today + timedelta(days=delta)).isoformat()
    return None


def parse_phone(text: str) -> str | None:
    match = re.search(r"(\+?\d[\d\s()-]{8,}\d)", text)
    return match.group(1).strip() if match else None


def parse_department(text: str) -> str | None:
    normalized = normalize_for_intent(text)
    candidates = {
        "onboarding desk": ["onboarding", "kurulum", "baslangic", "devreye alma", "kurulum destegi"],
        "technical support": ["technical", "support", "teknik", "destek", "tekink", "destk", "issue", "ariza", "calismiyor", "calismio", "baglanamiyorum"],
        "billing operations": ["billing", "invoice", "payment", "fatura", "ftra", "ftr", "odeme", "ucret", "tahsilat"],
        "compliance advisory": ["compliance", "legal", "uyum", "denetim", "policy", "kvk", "gdpr", "sozlesme"],
    }
    for department, keywords in candidates.items():
        if fuzzy_contains(normalized, keywords, threshold=0.80):
            return department.title()
    return None


_OUTREACH_KEYWORDS = [
    "görüşme",
    "gorusme",
    "arama",
    "ara",
    "telefon",
    "iletişim",
    "iletisim",
    "call",
    "contact",
    "reach",
    "randevu",
    "talep",
    "muayene",
    "doktor",
    "hekim",
    "hastane",
    "danışmanlık",
    "danismanlik",
]

# _PLACE_CATEGORIES, _normalize_tr, infer_place_category, _clean_term parsing.py'a taşındı


def extract_outreach_terms(text: str) -> dict | None:
    structured_terms = extract_external_request_terms(text)
    if structured_terms:
        # Outbound çağrılara gitmeden önce sertleştirme: < > " ' ; ( ) gibi
        # injection karakterleri reddedilir, max uzunluk uygulanır.
        return safe_outreach_terms(structured_terms)

    lower = text.lower()
    if not any(keyword in lower for keyword in _OUTREACH_KEYWORDS):
        return None

    known_companies = [
        (r"\bods(?:\s+consulting(?:\s+group)?)?\b", "ODS Consulting Group"),
        (r"\bmac\s*fit\b|\bmacfit\b", "MACFit"),
        (r"\bak\s*bank\b|\bakbank\b", "Akbank"),
        (r"\bflorence(?:\s+nightingale)?\b", "Ataşehir Florence Nightingale Hastanesi"),
    ]
    company = None
    for pattern, canonical in known_companies:
        if re.search(pattern, text, flags=re.IGNORECASE):
            company = canonical
            break

    location = None
    loc_match = re.search(
        r"\b([a-zçğıöşüİÇĞÖŞÜ]+)(?:'?(?:deki|daki|teki|taki|de|da|te|ta))\b",
        text,
        flags=re.IGNORECASE,
    )
    if loc_match:
        location = _clean_term(loc_match.group(1)).title()
    if not location:
        known_locations = [
            "ataşehir",
            "atasehir",
            "kadıköy",
            "kadikoy",
            "üsküdar",
            "uskudar",
            "ümraniye",
            "umraniye",
            "beşiktaş",
            "besiktas",
            "şişli",
            "sisli",
        ]
        normalized_text = _normalize_tr(text)
        for item in known_locations:
            if _normalize_tr(item) in normalized_text:
                location = item.replace("atasehir", "ataşehir").replace("kadikoy", "kadıköy").replace("umraniye", "ümraniye").title()
                break

    purpose = None
    purpose_for_matches = re.findall(r"([^.?!]{3,120}?)\s+(?:için|icin)\b", text, flags=re.IGNORECASE)
    if purpose_for_matches:
        purpose = _clean_term(purpose_for_matches[-1])
    purpose_match = re.search(
        r"(?:ile|için|icin|ilgili)\s+(.+?)(?:\s+(?:talep\s+ediyorum|istiyorum|ayarla|başlat|baslat)|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not purpose and purpose_match:
        purpose = _clean_term(purpose_match.group(1))
    if not purpose:
        purpose_match = re.search(r"((?:kredi|ihracat|müşteri|musteri|kayıt|kayit).{0,80})", text, flags=re.IGNORECASE)
        if purpose_match:
            purpose = _clean_term(purpose_match.group(1))

    category = infer_place_category(text)

    if category and "muayene" in lower:
        purpose = f"{category} muayenesi"

    if not company and not category:
        match = re.search(r"(.+?)\s+ile\s+.+?(?:görüşme|gorusme|arama|iletişim|iletisim)", text, flags=re.IGNORECASE)
        if match:
            candidate = _clean_term(match.group(1))
            if 2 <= len(candidate) <= 120:
                company = candidate

    if category and (not purpose or purpose in {"ilgili görüşme", "görüşme", "gorusme"}):
        purpose = f"{category} görüşmesi"

    if not company and category:
        company = category

    if not company:
        return None
    raw = {
        "company": company,
        "category": category,
        "location": location,
        "purpose": purpose or "görüşme talebi",
    }
    # Çıktıyı sertleştir — injection karakterleri reddedilirse None döner.
    sanitized = safe_outreach_terms(raw)
    if sanitized is None:
        return None
    sanitized["category"] = category   # category outreach validation'da yer almıyor, koru
    sanitized["search_query"] = f"{sanitized.get('company','')} {sanitized.get('location') or ''}".strip()
    return sanitized


def parse_company_outreach_request(text: str) -> str | None:
    terms = extract_outreach_terms(text)
    return terms["search_query"] if terms else None


def _outreach_activity_payload(job, terms: dict) -> dict:
    lead = job.leads[0] if job.leads else None
    contacts = lead.contact_points if lead else []
    phone = next((item for item in contacts if item.kind.value == "phone"), None)
    email = next((item for item in contacts if item.kind.value == "email"), None)
    provenance = lead.provenance if lead else {}
    source_label = {
        "website": "approved public website catalog",
        "google_places": "Google Places",
    }.get(lead.source_kind.value if lead else "", "public source")
    return {
        "type": "external_outreach",
        "job_id": job.id,
        "company": lead.organization_name if lead else job.query,
        "address": lead.location if lead else None,
        "phone": phone.value if phone else None,
        "email": email.value if email else None,
        "source_url": lead.source_url if lead else None,
        "source_kind": lead.source_kind.value if lead else None,
        "source_label": source_label,
        "confidence": lead.confidence if lead else 0,
        "status": "call_prepared" if phone else "contact_not_found",
        "failure_reason": provenance.get("mode") if not phone else None,
        "extracted_terms": terms,
        "events": [
            {"label": f"{'Firma' if terms.get('entity_type') == 'company' else 'İhtiyaç'} algılandı: {terms['company']}", "status": "completed"},
            {"label": f"Lokasyon/amaç çıkarıldı: {terms.get('location') or 'genel'} · {terms.get('purpose')}", "status": "completed"},
            {"label": f"{source_label} ile iletişim bilgisi arandı", "status": "completed"},
            {
                "label": "Telefon bulundu" if phone else "Telefon bulunamadı",
                "status": "completed" if phone else "blocked",
            },
            {
                "label": "Arama hazırlığı başlatıldı" if phone else "Operatör incelemesi gerekiyor",
                "status": "in_progress" if phone else "pending",
            },
        ],
    }


def handle_company_outreach_request(context: AgentContext, user_message: str, language: str) -> AgentReply | None:
    terms = extract_outreach_terms(user_message)
    if not terms:
        return None
    job = discover_company_contact_for_agent(
        context.db,
        current_user=context.user,
        query=terms["search_query"],
        target_location=terms.get("location") or "Türkiye",
    )
    activity = _outreach_activity_payload(job, terms)
    if activity.get("phone"):
        entity_label = "firma" if terms.get("entity_type") == "company" else "ihtiyaç"
        message = default_reply(
            language,
            (
                f"{activity['company']} için public kaynaklarda iletişim bilgisini buldum.\n"
                f"Çıkardığım terimler: {entity_label}={terms['company']}, lokasyon={terms.get('location') or 'genel'}, amaç={terms.get('purpose')}.\n"
                f"Kaynak: {activity.get('source_label')}.\n"
                f"Adres: {activity['address']}\n"
                f"Telefon: {activity['phone']}\n\n"
                f"{terms.get('purpose')} için arama hazırlığına geçiyorum. "
                "Şimdilik bu aşama simülasyon modunda; gerçek arama için operatör onayı gerekecek."
            ),
            (
                f"I found public contact details for {activity['company']}.\n"
                f"Extracted terms: entity={terms['company']}, location={terms.get('location') or 'general'}, purpose={terms.get('purpose')}.\n"
                f"Source: {activity.get('source_label')}.\n"
                f"Address: {activity['address']}\n"
                f"Phone: {activity['phone']}\n\n"
                f"I am preparing the call for {terms.get('purpose')}. "
                "For now this is simulated; a real call will require operator approval."
            ),
        )
        outcome = "external_contact_prepared"
    else:
        entity_label = "firma" if terms.get("entity_type") == "company" else "ihtiyaç"
        reason = activity.get("failure_reason")
        setup_hint = ""
        if reason == "google_places_not_configured":
            setup_hint = " Google Places canlı araması için GOOGLE_PLACES_API_KEY yapılandırılmalı."
        elif reason == "external_intelligence_disabled":
            setup_hint = " Google Places canlı araması için INTELLIGENCE_EXTERNAL_ENABLED=true yapılmalı."
        message = default_reply(
            language,
            (
                f"{terms['company']} için güvenilir public telefon bilgisi bulamadım. "
                f"Çıkardığım terimler: {entity_label}={terms['company']}, lokasyon={terms.get('location') or 'genel'}, amaç={terms.get('purpose')}. "
                f"Aranan kaynak: {activity.get('source_label')}.{setup_hint} "
                "Operatör incelemesine alıyorum."
            ),
            f"I could not find a reliable public phone number for {terms['company']}. I am routing it for operator review.",
        )
        outcome = "external_contact_needs_review"
    return AgentReply(
        message=message,
        language=language,
        outcome=outcome,
        metadata_json={"intelligence_activity": activity},
    )


# parse_slot_selection ve default_reply parsing.py'a taşındı


def _dispatch_appointment_confirmation_once(
    context: AgentContext,
    result: dict,
    language: str,
) -> None:
    confirmation_code = str(result.get("confirmation_code") or "")
    if not confirmation_code:
        return

    state = dict(context.session.workflow_state or {})
    sent = set(state.get("sent_notification_keys") or [])
    idempotency_key = f"appointment_confirmation:{confirmation_code}:{context.user.id}"
    if idempotency_key in sent:
        return

    delivered = send_appointment_confirmation(
        to_email=context.user.email,
        full_name=context.user.full_name,
        confirmation_code=confirmation_code,
        department=result["department"],
        scheduled_at=str(result["scheduled_at"]),
        location=result["location"],
        contact_phone=result["contact_phone"],
        purpose=result.get("purpose", ""),
        language=language,
    )
    sent.add(idempotency_key)
    state["sent_notification_keys"] = sorted(sent)
    update_workflow_state(context.db, context.session, state)
    log_action(
        context.db,
        user_id=context.user.id,
        session_id=context.session.id,
        action_type="notification.appointment_confirmation",
        explanation="Appointment confirmation notification dispatched",
        result_status=AuditResultStatus.SUCCESS if delivered else AuditResultStatus.FAILURE,
        success=delivered,
        details={"confirmation_code": confirmation_code, "idempotency_key": idempotency_key},
    )


def openai_enabled() -> bool:
    return select_llm_runtime() is not None


def run_openai_agent(context: AgentContext, user_message: str, language: str) -> AgentReply:
    runtime = select_llm_runtime()
    if runtime is None:
        raise HTTPException(status_code=503, detail="No OpenAI-compatible LLM runtime is configured")
    client = runtime.client

    # Kullanıcı bağlamını sistem promptuna ekle.
    # user_phone: AI'ın "kayıtlı numaraya onay göndereyim mi?" akışını tetikler.
    # Boşsa AI telefon sorar ve save_user_phone ile profil güncellenir.
    user_phone_display = context.user.phone or ""
    ctx_block = (
        f"[Oturum bağlamı] "
        f"Kullanıcı: {context.user.full_name} | "
        f"Rol: {context.user.role.name.value} | "
        f"Dil: {context.user.locale} | "
        f"user_phone: {user_phone_display} | "
        f"Workflow: {json.dumps(context.session.workflow_state or {}, ensure_ascii=False)}"
    )
    history: list[dict] = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "system", "content": ctx_block},
    ]

    # R-3: session.messages already contains the current user_message (saved
    # before the agent is called). Using [-13:-1] keeps up to 12 *previous*
    # turns and excludes the current message so we don't duplicate it below.
    for item in context.session.messages[-13:-1]:
        if item.sender == MessageSender.USER:
            history.append({"role": "user", "content": item.content})
        elif item.sender == MessageSender.ASSISTANT:
            history.append({"role": "assistant", "content": item.content})
        # system ve tool mesajları zaten context bloğunda var, atla

    history.append({"role": "user", "content": user_message})

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.chat.completions.create(
            model=runtime.model,
            messages=history,
            tools=tool_specs(),
            tool_choice="auto",
            temperature=0.65,
        )
        _record_openai_usage(context, response, settings.openai_model, "appointment")
        message = response.choices[0].message
        if message.tool_calls:
            history.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in message.tool_calls
                    ],
                }
            )
            confirmation_card: AppointmentConfirmationCard | None = None
            for tool_call in message.tool_calls:
                result = execute_tool(
                    context.db,
                    name=tool_call.function.name,
                    arguments=tool_call.function.arguments,
                    current_user=context.user,
                    session=context.session,
                )
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str),
                    }
                )

                # Slot listesi geldi → workflow_state'e kaydet (bir sonraki turda "3" seçimi çalışsın)
                if tool_call.function.name == "check_available_slots":
                    state = dict(context.session.workflow_state or {})
                    state["suggested_slots"] = result.get("slots", [])
                    update_workflow_state(context.db, context.session, state)

                # Randevu oluşturuldu → kart hazırla + bildirim gönder
                if tool_call.function.name == "create_appointment":
                    scheduled_at_val = result["scheduled_at"]
                    confirmation_card = AppointmentConfirmationCard(
                        confirmation_code=result["confirmation_code"],
                        department=result["department"],
                        scheduled_at=scheduled_at_val,
                        location=result["location"],
                        contact_phone=result["contact_phone"],
                        status=result["status"],
                    )
                    _dispatch_appointment_confirmation_once(context, result, language)

            # Randevu oluşturulduysa AI'ın güzel onay mesajı yazmasına izin ver
            if confirmation_card:
                final = client.chat.completions.create(
                    model=runtime.model,
                    messages=history,
                    temperature=0.65,
                )
                _record_openai_usage(context, final, settings.openai_model, "appointment")
                final_text = final.choices[0].message.content or default_reply(
                    language,
                    f"Randevunuz onaylandı! Kod: {confirmation_card.confirmation_code}",
                    f"Your appointment is confirmed! Code: {confirmation_card.confirmation_code}",
                )
                return AgentReply(
                    message=final_text,
                    language=language,
                    outcome="completed",
                    confirmation_card=confirmation_card,
                )
            continue

        return AgentReply(message=message.content or "", language=language, outcome="needs_input")

    raise HTTPException(status_code=502, detail="The AI agent could not complete the request")


# ─────────────────────────────────────────────────────────────────────────────
# STREAMING ENGINE
# ─────────────────────────────────────────────────────────────────────────────
#
# Mimari:
#   Faz 1 — Tool Loop   (non-streaming, hızlı JSON turları)
#     OpenAI-compatible runtime'a "tool_choice=auto" ile sor.
#     Tool call gelirse çalıştır, history'e ekle, tekrar sor.
#     Bu turlar text üretmez, sadece araç çağırır → ortalama <300ms/tur.
#
#   Faz 2 — Stream      (streaming, "tool_choice=none")
#     Tüm tool'lar tamamlandı, artık sadece metin üretiliyor.
#     "tool_choice=none" ile runtime'ı kilitleyip gerçek SSE stream'i başlat.
#     Her token chunk → SSE event → frontend'de anlık görünür.
#
# Yield formatı (JSON satır başına):
#   {"t": "tk", "v": "<token>"}          — metin parçası
#   {"t": "done", "card": <dict|null>}   — akış bitti, kart varsa gönder
#   {"t": "err",  "v": "<mesaj>"}        — hata
#
# Frontend bu stream'i okur, "tk" eventleri bir buffer'a ekler,
# "done" gelince session'ı yeniler ve kartı gösterir.
# ─────────────────────────────────────────────────────────────────────────────

def _build_history(context: AgentContext, user_message: str) -> list[dict]:
    """
    Ortak history builder — hem streaming hem normal agent kullanır.
    Context compression ile uzun konuşmalarda token tasarrufu sağlar.
    """
    user_phone_display = context.user.phone or ""
    sentiment = detect_sentiment(user_message)
    ctx_block = (
        f"[Oturum bağlamı] "
        f"Kullanıcı: {context.user.full_name} | "
        f"Rol: {context.user.role.name.value} | "
        f"Dil: {context.user.locale} | "
        f"user_phone: {user_phone_display} | "
        f"Duygu: {sentiment} | "
        f"Workflow: {json.dumps(context.session.workflow_state or {}, ensure_ascii=False)}"
    )
    history: list[dict] = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "system", "content": ctx_block},
    ]
    # R-3: session.messages already contains the current user_message (saved
    # before the agent is called). Pass [:-1] to _compress_history so the
    # current message is not included in the compressed block; we append it
    # explicitly below to avoid a duplicate in the LLM history.
    history.extend(_compress_history(context.session.messages[:-1]))
    history.append({"role": "user", "content": user_message})
    return history


def _execute_tool_calls(
    context: AgentContext,
    message,
    history: list[dict],
) -> tuple[list[dict], AppointmentConfirmationCard | None]:
    """
    Tool call'ları çalıştırır, history'e ekler.
    Döner: (güncellenmiş history, confirmation_card | None)
    Bu fonksiyon hem streaming hem normal agent tarafından kullanılır.
    """
    history.append({
        "role": "assistant",
        "content": message.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in message.tool_calls
        ],
    })

    confirmation_card: AppointmentConfirmationCard | None = None

    for tc in message.tool_calls:
        result = execute_tool(
            context.db,
            name=tc.function.name,
            arguments=tc.function.arguments,
            current_user=context.user,
            session=context.session,
        )
        history.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": json.dumps(result, default=str),
        })

        if tc.function.name == "check_available_slots":
            state = dict(context.session.workflow_state or {})
            state["suggested_slots"] = result.get("slots", [])
            update_workflow_state(context.db, context.session, state)

        if tc.function.name == "create_appointment":
            scheduled_at_val = result["scheduled_at"]
            confirmation_card = AppointmentConfirmationCard(
                confirmation_code=result["confirmation_code"],
                department=result["department"],
                scheduled_at=scheduled_at_val,
                location=result["location"],
                contact_phone=result["contact_phone"],
                status=result["status"],
            )
            _dispatch_appointment_confirmation_once(context, result, context.user.locale)

    return history, confirmation_card


def stream_openai_agent(
    context: AgentContext,
    user_message: str,
    language: str,
) -> Generator[str, None, None]:
    """
    SSE generator — her yield bir "data: ...\n\n" satırıdır.

    Faz 1: Tool loop (non-streaming) — araçları çalıştır.
    Faz 2: Son yanıt streaming — token token gönder.

    Bu ikili mimari sayesinde:
    - Tool execution hızlı kalır (streaming overhead yok)
    - Kullanıcı metin üretimini gerçek zamanlı görür
    - Tool call'dan sonraki onay mesajı da akarak gelir
    """
    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    # Sentiment escalation check (mirrors process_message logic for streaming path)
    current_state = dict(context.session.workflow_state or {})
    current_state = update_frustration_counter(current_state, detect_sentiment(user_message))
    update_workflow_state(context.db, context.session, current_state)
    if should_auto_escalate(current_state, detect_sentiment(user_message)):
        offer = escalation_offer_message(language)
        current_state["consecutive_frustrated_turns"] = 0
        update_workflow_state(context.db, context.session, current_state)
        for word in re.findall(r"\S+\s*", offer):
            yield _sse({"t": "tk", "v": word})
        add_message(
            context.db, session=context.session, sender=MessageSender.ASSISTANT,
            content=offer, language=language,
            metadata_json={"tier": "escalation_stream"},
        )
        yield _sse({"t": "done", "card": None})
        return

    outreach_reply = handle_company_outreach_request(context, user_message, language)
    if outreach_reply:
        full_text = outreach_reply.message
        words = re.findall(r"\S+\s*", full_text)
        for word in words:
            yield _sse({"t": "tk", "v": word})
        add_message(
            context.db,
            session=context.session,
            sender=MessageSender.ASSISTANT,
            content=full_text,
            language=language,
            metadata_json=outreach_reply.metadata_json or {},
        )
        yield _sse({"t": "done", "card": None})
        return

    # Try Anthropic streaming when preferred/auto and key is configured
    settings = get_settings()
    preferred = settings.preferred_agent_provider.strip().lower()
    anthropic_rt = get_anthropic_runtime() if anthropic_enabled() and preferred in {"auto", "anthropic"} else None
    if anthropic_rt is not None:
        user_phone_display = context.user.phone or ""
        ctx_block = (
            f"[Session context] User: {context.user.full_name} | "
            f"Role: {context.user.role.name.value} | Locale: {context.user.locale} | "
            f"phone: {user_phone_display} | "
            f"Workflow: {json.dumps(context.session.workflow_state or {}, ensure_ascii=False)}"
        )
        system_blocks = build_cached_system(build_system_prompt(), ctx_block)
        oai_history = _build_history(context, user_message)
        anthropic_messages = convert_history_to_anthropic(oai_history)
        if not anthropic_messages or anthropic_messages[-1]["role"] != "user":
            anthropic_messages.append({"role": "user", "content": user_message})

        def _exec_tool_for_anthropic(*, name: str, arguments: str):
            result = execute_tool(
                context.db, name=name, arguments=arguments,
                current_user=context.user, session=context.session,
            )
            card = None
            if name == "create_appointment":
                card = AppointmentConfirmationCard(
                    confirmation_code=result["confirmation_code"],
                    department=result["department"],
                    scheduled_at=result["scheduled_at"],
                    location=result["location"],
                    contact_phone=result["contact_phone"],
                    status=result["status"],
                )
                _dispatch_appointment_confirmation_once(context, result, language)
            if name == "check_available_slots":
                state = dict(context.session.workflow_state or {})
                state["suggested_slots"] = result.get("slots", [])
                update_workflow_state(context.db, context.session, state)
            return result, card

        full_text = ""
        confirmation_card = None
        for chunk in stream_anthropic_agent(
            runtime=anthropic_rt,
            system_blocks=system_blocks,
            messages=anthropic_messages,
            tools=tool_specs_anthropic(),
            execute_tool_fn=_exec_tool_for_anthropic,
        ):
            # Forward all SSE chunks except the done sentinel (we rewrite it below)
            if '"t": "done"' in chunk or '"t":"done"' in chunk:
                import json as _json
                try:
                    payload = _json.loads(chunk.removeprefix("data: ").strip())
                    full_text = payload.get("_full_text", full_text)
                    card_meta = payload.get("card") or {}
                    if card_meta and not confirmation_card:
                        pass  # card already built in execute_tool_fn
                except Exception:
                    pass
                break
            yield chunk
            # Extract streamed text for DB save
            if '"t": "tk"' in chunk or '"t":"tk"' in chunk:
                try:
                    import json as _json
                    token_payload = _json.loads(chunk.removeprefix("data: ").strip())
                    full_text += token_payload.get("v", "")
                except Exception:
                    pass

        card_meta = confirmation_card.model_dump(mode="json") if confirmation_card else {}
        add_message(
            context.db, session=context.session, sender=MessageSender.ASSISTANT,
            content=full_text, language=language, metadata_json=card_meta,
        )
        yield _sse({"t": "done", "card": card_meta or None})
        return

    runtime = select_llm_runtime()
    if runtime is None:
        fallback_reply = run_fallback_agent(context, user_message, language)
        words = re.findall(r"\S+\s*", fallback_reply.message)
        for word in words:
            yield _sse({"t": "tk", "v": word})
        card_meta = fallback_reply.confirmation_card.model_dump(mode="json") if fallback_reply.confirmation_card else {}
        add_message(
            context.db,
            session=context.session,
            sender=MessageSender.ASSISTANT,
            content=fallback_reply.message,
            language=fallback_reply.language,
            metadata_json={**(fallback_reply.metadata_json or {}), **card_meta, "tier": "local_guided_stream"},
        )
        yield _sse({"t": "done", "card": card_meta if fallback_reply.confirmation_card else None})
        return
    client = runtime.client
    history = _build_history(context, user_message)
    confirmation_card: AppointmentConfirmationCard | None = None

    # ── Faz 1: Tool Loop ─────────────────────────────────────────────────────
    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.chat.completions.create(
            model=runtime.model,
            messages=history,
            tools=tool_specs(),
            tool_choice="auto",
            temperature=0.65,
        )
        _record_openai_usage(context, response, settings.openai_model, "appointment")
        message = response.choices[0].message

        if not message.tool_calls:
            # Tool call yok → Faz 2'ye geç (bu history ile stream aç)
            break

        # Signal tool starts to frontend so user sees progress, not silence
        for tc in message.tool_calls:
            yield _sse({"t": "tool_start", "name": tc.function.name})

        # Tool call var → çalıştır, history'e ekle, döngüye devam et
        history, card = _execute_tool_calls(context, message, history)

        for tc in message.tool_calls:
            yield _sse({"t": "tool", "name": tc.function.name, "status": "done"})

        if card:
            confirmation_card = card
        # Tool sonuçları history'de, bir sonraki turda AI yanıt üretecek
    else:
        logger.warning(
            "stream_tool_loop_exhausted",
            extra={"session_id": context.session.id, "user_id": context.user.id},
        )
        log_action(
            context.db,
            user_id=context.user.id,
            session_id=context.session.id,
            action_type="agent.tool_loop_exhausted",
            explanation="Tool loop exceeded maximum iterations before final streaming response",
            result_status=AuditResultStatus.FAILURE,
            success=False,
            details={"max_iterations": MAX_TOOL_ITERATIONS},
        )
        yield _sse({
            "t": "err",
            "code": "tool_loop_exhausted",
            "v": default_reply(
                language,
                "İşlemi güvenli şekilde tamamlayamadım. Lütfen talebi biraz daha net yazarak tekrar deneyin.",
                "I could not safely complete the workflow. Please rephrase the request and try again.",
            ),
        })
        return

    # ── Faz 2: Streaming Final Response ──────────────────────────────────────
    # tool_choice="none" → runtime artık yeni tool call açamaz, sadece metin yazar.
    # stream=True → her token chunk anında yield edilir.
    try:
        stream = client.chat.completions.create(
            model=runtime.model,
            messages=history,
            tools=tool_specs(),
            stream=True,
            stream_options={"include_usage": True},  # son chunk usage taşır
            tool_choice="none",   # Faz 2'de tool call istemiyoruz
            temperature=0.65,
        )

        full_text = ""
        final_usage = None
        for chunk in stream:
            # Final usage chunk'unda choices=[] olabilir
            if getattr(chunk, "usage", None) is not None:
                final_usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            token = delta.content or ""
            if token:
                full_text += token
                yield _sse({"t": "tk", "v": token})

        # Stream bitti — usage'ı kaydet
        if final_usage is not None:
            record_llm_usage(
                context.db,
                model=settings.openai_model,
                prompt_tokens=int(getattr(final_usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(final_usage, "completion_tokens", 0) or 0),
                agent_type="appointment",
                organization_id=getattr(context.user, "organization_id", None),
                user_id=context.user.id,
            )

        # Stream bitti — mesajı DB'ye kaydet
        card_meta = confirmation_card.model_dump(mode="json") if confirmation_card else {}
        add_message(
            context.db,
            session=context.session,
            sender=MessageSender.ASSISTANT,
            content=full_text,
            language=language,
            metadata_json=card_meta,
        )

        # Done event: kart varsa frontend confirmation card gösterir
        yield _sse({
            "t": "done",
            "card": card_meta if confirmation_card else None,
        })

    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "stream_final_response_failed",
            extra={"session_id": context.session.id, "user_id": context.user.id},
        )
        log_action(
            context.db,
            user_id=context.user.id,
            session_id=context.session.id,
            action_type="agent.stream_failed",
            explanation="Final streaming response failed",
            result_status=AuditResultStatus.FAILURE,
            success=False,
            details={"error": str(exc)},
        )
        yield _sse({"t": "err", "code": "stream_failed", "v": str(exc)})


def run_fallback_agent(context: AgentContext, user_message: str, language: str) -> AgentReply:
    state = dict(context.session.workflow_state or {})
    active = state.get("intent")
    message_lower = user_message.lower()

    if any(keyword in message_lower for keyword in ["application", "başvuru", "form"]):
        return AgentReply(
            message=default_reply(
                language,
                "Bu MVP şu anda yalnızca randevu oluşturma akışını destekliyor. Başvuru akışı sonraki sürüm için hazırlandı ama henüz etkin değil.",
                "This MVP currently supports appointment booking only. The application flow is structured for a later release but is not enabled yet.",
            ),
            language=language,
            outcome="refused",
        )

    if not active and not any(
        keyword in message_lower
        for keyword in ["appointment", "book", "schedule", "meeting", "randevu", "rezervasyon", "görüşme"]
    ):
        return AgentReply(
            message=default_reply(
                language,
                "Size randevu oluşturma sürecinde yardımcı olabilirim. İsterseniz uygun bir ekip seçip adım adım ilerleyelim.",
                "I can help you book an appointment. If you want, we can pick the right team and complete the workflow step by step.",
            ),
            language=language,
            outcome="refused",
        )

    state.setdefault("intent", "appointment_booking")
    state.setdefault("language", language)
    state.setdefault("collected", {})
    collected = dict(state.get("collected") or {})
    state["collected"] = collected

    if not state.get("profile_snapshot"):
        state["profile_snapshot"] = execute_tool(
            context.db,
            name="fetch_user_profile",
            arguments=json.dumps({}),
            current_user=context.user,
            session=context.session,
        )
        update_workflow_state(context.db, context.session, state)

    department = parse_department(user_message)
    phone = parse_phone(user_message)
    preferred_date = parse_preferred_date(user_message)
    if department and not collected.get("department"):
        collected["department"] = department
    if phone and not collected.get("contact_phone"):
        collected["contact_phone"] = phone
    if preferred_date and not collected.get("preferred_date"):
        collected["preferred_date"] = preferred_date

    if state.get("stage") == "awaiting_slot_selection" and state.get("suggested_slots"):
        selected_slot = parse_slot_selection(user_message, state["suggested_slots"])
        if selected_slot:
            permission = execute_tool(
                context.db,
                name="validate_user_role",
                arguments=json.dumps(
                    {
                        "required_role": "customer_self_or_operator",
                        "action": "create_appointment",
                        "target_user_id": context.user.id,
                    }
                ),
                current_user=context.user,
                session=context.session,
            )
            if not permission["allowed"]:
                return AgentReply(
                    message=default_reply(
                        language,
                        "Bu işlem için yetkiniz bulunmuyor.",
                        "You are not authorized to complete this action.",
                    ),
                    language=language,
                    outcome="refused",
                )
            tool_result = execute_tool(
                context.db,
                name="create_appointment",
                arguments=json.dumps(
                    {
                        "slot_id": selected_slot["id"],
                        "purpose": collected["purpose"],
                        "contact_phone": collected["contact_phone"],
                        "notes": collected.get("notes"),
                        "language": language,
                        "target_user_id": context.user.id,
                    }
                ),
                current_user=context.user,
                session=context.session,
            )
            state["stage"] = "completed"
            state["selected_slot"] = selected_slot
            update_workflow_state(context.db, context.session, state)

            # Telefon profilden gelmemişse (yani yeni alındıysa) kaydet
            if collected.get("contact_phone") and not context.user.phone:
                from app.services.user_service import update_user_phone
                update_user_phone(context.db, context.user, collected["contact_phone"])

            card = AppointmentConfirmationCard(
                confirmation_code=tool_result["confirmation_code"],
                department=tool_result["department"],
                scheduled_at=tool_result["scheduled_at"],
                location=tool_result["location"],
                contact_phone=tool_result["contact_phone"],
                status=tool_result["status"],
            )
            return AgentReply(
                message=default_reply(
                    language,
                    f"Randevunuz onaylandı. Kodunuz {tool_result['confirmation_code']}. {tool_result['department']} için {selected_slot['start_time'][:16].replace('T', ' ')} saatinde görüşmeniz planlandı.",
                    f"Your appointment is confirmed. Your code is {tool_result['confirmation_code']}. You are booked with {tool_result['department']} at {selected_slot['start_time'][:16].replace('T', ' ')}.",
                ),
                language=language,
                outcome="completed",
                confirmation_card=card,
            )
        return AgentReply(
            message=default_reply(
                language,
                "Size sunduğum slotlardan birini seçmek için 1, 2 veya 3 yazabilirsiniz.",
                "Please choose one of the proposed slots by replying with 1, 2, or 3.",
            ),
            language=language,
            outcome="needs_input",
        )

    if not collected.get("department"):
        state["stage"] = "collect_department"
        update_workflow_state(context.db, context.session, state)
        return AgentReply(
            message=default_reply(
                language,
                "Memnuniyetle yardımcı olayım. Hangi ekiple randevu almak istiyorsunuz: Onboarding Desk, Technical Support, Billing Operations veya Compliance Advisory?",
                "Happy to help. Which team do you need an appointment with: Onboarding Desk, Technical Support, Billing Operations, or Compliance Advisory?",
            ),
            language=language,
            outcome="needs_input",
        )

    if not collected.get("purpose"):
        if len(user_message.strip()) > 18 and department is None:
            collected["purpose"] = user_message.strip()
        else:
            state["stage"] = "collect_purpose"
            update_workflow_state(context.db, context.session, state)
            return AgentReply(
                message=default_reply(
                    language,
                    "Kısa bir amaç bilgisi paylaşır mısınız? Örneğin hangi konu için görüşme talep ediyorsunuz?",
                    "Please share a short purpose for the appointment. What do you need help with?",
                ),
                language=language,
                outcome="needs_input",
            )

    if not collected.get("contact_phone"):
        # Telefon akışı:
        # - Profilde kayıtlı numara varsa → onay iste, yeni numara isteğini karşıla
        # - Profilde yoksa → sor ve kaydet
        saved_phone = context.user.phone
        if saved_phone and not state.get("phone_confirmation_asked"):
            # İlk kez soruyoruz — onay isteği gönder
            state["phone_confirmation_asked"] = True
            update_workflow_state(context.db, context.session, state)
            msg = (
                f"📱 Kayıtlı numaran **{saved_phone}**. Onay kodunu bu numaraya göndereyim mi, yoksa farklı bir numara mı kullanmak istersin?"
                if language == "tr" else
                f"📱 Your saved number is **{saved_phone}**. Should I use this for confirmation, or would you prefer a different one?"
            )
            return AgentReply(message=msg, language=language, outcome="needs_input")

        if saved_phone and state.get("phone_confirmation_asked"):
            # Kullanıcı onayladı mı yoksa yeni numara mı verdi?
            new_phone = parse_phone(user_message)
            confirm_words = ["evet", "olur", "tamam", "ok", "yes", "sure", "kullan", "gönder", "aynı"]
            if any(w in user_message.lower() for w in confirm_words) and not new_phone:
                # Onayladı → kayıtlı telefonu kullan
                collected["contact_phone"] = saved_phone
            elif new_phone:
                # Yeni numara verdi → kaydet
                from app.services.user_service import update_user_phone
                update_user_phone(context.db, context.user, new_phone)
                collected["contact_phone"] = new_phone
            else:
                # Belirsiz yanıt — tekrar sor
                msg = (
                    f"Kayıtlı numaranı (**{saved_phone}**) kullanmamı ister misin, yoksa yeni bir numara mı yazayım?"
                    if language == "tr" else
                    f"Should I use your saved number (**{saved_phone}**) or would you like to enter a new one?"
                )
                return AgentReply(message=msg, language=language, outcome="needs_input")

        if not collected.get("contact_phone"):
            state["stage"] = "collect_phone"
            update_workflow_state(context.db, context.session, state)
            return AgentReply(
                message=default_reply(
                    language,
                    "Randevu teyidi için bir telefon numarası paylaşır mısın?",
                    "Please share a phone number we can use for appointment confirmation.",
                ),
                language=language,
                outcome="needs_input",
            )

    slot_result = execute_tool(
        context.db,
        name="check_available_slots",
        arguments=json.dumps({
            "department": collected["department"],
            "preferred_date": collected.get("preferred_date"),
            "limit": 3,
        }),
        current_user=context.user,
        session=context.session,
    )
    slots = slot_result["slots"]
    if not slots:
        return AgentReply(
            message=default_reply(
                language,
                "Bu ekip için uygun slot bulamadım. İsterseniz başka bir ekip seçelim.",
                "I could not find available slots for that team. We can try a different department if you want.",
            ),
            language=language,
            outcome="needs_input",
        )

    state["stage"] = "awaiting_slot_selection"
    state["suggested_slots"] = slots
    update_workflow_state(context.db, context.session, state)
    slot_lines = []
    for index, slot in enumerate(slots, start=1):
        dt = datetime.fromisoformat(slot["start_time"])
        slot_lines.append(f"{index}. {dt.strftime('%Y-%m-%d %H:%M')} | {slot['location']}")
    prompt = default_reply(
        language,
        "Uygun slotları buldum. Lütfen birini seçin:\n" + "\n".join(slot_lines),
        "I found available slots. Please choose one:\n" + "\n".join(slot_lines),
    )
    return AgentReply(message=prompt, language=language, outcome="needs_input")


def process_message(context: AgentContext, user_message: str) -> AgentReply:
    """
    Main entry point. Routing strategy (cheapest-first):

    1. Simple intent? → canned reply, zero API cost.
    2. Frustrated 2+ turns? → escalation offer, zero API cost.
    3. Outreach request? → intelligence service, no LLM needed.
    4. Anthropic enabled (preferred_agent_provider=auto|anthropic)? → Anthropic agent.
    5. OpenAI-compatible LLM enabled? → OpenAI agent with tool calling.
    6. Fallback → local rule-based engine (works without any API key).
    """
    language  = detect_language(user_message, context.user.locale)
    sentiment = detect_sentiment(user_message)

    # ── Tier 0: müşteri sohbeti domain sınırı (KVKK + scope kilidi) ──────────
    # Selamlama/canned tier'ından ÖNCE çalışır; "Merhaba, diş ağrım var" gibi
    # mesajlar greeting'e düşmeden scope-dışı reddiyle döner.
    boundary_reply = handle_customer_domain_boundary(context, user_message, language)
    if boundary_reply:
        add_message(
            context.db,
            session=context.session,
            sender=MessageSender.ASSISTANT,
            content=boundary_reply.message,
            language=boundary_reply.language,
            metadata_json=boundary_reply.metadata_json or {},
        )
        return boundary_reply

    # Track frustrated turns for auto-escalation
    current_state = dict(context.session.workflow_state or {})
    current_state = update_frustration_counter(current_state, sentiment)
    update_workflow_state(context.db, context.session, current_state)

    # ── Tier 1: zero-cost canned replies ──────────────────────────────────────
    simple_intent = classify_simple_intent(user_message)
    if simple_intent and simple_intent != "affirmative":
        canned = make_simple_reply(simple_intent, language, sentiment, context.user.full_name)
        if canned:
            add_message(
                context.db,
                session=context.session,
                sender=MessageSender.ASSISTANT,
                content=canned,
                language=language,
                metadata_json={"intent": simple_intent, "sentiment": sentiment, "tier": "canned"},
            )
            return AgentReply(message=canned, language=language, outcome="smalltalk")

    # ── Tier 1b: sentiment escalation offer ───────────────────────────────────
    if should_auto_escalate(current_state, sentiment):
        offer = escalation_offer_message(language)
        # Reset counter so we don't spam the offer every turn
        current_state["consecutive_frustrated_turns"] = 0
        update_workflow_state(context.db, context.session, current_state)
        add_message(
            context.db,
            session=context.session,
            sender=MessageSender.ASSISTANT,
            content=offer,
            language=language,
            metadata_json={"intent": "auto_escalation_offer", "sentiment": sentiment, "tier": "escalation"},
        )
        return AgentReply(message=offer, language=language, outcome="escalation_offered")

    # ── Tier 2: outreach / intelligence ──────────────────────────────────────
    outreach_reply = handle_company_outreach_request(context, user_message, language) if _external_outreach_allowed(context) else None
    if outreach_reply:
        add_message(
            context.db,
            session=context.session,
            sender=MessageSender.ASSISTANT,
            content=outreach_reply.message,
            language=outreach_reply.language,
            metadata_json=outreach_reply.metadata_json or {},
        )
        return outreach_reply

    # ── Tier 3: LLM agent (Anthropic preferred, OpenAI fallback) ─────────────
    settings = get_settings()
    preferred = settings.preferred_agent_provider.strip().lower()

    # Try Anthropic first when preferred or auto with key present
    anthropic_runtime = get_anthropic_runtime() if anthropic_enabled() and preferred in {"auto", "anthropic"} else None

    if anthropic_runtime is not None:
        try:
            reply = _run_anthropic_agent_sync(context, user_message, language, anthropic_runtime)
        except Exception:  # noqa: BLE001
            logger.exception("anthropic_agent_failed_fallback_openai")
            reply = _run_openai_or_fallback(context, user_message, language)
    else:
        reply = _run_openai_or_fallback(context, user_message, language)

    # Attach sentiment to metadata for analytics
    metadata = {**(reply.metadata_json or {}), "sentiment": sentiment}
    if reply.confirmation_card:
        metadata = {**metadata, **reply.confirmation_card.model_dump(mode="json")}
    add_message(
        context.db,
        session=context.session,
        sender=MessageSender.ASSISTANT,
        content=reply.message,
        language=reply.language,
        metadata_json=metadata,
    )
    return reply


def _run_openai_or_fallback(context: AgentContext, user_message: str, language: str) -> AgentReply:
    if openai_enabled():
        try:
            return run_openai_agent(context, user_message, language)
        except Exception:  # noqa: BLE001
            pass
    return run_fallback_agent(context, user_message, language)


def _run_anthropic_agent_sync(
    context: AgentContext,
    user_message: str,
    language: str,
    runtime,
) -> AgentReply:
    """Non-streaming Anthropic agent call with prompt caching."""
    user_phone_display = context.user.phone or ""
    ctx_block = (
        f"[Session context] "
        f"User: {context.user.full_name} | "
        f"Role: {context.user.role.name.value} | "
        f"Locale: {context.user.locale} | "
        f"phone: {user_phone_display} | "
        f"Workflow: {json.dumps(context.session.workflow_state or {}, ensure_ascii=False)}"
    )
    system_blocks = build_cached_system(build_system_prompt(), ctx_block)

    oai_history = _build_history(context, user_message)
    anthropic_messages = convert_history_to_anthropic(oai_history)
    # Ensure history ends with user message
    if not anthropic_messages or anthropic_messages[-1]["role"] != "user":
        anthropic_messages.append({"role": "user", "content": user_message})

    response = runtime.client.messages.create(
        model=runtime.model,
        max_tokens=2048,
        system=system_blocks,
        messages=anthropic_messages,
        tools=tool_specs_anthropic(),
        temperature=0.65,
    )
    text_blocks = [b for b in response.content if b.type == "text"]
    text = " ".join(b.text for b in text_blocks)
    return AgentReply(message=text, language=language, outcome="needs_input")
