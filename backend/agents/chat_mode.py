"""Runtime enforcement della modalita di chat (plan / edit / agent).

La modalita e' una scelta dell'utente, non del modello: dice quanta parte del
lavoro sta delegando in questo turno. Vincola due cose, in due punti diversi:

1. *Quali capability il router puo' proporre* - vedi `CapabilitySpec.modes` in
   `graphs/routing_contracts.py`. Un rifiuto per modalita' torna all'agente con
   la ragione, come ogni altro rifiuto del gate.
2. *Quali scritture possono partire* - questo modulo. Il prompt non basta: in
   plan mode il modello non deve poter cambiare il modello BPMN nemmeno se
   decide che sarebbe utile, quindi il divieto sta sulla scrittura, dove e'
   verificabile, non sull'istruzione.

Stessa forma di `scope_guard`: un ContextVar vincolato per la durata dello
stream. Fuori da un agent run (worker, UI REST, test) il guard e' un no-op -
il bottone "approva" della UI non passa da qui, e non deve.
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager

from backend.schemas.chat import DEFAULT_CHAT_MODE, ChatMode

logger = logging.getLogger(__name__)

_active_mode: contextvars.ContextVar[ChatMode | None] = contextvars.ContextVar(
    "active_chat_mode", default=None
)


class WriteNotAllowedInMode(RuntimeError):
    """Una scrittura vietata dalla modalita' scelta dall'utente per questo turno."""


# Le scritture che ogni modalita' rifiuta. Plan non tocca il modello di processo:
# preparare e riscrivere la review *e'* il lavoro del plan mode, quindi quelle
# restano permesse. Edit applica modifiche locali ma non approva una review -
# approvare genera un modello intero da un piano, che non e' una modifica locale.
FORBIDDEN_WRITES: dict[str, frozenset[str]] = {
    "plan": frozenset(
        {
            "update_bpmn_model",
            "create_bpmn_version",
            "restore_bpmn_version",
            "approve_bpmn_review",
        }
    ),
    "edit": frozenset({"approve_bpmn_review"}),
    "agent": frozenset(),
}

MODE_REFUSALS: dict[str, str] = {
    "plan": (
        "Questa chat e' in modalita' Piano: posso preparare, correggere e "
        "spiegare il piano di processo, ma non modificare il canvas. "
        "Passa a Modifica o Agente per applicarlo."
    ),
    "edit": (
        "Questa chat e' in modalita' Modifica: posso applicare cambiamenti "
        "puntuali al canvas, ma non approvare una review e rigenerare il "
        "modello. Passa ad Agente per farlo."
    ),
}


@contextmanager
def bind_active_mode(mode: ChatMode | None) -> Iterator[None]:
    token = _active_mode.set(mode or DEFAULT_CHAT_MODE)
    try:
        yield
    finally:
        try:
            _active_mode.reset(token)
        except ValueError:
            logger.warning(
                "active mode reset skipped because LangGraph resumed in a different context"
            )


def active_mode() -> ChatMode | None:
    return _active_mode.get()


def assert_write_allowed(operation: str) -> None:
    """Solleva se `operation` e' vietata dalla modalita' del run corrente.

    No-op fuori da un agent run: worker, cutover, test e le azioni diverse che
    l'utente compie dalla UI non passano per una modalita' di chat.
    """
    mode = _active_mode.get()
    if mode is None:
        return

    if operation in FORBIDDEN_WRITES.get(mode, frozenset()):
        raise WriteNotAllowedInMode(
            MODE_REFUSALS.get(mode, f"Operazione '{operation}' non consentita in modalita' {mode}.")
        )
