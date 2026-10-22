"""SIM-11c: i timer intermedi del BPMN come attese del caso.

Il normalizer lascia nel BPMN i timer intermedi con una durata fissa
(``bpmn_normalizer.timer_wait_ids``); il motore li esegue solo se lo scenario
dice quanto durano. Qui il modello riceve un'attesa per ognuno: quella che il
modello porta gia' (un run v2 puo' cambiarla), altrimenti la durata scritta nel
timer. Un'attesa su un elemento che il BPMN non ha e' un errore, come un'attivita'.

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
        given.get(wait.id) or Wait(element_id=wait.id, name=wait.name, duration=Fixed(value=wait.seconds), provenance=_FROM_BPMN)
        for wait in waits
    )
    if complete == model.waits:
        return model
    return SimulationModel.model_validate(model.model_copy(update={"waits": complete}).model_dump())
