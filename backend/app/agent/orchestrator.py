from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re

from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy.orm import Session

from app.agent.prompts import build_system_prompt
from app.core.config import get_settings
from app.models import ChatSession, MessageSender, User
from app.schemas.chat import AgentReply
from app.schemas.appointment import AppointmentConfirmationCard
from app.services.appointment_service import format_slot_label
from app.services.chat_service import add_message, update_workflow_state
from app.services.external_intent_service import extract_external_request_terms
from app.services.intelligence_service import discover_company_contact_for_agent
from app.services.notification_service import send_appointment_confirmation
from app.tools.registry import execute_tool, tool_specs, tool_specs_anthropic


settings = get_settings()


@dataclass
class AgentContext:
    db: Session
    user: User
    session: ChatSession


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
# Goal: never call a paid API for trivial messages.
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
    # Very short messages are likely simple
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
    # Personalise with name if available
    if user_name and intent == "greeting":
        first = user_name.split()[0]
        template = template.replace("Merhaba!", f"Merhaba, {first}!").replace("Hello!", f"Hello, {first}!")
    # Sentiment overlay
    if sentiment == "frustrated" and intent not in ("thanks", "farewell"):
        prefix = "Üzgünüm duyduğuma. " if language == "tr" else "I'm sorry to hear that. "
        template = prefix + template
    return template


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
    turkish_markers = ["ş", "ğ", "ı", "ç", "ö", "ü", "randevu", "merhaba", "yardım", "bugün", "yarın"]
    return "tr" if any(marker in text.lower() for marker in turkish_markers) or fallback == "tr" else "en"


def parse_preferred_date(text: str) -> str | None:
    """Türkçe/kısa tarih ifadelerini YYYY-MM-DD'ye çevirir."""
    from datetime import date, timedelta
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


def extract_outreach_terms(text: str) -> dict | None:
    structured_terms = extract_external_request_terms(text)
    if structured_terms:
        return structured_terms

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
    search_query = f"{company} {location or ''}".strip()
    return {
        "company": company,
        "category": category,
        "location": location,
        "purpose": purpose or "görüşme talebi",
        "search_query": search_query,
    }


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


def parse_slot_selection(text: str, suggested_slots: list[dict]) -> dict | None:
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


def default_reply(language: str, message_tr: str, message_en: str) -> str:
    return message_tr if language == "tr" else message_en


def anthropic_enabled() -> bool:
    return bool(settings.anthropic_api_key)


def openai_enabled() -> bool:
    return bool(settings.openai_api_key)


def run_anthropic_agent(context: AgentContext, user_message: str, language: str) -> AgentReply:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = build_system_prompt() + "\n\n" + json.dumps({
        "workflow_state": context.session.workflow_state,
        "current_user": {
            "id": context.user.id,
            "role": context.user.role.name.value,
            "locale": context.user.locale,
        },
    })

    # Geçmiş mesajları Anthropic formatına çevir
    history: list[dict] = []
    for item in context.session.messages[-10:]:
        if item.sender == MessageSender.TOOL:
            continue
        role = "user" if item.sender == MessageSender.USER else "assistant"
        history.append({"role": role, "content": item.content})
    history.append({"role": "user", "content": user_message})

    for _ in range(6):
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=system_prompt,
            messages=history,
            tools=tool_specs_anthropic(),  # type: ignore[arg-type]
        )

        # Tool use var mı?
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]
        assistant_text = text_blocks[0].text if text_blocks else ""

        if not tool_uses:
            # Sadece metin yanıtı
            return AgentReply(message=assistant_text, language=language, outcome="needs_input")

        # Tool use yanıtını history'ye ekle
        history.append({"role": "assistant", "content": response.content})  # type: ignore[arg-type]

        # Tool'ları çalıştır ve sonuçları topla
        tool_results = []
        confirmation_card = None

        for tool_use in tool_uses:
            result = execute_tool(
                context.db,
                name=tool_use.name,
                arguments=json.dumps(tool_use.input),
                current_user=context.user,
                session=context.session,
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": json.dumps(result),
            })

            if tool_use.name == "create_appointment":
                confirmation_card = AppointmentConfirmationCard(
                    confirmation_code=result["confirmation_code"],
                    department=result["department"],
                    scheduled_at=result["scheduled_at"],
                    location=result["location"],
                    contact_phone=result["contact_phone"],
                    status=result["status"],
                )

        history.append({"role": "user", "content": tool_results})

        if confirmation_card:
            # Randevu oluşturuldu — bir sonraki döngüde AI onay mesajı üretecek
            # Ama hemen dönmek için bir tur daha çalıştır
            final = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=512,
                system=system_prompt,
                messages=history,
                tools=tool_specs_anthropic(),  # type: ignore[arg-type]
            )
            final_text_blocks = [b for b in final.content if b.type == "text"]
            final_text = final_text_blocks[0].text if final_text_blocks else default_reply(
                language,
                "Randevunuz oluşturuldu.",
                "Your appointment has been created.",
            )
            return AgentReply(
                message=final_text,
                language=language,
                outcome="completed",
                confirmation_card=confirmation_card,
            )

    raise HTTPException(status_code=502, detail="The AI agent could not complete the request")


