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

_APT_KEYWORDS = ["randevu", "appointment", "rezervasyon", "book", "schedule", "görüşme", "toplantı"]


def _extract_title(text: str, workflow_state: dict | None = None) -> str | None:
    """
    Konuşma metninden ve workflow state'ten anlamlı bir başlık çıkar.
    Boş / selamlama mesajları için None döner.
    """
    stripped = text.strip()
    if not stripped or _FILLER_RE.match(stripped):
        return None

    lower = stripped.lower()

    # 1) Workflow state'te zaten departman var → spesifik başlık
    if workflow_state:
        collected = workflow_state.get("collected") or {}
        dept = (collected.get("department") or "").lower()
        purpose = (collected.get("purpose") or "").strip()
        for keywords, title in _DEPT_TITLES:
            if any(k in dept for k in keywords):
                if purpose:
                    # Amaç kısa ise başlığa ekle
                    suffix = purpose[:28].rstrip() + ("…" if len(purpose) > 28 else "")
                    return f"{title.split(' Randevusu')[0]} – {suffix}"
                return title

    # 2) Mesaj içinde departman + randevu ipucu var mı?
    has_apt = any(k in lower for k in _APT_KEYWORDS)
    for keywords, title in _DEPT_TITLES:
        if any(k in lower for k in keywords):
            return title if has_apt else title.replace(" Randevusu", "")

    # 3) Sadece genel randevu isteği
    if has_apt:
        return "Randevu Talebi"

    # 4) Anlamlı cümlenin ilk parçasını al (min 10 karakter)
    # Gereksiz fiilleri/giriş kelimelerini strip et
    clean = _re.sub(r"^(ben\s+|bir\s+|şu\s+|acaba\s+)", "", stripped, flags=_re.IGNORECASE | _re.UNICODE)
    first_sent = _re.split(r"[.!?\n]", clean)[0].strip()
    if len(first_sent) >= 10:
        # Capitalize
        title = first_sent[0].upper() + first_sent[1:]
        return title[:48] + ("…" if len(first_sent) > 48 else "")

    return None


def maybe_update_title(db: Session, session: ChatSession, user_message: str, workflow_state: dict | None = None) -> None:
    """
    'New workflow' olan başlığı günceller.
    workflow_state verilirse departman/amaç bilgisiyle daha spesifik başlık üretir.
    """
    if session.title not in ("New workflow", "New workflow "):
        # Eğer zaten genel bir randevu başlığıysa ve şimdi daha spesifik olabiliyorsa güncelle
        generic_titles = {"Randevu Talebi"}
        if session.title not in generic_titles:
            return

    candidate = _extract_title(user_message, workflow_state)
    if not candidate:
        return

    if candidate == session.title:
        return  # zaten aynı, commit etme

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
