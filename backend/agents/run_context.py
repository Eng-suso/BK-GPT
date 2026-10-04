"""Identita' del turno corrente, per i tool che hanno bisogno di stato fra turni.

`bind_active_scope` (scope_guard) fissa *dove* si sta lavorando; qui si fissa
*in quale conversazione*. Serve alle azioni in due tempi (proponi -> conferma):
l'azione in attesa vive in `pending_action`, chiavata sul thread, e il tool di
conferma deve poterla ritrovare senza che il modello si ricordi un id.

Fuori da un agent run (worker, script, test) il thread e' `None` e i chiamanti
degradano su un thread esplicito o rifiutano l'operazione. Come per scope_guard,
se LangGraph esegue un nodo in un thread di sistema separato il ContextVar non
propaga: in quel caso il tool lo dice invece di indovinare.
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_active_thread: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "active_agent_thread", default=None
)


@contextmanager
def bind_active_thread(thread_id: str | None) -> Iterator[None]:
    """
    Temporarily bind the active agent thread ID for the current execution context.
    
    Args:
        thread_id (str | None): Untrusted thread identifier. Falsy values are normalized to
            None.
    
    Yields:
        None: Control while the thread ID is bound.
    
    The previous thread ID is restored when the context exits. The binding is scoped to the
    current context and is not persisted. If restoration occurs in a different execution
    context, the reset is skipped and a warning is logged.
    """
    token = _active_thread.set(str(thread_id) if thread_id else None)
    try:
        yield
    finally:
        try:
            _active_thread.reset(token)
        except ValueError:
            logger.warning(
                "active thread reset skipped because LangGraph resumed in a different context"
            )


def active_thread_id() -> str | None:
    """Get the active agent conversation/thread ID.
    
    Returns:
        str | None: The active thread ID, or `None` when no thread is active.
    """
    return _active_thread.get()


class BpmnVersionConflict(ValueError):
    """Il disegno e' cambiato dopo che chi scrive lo ha letto.

    Il messaggio e' scritto per chi lo riceve: il consulente (409 sul
    salvataggio manuale) o il modello (esito del tool), e dice cosa fare.
    Sta qui e non in `workspace_database` perche' il nodo dei tool deve
    poterlo riconoscere senza importare il database.
    """


def report_bpmn_version_conflict(exc: BpmnVersionConflict) -> str:
    """Esito del tool quando il canvas e' cambiato sotto l'agente.

    LangGraph ricava dal tipo dell'argomento quali eccezioni gestire: solo il
    conflitto diventa un messaggio per il modello, ogni altro errore del tool
    si propaga come prima.
    """
    return f"Modifica non salvata: {exc}"


@dataclass
class TurnWrites:
    """Cosa il turno corrente ha scritto sul canvas, e da quando lavora.

    Serve a riconoscere un salvataggio altrui arrivato a meta' turno: l'agente
    ha letto il disegno all'inizio, quindi una versione nata dopo `started_at`
    e non scritta da lui e' lavoro che una sua scrittura cancellerebbe.

    E' un oggetto mutabile dentro il ContextVar apposta: LangGraph esegue i
    tool in una copia del contesto, e la copia vede lo stesso oggetto, quindi
    le versioni scritte da un tool restano visibili al tool successivo.
    """

    started_at: str
    written_version_ids: set[int] = field(default_factory=set)
    # La versione salvata da cui parte il lavoro su ciascun modello: quella
    # dell'XML che la UI ha mandato col messaggio, poi l'ultima scritta dal
    # turno. Se c'e', una scrittura passa solo se l'ultima versione e' questa.
    # `None` = l'XML e' il diagramma iniziale di un modello senza versioni.
    base_version_by_model: dict[str, int | None] = field(default_factory=dict)


_turn_writes: contextvars.ContextVar[TurnWrites | None] = contextvars.ContextVar(
    "active_turn_writes", default=None
)


@contextmanager
def bind_turn_writes(base_versions: dict[str, int | None] | None = None) -> Iterator[TurnWrites]:
    """Apre il registro delle scritture BPMN del turno, con l'istante d'inizio.

    Args:
        base_versions: Per modello BPMN, la versione salvata da cui viene l'XML
            che la UI ha mandato. Senza, vale solo il controllo sull'istante.
    """
    writes = TurnWrites(
        started_at=datetime.now(UTC).isoformat(),
        base_version_by_model=dict(base_versions or {}),
    )
    token = _turn_writes.set(writes)
    try:
        yield writes
    finally:
        try:
            _turn_writes.reset(token)
        except ValueError:
            logger.warning(
                "turn writes reset skipped because LangGraph resumed in a different context"
            )


def active_turn_writes() -> TurnWrites | None:
    """Il registro del turno in corso, o `None` fuori da un agent run."""
    return _turn_writes.get()
