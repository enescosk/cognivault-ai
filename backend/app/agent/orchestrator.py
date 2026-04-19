from __future__ import annotations

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
from app.tools.registry import execute_tool, tool_specs, tool_specs_anthropic


settings = get_settings()


@dataclass
class AgentContext:
    db: Session
    user: User
    session: ChatSession


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

    # "24.04" veya "24/04" formatları → bu yıl
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
    history = [{"role": "system", "content": build_system_prompt()}]
    history.append(
        {
            "role": "system",
            "content": json.dumps(
                {
                    "workflow_state": context.session.workflow_state,
                    "current_user": {
                        "id": context.user.id,
                        "role": context.user.role.name.value,
                        "locale": context.user.locale,
                    },
                }
            ),
        }
    )
    for item in context.session.messages[-8:]:
        history.append({"role": item.sender.value if item.sender != MessageSender.TOOL else "tool", "content": item.content})
    history.append({"role": "user", "content": user_message})

    for _ in range(6):
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=history,
            tools=tool_specs(),
            tool_choice="auto",
            temperature=0.2,
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
                        "content": json.dumps(result),
                    }
                )
                if tool_call.function.name == "create_appointment":
                    card = AppointmentConfirmationCard(
                        confirmation_code=result["confirmation_code"],
                        department=result["department"],
                        scheduled_at=result["scheduled_at"],
                        location=result["location"],
                        contact_phone=result["contact_phone"],
                        status=result["status"],
                    )
                    return AgentReply(
                        message=message.content
                        or default_reply(
                            language,
                            "Randevunuz oluşturuldu.",
                            "Your appointment has been created.",
                        ),
                        language=language,
                        outcome="completed",
                        confirmation_card=card,
                    )
            continue

        return AgentReply(message=message.content or "", language=language, outcome="needs_input")

    raise HTTPException(status_code=502, detail="The AI agent could not complete the request")


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
        state["stage"] = "collect_phone"
        update_workflow_state(context.db, context.session, state)
        return AgentReply(
            message=default_reply(
                language,
                "Randevu teyidi için ulaşabileceğimiz telefon numarasını paylaşır mısınız?",
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
    language = detect_language(user_message, context.user.locale)
    if anthropic_enabled():
        try:
            reply = run_anthropic_agent(context, user_message, language)
        except Exception:  # noqa: BLE001
            reply = run_fallback_agent(context, user_message, language)
    elif openai_enabled():
        try:
            reply = run_openai_agent(context, user_message, language)
        except Exception:  # noqa: BLE001
            reply = run_fallback_agent(context, user_message, language)
    else:
        reply = run_fallback_agent(context, user_message, language)

    metadata = {}
    if reply.confirmation_card:
        metadata = reply.confirmation_card.model_dump(mode="json")
    add_message(
        context.db,
        session=context.session,
        sender=MessageSender.ASSISTANT,
        content=reply.message,
        language=reply.language,
        metadata_json=metadata,
    )
    return reply
