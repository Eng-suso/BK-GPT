from typing import Any

from pydantic import BaseModel

from backend.schemas.chat import ChatScope


class ChatRequest(BaseModel):
    model_name: str | None = None
    messages: list[dict]
    thread_id: str
    scope: ChatScope | None = None


class CreateSessionRequest(BaseModel):
    model_name: str | None = None
    title: str | None = None
    scope: ChatScope | None = None


class CreateSessionResponse(BaseModel):
    thread_id: str
    model_name: str | None = None
    title: str = "Nuova chat"
    scope_type: str | None = None
    project_id: str | None = None
    process_id: str | None = None
    bpmn_model_id: str | None = None
    scope_key: str | None = None


class ChatMessageRecord(BaseModel):
    id: int | None = None
    role: str
    content: str
    created_at: str | None = None


class ChatSessionSummary(BaseModel):
    thread_id: str
    title: str
    model_name: str | None = None
    scope_type: str | None = None
    project_id: str | None = None
    process_id: str | None = None
    bpmn_model_id: str | None = None
    scope_key: str | None = None
    created_at: str
    updated_at: str
    message_count: int = 0


class ChatSessionDetail(BaseModel):
    thread_id: str
    title: str
    model_name: str | None = None
    scope_type: str | None = None
    project_id: str | None = None
    process_id: str | None = None
    bpmn_model_id: str | None = None
    scope_key: str | None = None
    created_at: str
    updated_at: str
    messages: list[ChatMessageRecord]


class SendMessageRequest(BaseModel):
    message: str
    model_name: str | None = None
    scope: ChatScope | None = None


class ChatResponse(BaseModel):
    thread_id: str
    message: str


class SaveMemoryRequest(BaseModel):
    content: str
    category: str


class SearchMemoryRequest(BaseModel):
    query: str
    category: str | None = None


class TranscriptionResponse(BaseModel):
    text: str
    model: str
    segments: list[dict[str, Any]] = []
    duration: float | None = None
