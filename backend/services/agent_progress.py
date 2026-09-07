"""Progresso leggibile dal consulente, non traccia di esecuzione.

Lo stream dell'agente ha tre livelli distinti, e questo modulo governa solo il
secondo:

1. **traccia interna** — eventi ``trace`` e ``node``: nomi di nodo, tool, tempi.
   Servono a chi debugga, non a chi consulta.
2. **progresso utente** — eventi ``activity``: una frase per *fase di lavoro*,
   nel vocabolario del consulente ("Leggo le fonti", non
   "canvas_layout_consultant_agent").
3. **risposta finale** — eventi ``delta``: il testo dell'agente.

Il narratore precedente chiedeva a un LLM una micro-frase ogni 4 secondi di
silenzio: costava una chiamata per battito, ripeteva "Analizzo..." finche' il
turno durava, e taceva proprio quando l'agente stava usando un tool (l'unico
momento in cui il consulente vorrebbe sapere cosa sta succedendo). Qui la fase
si deriva in modo deterministico da cosa l'agente sta effettivamente facendo, e
si emette **solo quando la fase cambia**.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Any


@dataclass(frozen=True)
class ProgressPhase:
    """Una fase di lavoro come la vede il consulente."""

    id: str
    label: str
    icon: str


UNDERSTANDING = ProgressPhase("understanding", "Leggo la richiesta", "brain")
RECALLING = ProgressPhase("recalling", "Cerco nella memoria di lavoro", "recall")
READING_WORKSPACE = ProgressPhase("reading_workspace", "Rileggo i dati del workspace", "folder")
READING_SOURCES = ProgressPhase("reading_sources", "Leggo le fonti raccolte", "document")
RESEARCHING = ProgressPhase("researching", "Cerco riferimenti esterni", "search")
EXTRACTING = ProgressPhase("extracting", "Estraggo fatti e punti aperti", "extract")
COMPARING = ProgressPhase("comparing", "Confronto con le evidenze esistenti", "compare")
MODELING = ProgressPhase("modeling", "Costruisco il modello di processo", "build")
DRAWING = ProgressPhase("drawing", "Disegno il diagramma", "draw")
CHECKING = ProgressPhase("checking", "Verifico coerenza e copertura", "check")
RECORDING = ProgressPhase("recording", "Aggiorno il registro del progetto", "edit")
SAVING_MEMORY = ProgressPhase("saving_memory", "Aggiorno la memoria di lavoro", "recall")
HANDING_OVER = ProgressPhase("handing_over", "Preparo il passaggio di consegne", "route")
ASKING = ProgressPhase("asking", "Preparo le domande aperte", "help")
DRAFTING = ProgressPhase("drafting", "Preparo la risposta", "pen")

ALL_PHASES: tuple[ProgressPhase, ...] = (
    UNDERSTANDING,
    RECALLING,
    READING_WORKSPACE,
    READING_SOURCES,
    RESEARCHING,
    EXTRACTING,
    COMPARING,
    MODELING,
    DRAWING,
    CHECKING,
    RECORDING,
    SAVING_MEMORY,
    HANDING_OVER,
    ASKING,
    DRAFTING,
)

# Nome esatto del tool -> fase. Le regole a prefisso sotto coprono il resto, cosi'
# un tool nuovo non resta muto ne' costringe a ricordarsi di registrarlo.
_TOOL_PHASES: dict[str, ProgressPhase] = {
    "retrieve_consulting_context": RECALLING,
    "retrieve_consulting_graph_context": RECALLING,
    "retrieve_project_context": RECALLING,
    "retrieve_process_context": RECALLING,
    "remember_consultant_fact": SAVING_MEMORY,
    "manage_consultant_memory": SAVING_MEMORY,
    "manage_consultant_playbook": SAVING_MEMORY,
    "manage_consulting_evidence": SAVING_MEMORY,
    "web_research": RESEARCHING,
    "get_workspace_overview": READING_WORKSPACE,
    "list_workspace_project_sources": READING_SOURCES,
    "add_workspace_source": READING_SOURCES,
    "list_workspace_project_decisions": READING_WORKSPACE,
    "prepare_delegation_payload": HANDING_OVER,
    "ask_canvas_clarification": ASKING,
}

# (frammento nel nome del tool, fase). L'ordine conta: il primo che combacia vince.
_TOOL_PREFIX_RULES: tuple[tuple[str, ProgressPhase], ...] = (
    ("source", READING_SOURCES),
    ("interview", READING_SOURCES),
    ("transcript", READING_SOURCES),
    ("playbook", SAVING_MEMORY),
    ("memory", SAVING_MEMORY),
    ("remember", SAVING_MEMORY),
    ("recall", RECALLING),
    ("retrieve", RECALLING),
    ("search", RESEARCHING),
    ("research", RESEARCHING),
    ("web", RESEARCHING),
    ("understanding", EXTRACTING),
    ("extract", EXTRACTING),
    ("review", CHECKING),
    ("validate", CHECKING),
    ("validation", CHECKING),
    ("quality", CHECKING),
    ("draw", DRAWING),
    ("layout", DRAWING),
    ("render", DRAWING),
    ("bpmn", MODELING),
    ("canvas", MODELING),
    ("model", MODELING),
    ("create", RECORDING),
    ("update", RECORDING),
    ("add_", RECORDING),
    ("record", RECORDING),
    ("prepare_home", RECORDING),
    ("list_", READING_WORKSPACE),
    ("get_", READING_WORKSPACE),
)

# (frammento nel nome del nodo, fase). Un nodo senza corrispondenza non produce
# nessun evento: meglio nessun aggiornamento che un nome interno a schermo.
_NODE_RULES: tuple[tuple[str, ProgressPhase], ...] = (
    ("clarification", ASKING),
    ("question", ASKING),
    ("completion_report", DRAFTING),
    ("validation", CHECKING),
    ("review", CHECKING),
    ("layout", DRAWING),
    ("drawing", DRAWING),
    ("construction", MODELING),
    ("patch_edit", MODELING),
    ("understanding", EXTRACTING),
    ("delegation", HANDING_OVER),
)

_ID_LIKE = re.compile(r"^[0-9a-f]{8}-|^[a-z0-9]+[-_][0-9a-f]{6,}$|^\d+$", re.IGNORECASE)
_DETAIL_KEYS = (
    "name",
    "title",
    "source_name",
    "project_name",
    "client_name",
    "process_name",
    "question",
    "query",
    "topic",
    "fact",
)
_DETAIL_MAX_CHARS = 48


def phase_for_tool(tool_name: str | None) -> ProgressPhase | None:
    """Fase corrispondente a un tool, o `None` se il tool non e' riconoscibile."""
    name = (tool_name or "").strip().lower()
    if not name:
        return None

    exact = _TOOL_PHASES.get(name)
    if exact is not None:
        return exact

    for fragment, phase in _TOOL_PREFIX_RULES:
        if fragment in name:
            return phase

    return None


