from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.schemas.chat import (
    MAX_CHAT_ATTACHMENTS,
    ChatAttachment,
    ChatScope,
)


# Public requests must match the modes enforced by the current router and write
# guard. Scope-specific modes are not wired through that runtime yet.
RequestChatMode = Literal["plan", "edit", "agent"]


class ChatRequest(BaseModel):
    model_name: str | None = None
    messages: list[dict]
    thread_id: str
    scope: ChatScope | None = None
    # How much of the workflow the user is handing over this turn. Per-request, not
    # per-thread: switching mode must not fork the conversation.
    mode: RequestChatMode = "agent"
    attachments: list[ChatAttachment] = Field(
        default_factory=list, max_length=MAX_CHAT_ATTACHMENTS
    )


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
    mode: RequestChatMode = "agent"
    # Il cap non e' difesa dal client: oltre un pugno di allegati il turno
    # diventa un dump e il modello smette di leggerli.
    attachments: list[ChatAttachment] = Field(
        default_factory=list, max_length=MAX_CHAT_ATTACHMENTS
    )


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
    # Lingua effettivamente richiesta all'API (ISO-639-1), e quanti segmenti il
    # guard ha scartato perche' tornati in un altro alfabeto: senza questo, un
    # transcript accorciato dal guard e' indistinguibile da uno corto.
    language: str = ""
    segments: list[dict[str, Any]] = []
    dropped_segments: int = 0
    duration: float | None = None
