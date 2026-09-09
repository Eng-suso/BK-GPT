from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field


# How much of the workflow the user is handing to the agent this turn. The user
# picks it in the UI; it is not inferred from the message and not chosen by the
# model.
#
# The modes are namespaced per surface because the same three words did not mean
# the same thing in four different chats. `plan / edit / agent` describe work on
# a BPMN canvas; in the consultant and project chats they constrained nothing at
# all - no `consultant.*` or `project.*` capability declared a mode, and no write
# they could reach was in `FORBIDDEN_WRITES` - so the selector promised a limit
# the runtime never applied. Each surface now names the modes its own work has,
# and every one of them narrows something real: the capabilities the router may
# propose, and the writes the guard refuses.
#
# Each surface's delegated modes are a ladder: every rung allows what the rung
# before it allows, plus more. Conversation sits outside that ladder and is the
# safe default until the user explicitly delegates workflow work.
ChatMode: TypeAlias = Literal[
    # Compatibility with the frontend and runtime during the scoped-mode migration.
    "conversation",
    "plan",
    "edit",
    "agent",
    # The consultant chat has one mode: portfolio work has no narrower rung that
    # means anything, and the control the consultant actually wants there is how
    # hard the model thinks (reasoning effort), not what it may touch.
    "consultant.full",
    "project.status",
    "project.coordination",
    "project.execution",
    "process.interview",
    "process.analysis",
    "process.modeling",
    "canvas.plan",
    "canvas.edit",
    "canvas.agent",
]

ChatScopeType: TypeAlias = Literal["consultant", "project", "process", "canvas"]

CHAT_MODES_BY_SCOPE: dict[ChatScopeType, tuple[ChatMode, ...]] = {
    "consultant": ("consultant.full",),
    "project": ("project.status", "project.coordination", "project.execution"),
    "process": ("process.interview", "process.analysis", "process.modeling"),
    "canvas": ("canvas.plan", "canvas.edit", "canvas.agent"),
}

ALL_CHAT_MODES: frozenset[str] = frozenset(
    {"conversation", *(mode for modes in CHAT_MODES_BY_SCOPE.values() for mode in modes)}
)

# Conversation is the safe baseline for callers that do not explicitly hand a
# workflow over to the agent.
DEFAULT_CHAT_MODE_BY_SCOPE: dict[ChatScopeType, ChatMode] = {
    scope: "conversation" for scope in CHAT_MODES_BY_SCOPE
}
DEFAULT_CHAT_MODE: ChatMode = "conversation"


def chat_modes_for_scope(scope_type: str | None) -> tuple[ChatMode, ...]:
    """List the chat modes a scope offers.

    Args:
        scope_type: Untrusted scope type; unknown values fall back to the
            consultant surface.

    Returns:
        The modes available on that surface, narrowest rung first.
    """
    return CHAT_MODES_BY_SCOPE.get(scope_type or "consultant", CHAT_MODES_BY_SCOPE["consultant"])


def default_chat_mode(scope_type: str | None) -> ChatMode:
    """Return the mode a turn runs as when the caller chose none.

    Args:
        scope_type: Untrusted scope type; unknown values fall back to the
            consultant surface.

    Returns:
        Conversation mode, the safe non-workflow baseline.
    """
    return "conversation"


def chat_mode_belongs_to_scope(mode: str | None, scope_type: str | None) -> bool:
    """Check whether a mode is one this surface actually offers.

    Args:
        mode: Untrusted mode identifier, or `None` for "no choice made".
        scope_type: Untrusted scope type.

    Returns:
        True when the mode is absent or belongs to the scope's ladder.
    """
    if mode is None:
        return True
    return mode == "conversation" or mode in chat_modes_for_scope(scope_type)


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
