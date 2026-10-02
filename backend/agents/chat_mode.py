"""Runtime enforcement della modalita di chat (plan / edit / agent).

Nel prodotto il consulente sceglie l'*autonomia* - Auto, Chiedi approvazione,
Manuale - e il runtime la traduce nelle modalita' interne qui sotto
(`schemas/chat.py: AUTONOMY_TO_MODE`): agent, plan, conversation. I nomi interni
restano perche' su di loro sono costruiti il router e i test; quello che il
consulente vede sono i tre livelli.

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


class WriteNeedsApproval(RuntimeError):
    """Una scrittura permessa, ma solo dopo che il consulente l'ha approvata."""


# Le scritture dell'agente sui record del workspace: clienti, progetti, primo
# processo. Non toccano il modello BPMN, ma restano scritture: in Manuale non
# partono, in Chiedi approvazione partono dopo il "si'" del consulente.
WORKSPACE_RECORD_WRITE = "create_workspace_records"

_approved_write: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "approved_workspace_write", default=False
)


# Le scritture che ogni modalita' rifiuta. Plan non tocca il modello di processo:
# preparare e riscrivere la review *e'* il lavoro del plan mode, quindi quelle
# restano permesse. Edit applica modifiche locali ma non approva una review -
# approvare genera un modello intero da un piano, che non e' una modifica locale.
FORBIDDEN_WRITES: dict[str, frozenset[str]] = {
    "conversation": frozenset(
        {
            "prepare_bpmn_review",
            "revise_bpmn_review",
            "update_bpmn_review_brief",
            "answer_bpmn_review_question",
            "update_bpmn_model",
            "create_bpmn_version",
            "restore_bpmn_version",
            "approve_bpmn_review",
            WORKSPACE_RECORD_WRITE,
        }
    ),
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

# Le scritture che una modalita' permette solo dopo un'approvazione esplicita,
# legata al thread (`backend.memory.pending_actions`). In Chiedi approvazione il
# modello BPMN cambia dal bottone Approva della review; i record del workspace
# da qui.
APPROVAL_WRITES: dict[str, frozenset[str]] = {
    "plan": frozenset({WORKSPACE_RECORD_WRITE}),
    "edit": frozenset({WORKSPACE_RECORD_WRITE}),
}


@contextmanager
def bind_approved_write() -> Iterator[None]:
    """Esegue una scrittura che il consulente ha appena approvato."""
    token = _approved_write.set(True)
    try:
        yield
    finally:
        _approved_write.reset(token)

def narrowest_mode_allowing(operation: str) -> str | None:
    """La modalita' meno ampia in cui questa scrittura passa.

    Il rifiuto nominava sempre tre modalita' insieme, e chi lo leggeva ne
    sceglieva una a caso - di solito la piu' larga: per scrivere sul piano veniva
    attivata la modalita' che serve a disegnare. Il piano e il disegno sono due
    artefatti e costano due permessi diversi, e il permesso piu' basso che basta
    e' quello da chiedere.

    La risposta si ricava da `FORBIDDEN_WRITES`, che e' il gate vero. Una tabella
    scritta a mano accanto al gate sarebbe una seconda verita' sullo stesso
    fatto, e le due divergerebbero al primo permesso che cambia.

    Args:
        operation: L'operazione rifiutata, non affidabile.

    Returns:
        L'etichetta di prodotto della modalita', o `None` se nessuna la permette.
    """
    from backend.graphs.routing_contracts import MODE_LADDER, mode_label

    for mode in MODE_LADDER:
        if operation not in FORBIDDEN_WRITES.get(mode, frozenset()):
            return mode_label(mode)
    return None


MODE_REFUSALS: dict[str, str] = {
    "conversation": (
        "Questa chat e' in autonomia Manuale: DeliR propone e spiega, ma non "
        "scrive niente - ne' record del workspace ne' artefatti BPMN. Per farlo "
        "fare a DeliR serve Chiedi approvazione o Auto."
    ),
    "plan": (
        "Questa chat e' in autonomia Chiedi approvazione: posso preparare e "
        "correggere il piano di processo, ma il canvas cambia solo quando il "
        "consulente approva la review. Per modifiche dirette serve Auto."
    ),
    "edit": (
        "Questa chat e' in modalita' Modifica: posso applicare cambiamenti "
        "puntuali al canvas, ma non approvare una review e rigenerare il "
        "modello. Passa ad Agente per farlo."
    ),
}


@contextmanager
def bind_active_mode(mode: ChatMode | None) -> Iterator[None]:
    """
    Temporarily binds a chat mode to the current execution context.
    
    Args:
        mode (ChatMode | None): Untrusted mode value to bind; `None` uses the
            default chat mode.
    
    Yields:
        None: Control while the mode is active.
    
    The previous mode is restored when the context exits. This function changes
    context-local state only and performs no persistence. If restoration cannot
    occur because execution resumed in a different context, the failure is
    logged and not raised.
    """
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
    """Get the chat mode active in the current execution context.
    
    Returns:
        ChatMode | None: The active chat mode, or `None` when no mode is bound.
    """
    return _active_mode.get()


def assert_write_allowed(operation: str) -> None:
    """
    Ensure the requested write operation is permitted in the active chat mode.
    
    Args:
        operation (str): Untrusted operation identifier to check against the active mode's restrictions.
    
    Raises:
        WriteNotAllowedInMode: If the operation is forbidden in the active chat mode.
    
    This function has no effect outside an active agent run and does not persist changes.
    """
    mode = _active_mode.get()
    if mode is None:
        return

    if operation in APPROVAL_WRITES.get(mode, frozenset()) and not _approved_write.get():
        raise WriteNeedsApproval(
            "In Chiedi approvazione questa scrittura parte solo dopo il si' del consulente."
        )

    if operation in FORBIDDEN_WRITES.get(mode, frozenset()):
        message = MODE_REFUSALS.get(
            mode, f"Operazione '{operation}' non consentita in modalita' {mode}."
        )
        required = narrowest_mode_allowing(operation)
        if required:
            message += (
                f" Per questa operazione basta la modalita' {required}: non serve "
                "una modalita' piu' ampia."
            )
        raise WriteNotAllowedInMode(message)
