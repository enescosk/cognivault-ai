from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AuditResultStatus, ChatMessage, ChatSession, MessageSender, RoleName, User
from app.services.audit_service import log_action


def create_session(db: Session, user: User, title: str | None = None) -> ChatSession:
    session = ChatSession(user_id=user.id, title=title or "New workflow", workflow_state={})
    db.add(session)
    db.commit()
    db.refresh(session)
    log_action(
        db,
        user_id=user.id,
        session_id=session.id,
        action_type="chat.session_created",
        explanation="New chat session created",
        result_status=AuditResultStatus.SUCCESS,
    )
    return session


def list_sessions(db: Session, current_user: User) -> list[ChatSession]:
    query = select(ChatSession).order_by(ChatSession.updated_at.desc())
    if current_user.role.name == RoleName.CUSTOMER:
        query = query.where(ChatSession.user_id == current_user.id)
    return list(db.scalars(query))


def get_session(db: Session, session_id: int, current_user: User) -> ChatSession:
    query = (
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id)
        .order_by(ChatSession.updated_at.desc())
    )
    session = db.scalars(query).first()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    if current_user.role.name == RoleName.CUSTOMER and session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to access this chat")
    return session


def add_message(
    db: Session,
    *,
    session: ChatSession,
    sender: MessageSender,
    content: str,
    language: str,
    metadata_json: dict | None = None,
) -> ChatMessage:
    message = ChatMessage(
        session_id=session.id,
        sender=sender,
        content=content,
        language=language,
        metadata_json=metadata_json or {},
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def update_workflow_state(db: Session, session: ChatSession, new_state: dict) -> ChatSession:
    session.workflow_state = new_state
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


import re as _re

# Anlamlı içerik taşımayan mesajlar — başlık üretme
# Sadece tarih / telefon / sayı içeren mesajları atla
_INFO_ONLY_RE = _re.compile(
    r"^(tarih\s+(olarak\s+)?[\d./]+|[\d./]+\s+tarihi?"
    r"|\+?[\d\s\-().]{9,}"         # sadece telefon
    r"|\d{1,2}[./]\d{1,2}([./]\d{2,4})?"  # sadece tarih
    r"|(pazartesi|salı|çarşamba|perşembe|cuma|cumartesi|pazar)(\s+günü?)?"  # sadece gün adı
    r"|[1-3]\b"                     # sadece slot seçimi
    r")\s*([ve,]\s*\+?[\d\s\-().]+)?$",
    _re.IGNORECASE | _re.UNICODE,
)

_FILLER_RE = _re.compile(
    r"^("
    # selamlaşma + nasılsın kombinasyonları
    r"(merhaba|selam|selamlar|hello|hi|hey|sa|iyi\s*günler|günaydın)"
    r"(\s+(nasıls[ıi]n|nasılsun|iyi\s*misin|naber|ne\s*haber|:?\)))*"
    r"|nasıls[ıi]n|nasılsun|naber|ne\s*haber|iyi\s*misin"
    # onay / kısa yanıt
    r"|evet|tamam|ok|olur|tabii(\s*ki)?|tabi(\s*ki)?|güzel|iyi|anladım"
    r"|teşekkür(ler)?|peki|harika|süper|tamamdır|anladım"
    r")\s*[.!?]?$",
    _re.IGNORECASE | _re.UNICODE,
)

_DEPT_TITLES: list[tuple[list[str], str]] = [
    (["onboarding", "kurulum", "başlangıç", "devreye"],  "Onboarding Randevusu"),
    (["teknik", "technical", "support", "destek", "arıza", "sorun"], "Teknik Destek Randevusu"),
    (["fatura", "billing", "ödeme", "invoice"],           "Fatura İşlemleri Randevusu"),
    (["compliance", "uyum", "denetim", "legal"],          "Uyum Danışmanlığı Randevusu"),
]

_APT_KEYWORDS = ["randevu", "appointment", "rezervasyon", "book", "schedule", "görüşme", "toplantı",
                 "almak istiyorum", "oluştur", "ayarla", "planla"]
# Saat ifadesi de randevu bağlamında ipucu sayılır
_TIME_RE = _re.compile(r"\b\d{1,2}[:.]\d{2}\b|\bsaat\b|\bsa\b", _re.IGNORECASE)


def _title_score(text: str, workflow_state: dict | None = None) -> tuple[int, str | None]:
    """
    (skor, başlık) döner. Yüksek skor = daha spesifik/kaliteli başlık.
    Skor: 4=dept+purpose, 3=dept+apt, 2=dept, 1=apt, 0=cümle, -1=atla
    """
    stripped = text.strip()
    if not stripped:
        return -1, None
    if _FILLER_RE.match(stripped):
        return -1, None
    if _INFO_ONLY_RE.match(stripped):
        return -1, None

    lower = stripped.lower()

    # Skor 4: workflow'dan dept + purpose
    if workflow_state:
        collected = workflow_state.get("collected") or {}
        dept = (collected.get("department") or "").lower()
        purpose = (collected.get("purpose") or "").strip()
        for keywords, title in _DEPT_TITLES:
            if any(k in dept for k in keywords):
                if purpose:
                    suffix = purpose[:28].rstrip() + ("…" if len(purpose) > 28 else "")
                    return 4, f"{title.split(' Randevusu')[0]} – {suffix}"
                return 3, title

    has_apt = any(k in lower for k in _APT_KEYWORDS) or bool(_TIME_RE.search(stripped))

    # Skor 3: mesajda dept + randevu/saat
    for keywords, title in _DEPT_TITLES:
        if any(k in lower for k in keywords) and has_apt:
            return 3, title

    # Skor 2: mesajda sadece dept
    for keywords, title in _DEPT_TITLES:
        if any(k in lower for k in keywords):
            return 2, title.replace(" Randevusu", "")

    # Skor 1: sadece randevu isteği
    if has_apt:
        return 1, "Randevu Talebi"

    # Skor 0: anlamlı cümle
    clean = _re.sub(r"^(ben\s+|bir\s+|şu\s+|acaba\s+)", "", stripped, flags=_re.IGNORECASE | _re.UNICODE)
    first_sent = _re.split(r"[.!?\n]", clean)[0].strip()
    if len(first_sent) >= 10:
        t = first_sent[0].upper() + first_sent[1:]
        return 0, t[:48] + ("…" if len(first_sent) > 48 else "")

    return -1, None


def _extract_title(text: str, workflow_state: dict | None = None) -> str | None:
    """En iyi (skor, başlık) döner; skor < 0 ise None."""
    _, title = _title_score(text, workflow_state)
    return title


def maybe_update_title(db: Session, session: ChatSession, user_message: str, workflow_state: dict | None = None) -> None:
    """
    Başlığı yalnızca daha iyi bir başlık üretilebiliyorsa günceller.
    Skor sistemiyle: workflow_state dept+purpose > dept+apt > dept > apt > cümle.
    """
    _UPGRADEABLE = {"New workflow", "New workflow ", "Randevu Talebi"}
    if session.title not in _UPGRADEABLE:
        return

    score, candidate = _title_score(user_message, workflow_state)
    if score < 0 or not candidate or candidate == session.title:
        return

    # Mevcut başlık "Randevu Talebi" ise sadece skor>=2 ile upgrade et
    if session.title == "Randevu Talebi" and score < 2:
        return

    session.title = candidate
    db.add(session)
    db.commit()


def session_detail_payload(session: ChatSession) -> dict:
    last_preview = session.messages[-1].content[:80] if session.messages else None
    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "last_message_preview": last_preview,
    }
