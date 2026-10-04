"""Cosa arriva al modello quando un tool fallisce.

Il `ToolNode` di LangGraph, di default, rilancia ogni eccezione che non sia un
errore di validazione degli argomenti: un tool che dice "Modello BPMN non
trovato" o "element_id obbligatorio per update_element" faceva cadere l'intero
turno, e il consulente vedeva un errore generico invece di una risposta.

Quei messaggi sono scritti per il modello: nei tool sono `ValueError` (63 su
63 `raise` dei toolset), e qui diventano l'esito della chiamata, cosi' il
modello corregge la richiesta o lo dice al consulente. Il budget del turno
(`agent_budget`) impedisce che riprovi all'infinito.

Restano fuori, e fermano il turno come prima, le `RuntimeError`: sono i
confini (`ScopeViolation`, `WriteNotAllowedInMode`, `WriteNeedsApproval`,
`OperationNotOpen`) e i guasti veri. Un confine non si negozia col modello.
"""

from __future__ import annotations

import logging

from backend.agents.run_context import BpmnVersionConflict

logger = logging.getLogger(__name__)


def report_tool_error(exc: ValueError) -> str:
    """Esito del tool per un `ValueError`: il messaggio, e cosa farne.

    LangGraph ricava dal tipo dell'argomento quali eccezioni gestire: solo i
    `ValueError` (e le sottoclassi, come le `ValidationError` di Pydantic)
    diventano un messaggio; il resto si propaga.
    """
    if isinstance(exc, BpmnVersionConflict):
        return f"Modifica non salvata: {exc}"
    # Un ValueError puo' anche essere un difetto del codice: resta nel log con
    # la traccia, anche se il turno prosegue.
    logger.warning("tool fallito, esito restituito al modello: %s", exc, exc_info=True)
    return (
        f"Il tool non e' andato a buon fine: {exc} "
        "Correggi la richiesta se puoi; altrimenti dillo al consulente con parole "
        "sue. Non ripetere la stessa chiamata con gli stessi argomenti."
    )
