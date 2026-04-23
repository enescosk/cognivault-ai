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
from app.services.notification_service import send_appointment_confirmation
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
    """Ortak history builder — hem streaming hem normal agent kullanır."""
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
    for item in context.session.messages[-12:]:
        if item.sender == MessageSender.USER:
            history.append({"role": "user", "content": item.content})
        elif item.sender == MessageSender.ASSISTANT:
            history.append({"role": "assistant", "content": item.content})
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
    language = detect_language(user_message, context.user.locale)
    if openai_enabled():
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
