from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.orchestrator import AgentContext, process_message, stream_openai_agent
from app.api.dependencies import get_current_user, get_db
from app.models import AuditResultStatus, MessageSender, User
from app.schemas.chat import (
    ChatSessionCreateRequest,
    ChatSessionDetail,
    ChatSessionSummary,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services.audit_service import log_action
from app.services.chat_service import (
    add_message,
    create_session,
    get_session,
    list_sessions,
    maybe_update_title,
)


router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/sessions", response_model=list[ChatSessionSummary])
def get_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[ChatSessionSummary]:
    sessions = list_sessions(db, current_user)
    payload = []
    for session in sessions:
        payload.append(
            ChatSessionSummary(
                id=session.id,
                title=session.title,
                status=session.status,
                created_at=session.created_at,
                updated_at=session.updated_at,
                last_message_preview=session.messages[-1].content[:80] if session.messages else None,
            )
        )
    return payload


@router.post("/sessions", response_model=ChatSessionDetail)
def create_chat_session(
    payload: ChatSessionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionDetail:
    session = create_session(db, current_user, payload.title)
    return ChatSessionDetail(
        id=session.id,
        title=session.title,
        status=session.status,
        workflow_state=session.workflow_state,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[],
    )


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionDetail:
    session = get_session(db, session_id, current_user)
    return ChatSessionDetail(
        id=session.id,
        title=session.title,
        status=session.status,
        workflow_state=session.workflow_state,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=session.messages,
    )


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
def send_message(
    session_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SendMessageResponse:
    session = get_session(db, session_id, current_user)
    # İlk geçiş: ham mesajdan başlık dene
    maybe_update_title(db, session, payload.content)
    add_message(
        db,
        session=session,
        sender=MessageSender.USER,
        content=payload.content,
        language=current_user.locale,
    )
    log_action(
        db,
        user_id=current_user.id,
        session_id=session.id,
        action_type="chat.message_sent",
        explanation="User sent a message to the agent",
        result_status=AuditResultStatus.SUCCESS,
        details={"length": len(payload.content)},
    )
    reply = process_message(AgentContext(db=db, user=current_user, session=session), payload.content)
    # İkinci geçiş: agent cevabı sonrası workflow_state güncellendi, daha spesifik başlık üretilebilir
    session = get_session(db, session_id, current_user)
    maybe_update_title(db, session, payload.content, session.workflow_state)
    return SendMessageResponse(
        session=ChatSessionDetail(
            id=session.id,
            title=session.title,
            status=session.status,
            workflow_state=session.workflow_state,
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=session.messages,
        ),
        assistant_reply=reply,
    )

@router.post("/sessions/{session_id}/messages/stream")
def stream_message(
    session_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    SSE streaming endpoint — kullanıcı mesajını alır, AI yanıtını
    token token Server-Sent Events olarak akar.

    Format:
      data: {"t":"tk","v":"<token>"}\n\n   — metin parçası
      data: {"t":"done","card":<dict|null>}\n\n — akış bitti

    Frontend bu stream'i okuyarak her token'ı anlık ekrana yazar.
    Böylece kullanıcı yanıtın ilk kelimesini <300ms içinde görür.
    """
    session = get_session(db, session_id, current_user)

    # Başlık güncelle (ilk geçiş)
    maybe_update_title(db, session, payload.content)

    # Kullanıcı mesajını hemen kaydet
    add_message(
        db,
        session=session,
        sender=MessageSender.USER,
        content=payload.content,
        language=current_user.locale,
    )
    log_action(
        db,
        user_id=current_user.id,
        session_id=session.id,
        action_type="chat.message_sent",
        explanation="User sent a message (streaming)",
        result_status=AuditResultStatus.SUCCESS,
        details={"length": len(payload.content)},
    )

    context = AgentContext(db=db, user=current_user, session=session)
    language = "tr" if current_user.locale == "tr" else "en"

    def event_stream():
        yield from stream_openai_agent(context, payload.content, language)
        # Stream bitti — başlığı workflow_state ile yeniden dene
        updated = get_session(db, session_id, current_user)
        maybe_update_title(db, updated, payload.content, updated.workflow_state)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # nginx proxy buffering'i kapat
        },
    )


@router.delete("/sessions/{session_id}")
def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    session = get_session(db, session_id, current_user)
    db.delete(session)
    db.commit()
    return {"deleted": session_id}
