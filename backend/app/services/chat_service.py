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


def maybe_update_title(db: Session, session: ChatSession, user_message: str) -> None:
    if session.title != "New workflow":
        return
    trimmed = user_message.strip()
    if not trimmed:
        return
    session.title = trimmed[:60]
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
