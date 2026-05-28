from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ReasoningEventOut(BaseModel):
    id: int
    seq: int
    step_type: str
    node: str
    payload: dict
    created_at: datetime


class ConversationSummary(BaseModel):
    id: str
    customer_id: str | None
    customer_name: str | None
    created_at: datetime
    message_count: int
    last_message: str | None


class ConversationDetail(BaseModel):
    id: str
    customer_id: str | None
    customer_name: str | None
    messages: list[MessageOut]
    events: list[ReasoningEventOut]
