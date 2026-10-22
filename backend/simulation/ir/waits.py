"""SIM-11c/d: gli eventi intermedi del BPMN come attese del caso.

Il normalizer lascia nel BPMN i timer intermedi con una durata fissa e i
messaggi, segnali e condizioni (``bpmn_normalizer.wait_event_ids``); il motore
li esegue solo se lo scenario dice quanto durano. Qui il modello riceve
un'attesa per ognuno: quella che il modello porta gia' (impostata nel pannello,
o cambiata da un run v2), altrimenti la durata scritta nel timer, o nessuna
attesa per un messaggio. Un'attesa su un elemento che il BPMN non ha e' un errore, come un'attivita'.

Funzioni pure: il modello in ingresso non cambia.
"""

from __future__ import annotations

from backend.simulation.ir.model import Fixed, Provenance, SimulationModel, Wait
from backend.simulation.models import BpmnWait

_FROM_BPMN = Provenance(origin="declared", note="Durata scritta nel timer del BPMN")


def with_bpmn_waits(model: SimulationModel, waits: list[BpmnWait]) -> SimulationModel:
    known = {wait.id: wait for wait in waits}
    unknown = sorted(wait.element_id for wait in model.waits if wait.element_id not in known)
    if unknown:
        raise ValueError(f"Attesa su un elemento che il BPMN non ha come timer con durata: {', '.join(unknown)}.")
    given = {wait.element_id: wait for wait in model.waits}
    complete = tuple(
        given[wait.id].model_copy(update={"name": wait.name, "kind": wait.kind}) if wait.id in given else _from_bpmn(wait)
        for wait in waits
    )
    if complete == model.waits:
        return model
    return SimulationModel.model_validate(model.model_copy(update={"waits": complete}).model_dump())


def _from_bpmn(wait: BpmnWait) -> Wait:
    """Un timer ha la sua durata; un messaggio o un segnale senza attesa impostata non aspetta."""
    if wait.seconds is None:
        return Wait(element_id=wait.id, name=wait.name, kind=wait.kind)
    return Wait(element_id=wait.id, name=wait.name, kind=wait.kind, duration=Fixed(value=wait.seconds), provenance=_FROM_BPMN)
