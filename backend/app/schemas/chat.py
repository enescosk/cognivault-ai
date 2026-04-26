from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.appointment import AppointmentConfirmationCard


class ChatSessionCreateRequest(BaseModel):
    title: str | None = None


class ChatSessionSummary(BaseModel):
    id: int
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender: str
    content: str
    language: str
    metadata_json: dict | None = None
    created_at: datetime


class ChatSessionDetail(BaseModel):
    id: int
    title: str
    status: str
    workflow_state: dict
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse]


class SendMessageRequest(BaseModel):
    content: str


class AgentReply(BaseModel):
    message: str
    language: str
    outcome: str
    confirmation_card: AppointmentConfirmationCard | None = None
    metadata_json: dict | None = None


class SendMessageResponse(BaseModel):
    session: ChatSessionDetail
    assistant_reply: AgentReply
