from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from backend.schemas.chat import (
    AUTONOMY_TO_MODE,
    DEFAULT_AUTONOMY,
    DEFAULT_REASONING_EFFORT,
    ReasoningEffort,
    MAX_CHAT_ATTACHMENTS,
    Autonomy,
    ChatAttachment,
    ChatMode,
    ChatScope,
    Posture,
    posture_belongs_to_scope,
)


class _TurnChoices(BaseModel):
    """Postura e autonomia del turno, come le sceglie il consulente.

    Per richiesta, non per thread: cambiarle non biforca la conversazione.
    """

    posture: Posture = "auto"
    autonomy: Autonomy = DEFAULT_AUTONOMY
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT

    @property
    def chat_mode(self) -> ChatMode:
        """La modalita' interna che l'autonomia scelta produce."""
        return AUTONOMY_TO_MODE[self.autonomy]

    def _check_posture(self, scope) -> None:
        scope_type = getattr(scope, "type", None) or "consultant"
        if not posture_belongs_to_scope(self.posture, scope_type):
            raise ValueError(f"La postura {self.posture!r} non appartiene alla chat {scope_type}.")


class ChatRequest(_TurnChoices):
    model_name: str | None = None
    messages: list[dict]
    thread_id: str
    scope: ChatScope | None = None
    attachments: list[ChatAttachment] = Field(
        default_factory=list, max_length=MAX_CHAT_ATTACHMENTS
    )

    @model_validator(mode="after")
    def _posture_matches_scope(self):
        self._check_posture(self.scope)
        return self


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


class ChatMessageAttachmentRecord(BaseModel):
    """Un allegato com'e' partito con il messaggio: quanto basta per mostrarlo."""

    kind: str
    id: str
    label: str = ""


class ChatMessageRecord(BaseModel):
    id: int | None = None
    role: str
    content: str
    created_at: str | None = None
    attachments: list[ChatMessageAttachmentRecord] = Field(default_factory=list)


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


class ChatSessionSearchHit(ChatSessionSummary):
    """Una conversazione trovata, col perche' e' stata trovata."""

    #: Il testo intorno alla parola cercata; vuoto quando ha corrisposto il titolo.
    snippet: str = ""
    #: Chi ha scritto il messaggio dello snippet (`user` / `assistant`).
    snippet_role: str | None = None
    #: Quanti messaggi corrispondono, fino al limite di scansione.
    match_count: int = 0


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


class SendMessageRequest(_TurnChoices):
    message: str
    model_name: str | None = None
    scope: ChatScope | None = None
    # Il cap non e' difesa dal client: oltre un pugno di allegati il turno
    # diventa un dump e il modello smette di leggerli.
    attachments: list[ChatAttachment] = Field(
        default_factory=list, max_length=MAX_CHAT_ATTACHMENTS
    )

    @model_validator(mode="after")
    def _posture_matches_scope(self):
        self._check_posture(self.scope)
        return self


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
