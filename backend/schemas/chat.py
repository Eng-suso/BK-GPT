from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field


# How much of the workflow the user is handing to the agent this turn. The user
# picks it in the UI; it is not inferred from the message and not chosen by the
# model. `agent` is the default and the full loop.
ChatMode: TypeAlias = Literal["plan", "edit", "agent"]
DEFAULT_CHAT_MODE: ChatMode = "agent"


class ConsultantChatScope(BaseModel):
    type: Literal["consultant"]


class ProjectChatScope(BaseModel):
    type: Literal["project"]
    project_id: str


class ProcessChatScope(BaseModel):
    type: Literal["process"]
    project_id: str
    process_id: str


class CanvasChatScope(BaseModel):
    type: Literal["canvas"]
    project_id: str
    process_id: str
    bpmn_model_id: str
    current_bpmn_xml: str | None = None


ChatScope: TypeAlias = Annotated[
    ConsultantChatScope | ProjectChatScope | ProcessChatScope | CanvasChatScope,
    Field(discriminator="type"),
]


# Cosa il consulente mette sul tavolo insieme al messaggio. Non sono file: sono
# riferimenti a oggetti che il workspace conosce gia', piu' il testo incollato a
# mano. Arrivano come id + etichetta; il contenuto lo rilegge il backend al
# momento del turno, cosi' l'allegato non invecchia dentro il thread.
MAX_NOTE_ATTACHMENT_CHARS = 20_000
MAX_CHAT_ATTACHMENTS = 8


class SourceAttachment(BaseModel):
    kind: Literal["source"]
    id: str
    label: str
    project_id: str


class ProcessAttachment(BaseModel):
    kind: Literal["process"]
    id: str
    label: str
    project_id: str


class SimulationRunAttachment(BaseModel):
    kind: Literal["simulation_run"]
    id: str
    label: str
    bpmn_model_id: str


class NoteAttachment(BaseModel):
    kind: Literal["note"]
    id: str
    label: str
    text: str = Field(max_length=MAX_NOTE_ATTACHMENT_CHARS)


ChatAttachment: TypeAlias = Annotated[
    SourceAttachment | ProcessAttachment | SimulationRunAttachment | NoteAttachment,
    Field(discriminator="kind"),
]


def chat_scope_key(scope: ChatScope | None) -> str:
    """Build a stable key for a chat scope.
    
    Args:
        scope: Untrusted chat scope input, or None for the consultant-wide scope.
    
    Returns:
        The canonical scope key.
    """
    if scope is None or scope.type == "consultant":
        return "consultant"
    if scope.type == "project":
        return f"project:{scope.project_id}"
    if scope.type == "process":
        return f"process:{scope.project_id}:{scope.process_id}"
    return f"canvas:{scope.project_id}:{scope.process_id}:{scope.bpmn_model_id}"
