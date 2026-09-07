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