def run_openai_agent(context: AgentContext, user_message: str, language: str) -> AgentReply:
    client = OpenAI(api_key=settings.openai_api_key)

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

    # Sadece kullanıcı ve asistan mesajlarını geçmişe ekle (tool mesajları OpenAI'da tool_call_id gerektiriyor)
    for item in context.session.messages[-12:]:
        if item.sender == MessageSender.USER:
            history.append({"role": "user", "content": item.content})
        elif item.sender == MessageSender.ASSISTANT:
            history.append({"role": "assistant", "content": item.content})
        # system ve tool mesajları zaten context bloğunda var, atla

    history.append({"role": "user", "content": user_message})

    for _ in range(6):
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=history,
            tools=tool_specs(),
            tool_choice="auto",
            temperature=0.65,
        )
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
                    # Kullanıcıya bildirim gönder
                    send_appointment_confirmation(
                        to_email=context.user.email,
                        full_name=context.user.full_name,
                        confirmation_code=result["confirmation_code"],
                        department=result["department"],
                        scheduled_at=str(scheduled_at_val),
                        location=result["location"],
                        contact_phone=result["contact_phone"],
                        purpose=result.get("purpose", ""),
                        language=language,
                    )

            # Randevu oluşturulduysa AI'ın güzel onay mesajı yazmasına izin ver
            if confirmation_card:
                final = client.chat.completions.create(
                    model=settings.openai_model,
                    messages=history,
                    temperature=0.65,
                )
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
#     OpenAI'a "tool_choice=auto" ile sor.
#     Tool call gelirse çalıştır, history'e ekle, tekrar sor.
#     Bu turlar text üretmez, sadece araç çağırır → ortalama <300ms/tur.
#
#   Faz 2 — Stream      (streaming, "tool_choice=none")
#     Tüm tool'lar tamamlandı, artık sadece metin üretiliyor.
#     "tool_choice=none" ile OpenAI'ı kilitleyip gerçek SSE stream'i başlat.
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
    # Use compressed history to save tokens on long conversations
    history.extend(_compress_history(context.session.messages))
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
            send_appointment_confirmation(
                to_email=context.user.email,
                full_name=context.user.full_name,
                confirmation_code=result["confirmation_code"],
                department=result["department"],
                scheduled_at=str(scheduled_at_val),
                location=result["location"],
                contact_phone=result["contact_phone"],
                purpose=result.get("purpose", ""),
                language=context.user.locale,
            )

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

    client = OpenAI(api_key=settings.openai_api_key)
    history = _build_history(context, user_message)
    confirmation_card: AppointmentConfirmationCard | None = None

    # ── Faz 1: Tool Loop ─────────────────────────────────────────────────────
    for _ in range(6):
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=history,
            tools=tool_specs(),
            tool_choice="auto",
            temperature=0.65,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            # Tool call yok → Faz 2'ye geç (bu history ile stream aç)
            break

        # Tool call var → çalıştır, history'e ekle, döngüye devam et
        history, card = _execute_tool_calls(context, message, history)
        if card:
            confirmation_card = card
        # Tool sonuçları history'de, bir sonraki turda AI yanıt üretecek

    # ── Faz 2: Streaming Final Response ──────────────────────────────────────
    # tool_choice="none" → OpenAI artık yeni tool call açamaz, sadece metin yazar.
    # stream=True → her token chunk anında yield edilir.
    try:
        stream = client.chat.completions.create(
            model=settings.openai_model,
            messages=history,
            tools=tool_specs(),
            stream=True,
            tool_choice="none",   # Faz 2'de tool call istemiyoruz
            temperature=0.65,
        )

        full_text = ""
        for chunk in stream:
            delta = chunk.choices[0].delta
            token = delta.content or ""
            if token:
                full_text += token
                yield _sse({"t": "tk", "v": token})

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
        yield _sse({"t": "err", "v": str(exc)})


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
    2. Outreach request? → intelligence service, no LLM needed.
    3. OpenAI enabled? → full LLM agent with tool calling.
    4. Fallback → local rule-based engine (works without any API key).
    """
    language  = detect_language(user_message, context.user.locale)
    sentiment = detect_sentiment(user_message)

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

    # ── Tier 2: outreach / intelligence ──────────────────────────────────────
    outreach_reply = handle_company_outreach_request(context, user_message, language)
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

    # ── Tier 3: LLM agent ─────────────────────────────────────────────────────
    if openai_enabled():
        try:
            reply = run_openai_agent(context, user_message, language)
        except Exception:  # noqa: BLE001
            reply = run_fallback_agent(context, user_message, language)
    elif anthropic_enabled():
        try:
            reply = run_anthropic_agent(context, user_message, language)
        except Exception:  # noqa: BLE001
            reply = run_fallback_agent(context, user_message, language)
    else:
        # ── Tier 4: local rule-based fallback (zero cost) ─────────────────────
        reply = run_fallback_agent(context, user_message, language)

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
