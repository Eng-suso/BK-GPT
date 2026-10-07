from typing import Annotated, Literal, TypeAlias, TypeGuard

from pydantic import BaseModel, Field, model_validator


# Due scelte del consulente per ogni turno, su due assi separati
# (docs: "DeliR - Architettura delle modalita' di lavoro"):
#
# - la *postura*: che tipo di lavoro sta facendo. Diversa per chat, e "auto"
#   per default: DeliR la ricava dal messaggio. Guida il router e il modo di
#   rispondere; non vieta mai una scrittura.
# - l'*autonomia*: quanto DeliR puo' fare da solo. Uguale in ogni chat. E' lei a
#   decidere se una scrittura parte (Auto), aspetta un si' (Chiedi
#   approvazione) o non parte (Manuale).
#
# Prima le due cose erano una sola scala - Conversazione / Piano / Modifica /
# Agente - pensata per il BPMN e applicata a tutte le chat: nella chat del
# consulente "Conversazione", il default, toglieva al router la creazione di
# clienti e progetti, e l'agente finiva per annunciare salvataggi mai fatti.

# La modalita' interna, su cui sono costruiti router (`CapabilitySpec.modes`) e
# guard delle scritture (`agents/chat_mode.py`). Non arriva piu' dal client:
# la produce l'autonomia, con `AUTONOMY_TO_MODE`.
ChatMode: TypeAlias = Literal["conversation", "plan", "edit", "agent"]

# Chi chiama il runtime senza una richiesta HTTP (eval, script) e non dice
# niente parte dalla modalita' che non scrive.
DEFAULT_CHAT_MODE: ChatMode = "conversation"

Autonomy: TypeAlias = Literal["auto", "ask", "manual"]
DEFAULT_AUTONOMY: Autonomy = "auto"
AUTONOMY_TO_MODE: dict[str, ChatMode] = {
    # Scrive da solo; le azioni distruttive chiedono comunque conferma.
    "auto": "agent",
    # Il modello BPMN cambia dal bottone Approva della review, i record del
    # workspace dopo il si' del consulente (`confirm_workspace_write`).
    "ask": "plan",
    # Propone e spiega, non scrive.
    "manual": "conversation",
}

ChatScopeType: TypeAlias = Literal["consultant", "project", "process", "canvas"]

# Quanto il modello deve pensare prima di rispondere. E' il controllo che il
# consulente ha davvero in mano nella chat: non cosa l'agente puo' toccare (la
# modalita'), ma quanto tempo e quanti token valgono questa domanda.
ReasoningEffort: TypeAlias = Literal["low", "medium", "high"]

# Il livello piu' basso e' quello con cui il prodotto ha sempre risposto finora:
# resta il default, cosi' un turno costa quanto costava e i livelli piu' alti si
# pagano solo quando qualcuno li chiede.
DEFAULT_REASONING_EFFORT: ReasoningEffort = "low"

# Cio' che l'interfaccia chiama "Rapido" per il fornitore e' "nessun
# ragionamento": e' il valore con cui l'agente ha sempre girato, ed e' anche cio'
# che l'etichetta promette. La traduzione vive qui, in un punto solo, perche' i
# nomi dei livelli del fornitore cambiano fra famiglie di modelli mentre il
# controllo che il consulente vede no.
PROVIDER_REASONING_EFFORT: dict[ReasoningEffort, str] = {
    "low": "none",
    "medium": "medium",
    "high": "high",
}

Posture: TypeAlias = Literal[
    "auto",
    "desk",
    "prepare",
    "align",
    "analyze",
    "deliver",
    "discover",
    "improve",
    "validate",
    "map",
    "review",
    "compare",
]

POSTURES_BY_SCOPE: dict[ChatScopeType, tuple[str, ...]] = {
    "consultant": ("desk", "prepare"),
    "project": ("align", "analyze", "deliver"),
    "process": ("discover", "improve", "validate"),
    "canvas": ("map", "review", "compare"),
}


def is_chat_scope_type(value: str | None) -> TypeGuard[ChatScopeType]:
    """Questa stringa nomina una superficie che esiste davvero?"""
    return value in POSTURES_BY_SCOPE


def postures_for_scope(scope_type: str | None) -> tuple[str, ...]:
    """Le posture che una chat offre, senza "auto".

    Args:
        scope_type: Tipo di scope non affidabile; un valore sconosciuto vale
            come chat del consulente.
    """
    scope: ChatScopeType = scope_type if is_chat_scope_type(scope_type) else "consultant"
    return POSTURES_BY_SCOPE[scope]


def posture_belongs_to_scope(posture: str | None, scope_type: str | None) -> bool:
    """`auto` vale ovunque; le altre posture solo nella chat che le offre."""
    if posture is None or posture == "auto":
        return True
    return posture in postures_for_scope(scope_type)


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
    # La versione salvata da cui viene `current_bpmn_xml`. Il turno la usa come
    # base: se nel frattempo qualcuno ha salvato, l'agente non ci scrive sopra.
    current_bpmn_version_id: int | None = None
    review_node_id: str | None = Field(default=None, min_length=1, max_length=256)
    review_base_revision: str | None = Field(default=None, min_length=64, max_length=64)

    @model_validator(mode="after")
    def review_target_is_complete(self):
        if bool(self.review_node_id) != bool(self.review_base_revision):
            raise ValueError("La chat di review richiede task e revisione insieme.")
        return self


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
    key = f"canvas:{scope.project_id}:{scope.process_id}:{scope.bpmn_model_id}"
    return f"{key}:review:{scope.review_node_id}" if scope.review_node_id else key