def phase_for_node(node_name: str | None) -> ProgressPhase | None:
    """Fase corrispondente a un nodo del grafo, o `None` se il nodo non ne ha una.

    Non esiste un fallback generico: un nodo sconosciuto tace, perche' l'unica
    alternativa sarebbe mostrare il suo nome interno.
    """
    node = (node_name or "").strip().lower()
    if not node:
        return None

    for fragment, phase in _NODE_RULES:
        if fragment in node:
            return phase

    return None


def detail_from_tool_args(args: Any) -> str:
    """Estrae dal payload di un tool un nome che il consulente riconosce.

    Solo campi di dominio (nomi, titoli, domande): mai identificativi, mai JSON,
    mai frammenti di prompt. Restituisce stringa vuota quando non c'e' niente di
    presentabile.
    """
    if not isinstance(args, dict):
        return ""

    for key in _DETAIL_KEYS:
        raw = args.get(key)
        if not isinstance(raw, str):
            continue

        value = " ".join(raw.strip().split())
        if not value or "{" in value or "}" in value:
            continue
        if _ID_LIKE.match(value):
            continue
        if len(value) > _DETAIL_MAX_CHARS:
            value = value[: _DETAIL_MAX_CHARS - 1].rstrip() + "…"
        return value

    return ""


class ProgressNarrator:
    """Tiene la fase corrente e decide quando vale la pena dirlo.

    Un aggiornamento esce solo quando la fase cambia davvero. Il tempo che passa
    dentro la stessa fase e' compito del client: l'evento porta l'istante di
    inizio, non serve un battito che ripete la stessa frase.
    """

    def __init__(self, *, clock=time.monotonic) -> None:
        self._clock = clock
        self._started_at = clock()
        self._current: ProgressPhase | None = None
        self._sequence = 0

    @property
    def current_phase_id(self) -> str | None:
        return self._current.id if self._current else None

    def elapsed_ms(self) -> int:
        return int((self._clock() - self._started_at) * 1000)

    def enter(self, phase: ProgressPhase | None, *, detail: str = "") -> dict | None:
        """Registra una fase; restituisce il payload da emettere, o `None`.

        `None` significa "niente di nuovo da dire": stessa fase di prima, oppure
        fase non riconosciuta.
        """
        if phase is None:
            return None
        if self._current is not None and phase.id == self._current.id:
            return None

        self._current = phase
        self._sequence += 1
        return {
            "activity_id": f"phase-{self._sequence}-{phase.id}",
            "phase": phase.id,
            "label": phase.label,
            "detail": detail,
            "icon": phase.icon,
            "elapsed_ms": self.elapsed_ms(),
            "source": "phase",
        }

    def enter_for_tool(self, tool_name: str | None, args: Any = None) -> dict | None:
        return self.enter(phase_for_tool(tool_name), detail=detail_from_tool_args(args))

    def enter_for_node(self, node_name: str | None) -> dict | None:
        return self.enter(phase_for_node(node_name))
