"""Salti e rilavorazioni (SIM-35) compilati nel BPMN del motore.

Prosimos 2.1 non conosce ne' un'attivita' facoltativa ne' un ritorno indietro
con un tetto (spike G1). Sa pero' instradare per regola e aggiornare attributi
dell'evento, e con quelli si scrivono entrambi:

    salto:          -> [salto?] -> attivita' -> [unione] ->
                               \\-------------->/

    rilavorazione:  -> [ritorno] -> da_rifare ... attivita' -> [di nuovo?] -> avanti
                          ^-------------------------------------/

Il ritorno e' una decisione per regola su un contatore che l'attivita' aggiorna
a ogni completamento: oltre ``max_repeats`` resta solo il ramo in avanti.
Due comportamenti del motore, fissati da ``test_simulation_ir_engine.py``:

- un attributo del caso non si puo' aggiornare da un evento, quindi il
  contatore e' solo un attributo d'evento, senza valore iniziale;
- al primo completamento ``contatore + 1`` vale 0 (il nome non esiste ancora e
  il motore valuta l'espressione a zero): dopo k completamenti vale k - 1.

Con piu' rami veri il motore sceglie fra quelli con le loro probabilita'
riscalate: e' cosi' che "il 30% dei casi che soddisfano la regola" diventa una
regola sul ramo e una regola sempre vera sull'altro.

Funzioni pure: il modello e il BPMN in ingresso non cambiano.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring as safe_fromstring

from backend.simulation.ir.escalations import timer_split_id
from backend.simulation.ir.model import (
    Activity,
    AttributeUpdate,
    Branch,
    Condition,
    Gateway,
    Rule,
    SimulationModel,
)

_BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"

# Da un'attivita' si torna indietro solo lungo un percorso in sequenza: passare
# da un parallelo o da un inclusivo lascerebbe token orfani nel motore.
_BACKWARD_OK = frozenset({"task", "exclusiveGateway", "intermediateCatchEvent", "eventBasedGateway"})


def expand_flow_rules(bpmn_xml: str, model: SimulationModel) -> tuple[str, SimulationModel]:
    """Il BPMN e il modello con salti e rilavorazioni scritti come decisioni.

    Senza salti ne' rilavorazioni restituisce gli stessi oggetti.
    """
    if not any(activity.skip or activity.rework for activity in model.activities):
        return bpmn_xml, model

    ET.register_namespace("", _BPMN)
    # Il BPMN viene dal consulente: letto senza entita' esterne ne' espansioni.
    root = safe_fromstring(bpmn_xml)
    taken = {element.get("id") for element in root.iter() if element.get("id")}
    attributes = {a.name for a in model.case_attributes} | {u.name for u in model.attribute_updates}
    gateways = list(model.gateways)
    updates = list(model.attribute_updates)

    for activity in model.activities:
        if activity.skip is not None:
            gateways.append(_skip(root, activity, taken))
    for index, activity in enumerate(a for a in model.activities if a.rework is not None):
        counter = f"delir_rework_{index + 1}"
        if counter in attributes:
            raise ValueError(f"l'attributo {counter} è riservato alle rilavorazioni: rinominalo")
        gateway, update = _rework(root, activity, counter, taken)
        gateways.append(gateway)
        updates.append(update)

    expanded = model.model_copy(update={
        "activities": tuple(a.model_copy(update={"skip": None, "rework": None}) for a in model.activities),
        "gateways": tuple(gateways),
        "attribute_updates": tuple(updates),
    })
    xml = ET.tostring(root, encoding="unicode")
    # Rivalidato: un id generato che collide con uno esistente deve fallire qui, non nel motore.
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml, SimulationModel.model_validate(expanded.model_dump())


def _skip(root: ET.Element, activity: Activity, taken: set[str]) -> Gateway:
    skip = activity.skip
    assert skip is not None
    process, task = _find(root, activity.element_id)
    outgoing = _single_outgoing(process, activity)
    split_id = _claim(taken, f"{activity.element_id}__skip_split")
    join_id = _claim(taken, f"{activity.element_id}__skip_join")
    entry = _entry(process, activity.element_id)
    for flow in _flows(process):
        if flow.get("targetRef") == entry:
            flow.set("targetRef", split_id)
    outgoing.set("sourceRef", join_id)

    process.insert(list(process).index(task), _gateway(split_id, task.get("name", "")))
    process.insert(list(process).index(task) + 1, _gateway(join_id))
    do_flow = _flow(process, taken, f"{split_id}__{activity.element_id}", split_id, entry)
    bypass = _flow(process, taken, f"{split_id}__bypass", split_id, join_id)
    _flow(process, taken, f"{activity.element_id}__{join_id}", activity.element_id, join_id)

    if skip.condition is None:
        branches = (
            Branch(flow_id=do_flow, probability=1 - skip.probability),
            Branch(flow_id=bypass, probability=skip.probability, provenance=skip.provenance),
        )
    else:
        branches = (
            Branch(flow_id=do_flow, probability=1 - skip.probability, condition=_always(skip.condition)),
            Branch(flow_id=bypass, probability=skip.probability, condition=skip.condition, provenance=skip.provenance),
        )
    return Gateway(element_id=split_id, branches=branches)


def _rework(root: ET.Element, activity: Activity, counter: str, taken: set[str]) -> tuple[Gateway, AttributeUpdate]:
    rework = activity.rework
    assert rework is not None
    process, task = _find(root, activity.element_id)
    _, target = _find(root, rework.back_to)
    _check_reachable_backwards(process, rework.back_to, activity)
    outgoing = _single_outgoing(process, activity)

    decision_id = _claim(taken, f"{activity.element_id}__rework")
    join_id = _claim(taken, f"{activity.element_id}__rework_join")
    entry = _entry(process, rework.back_to)
    for flow in _flows(process):
        if flow.get("targetRef") == entry:
            flow.set("targetRef", join_id)
    process.insert(list(process).index(target), _gateway(join_id))
    _flow(process, taken, f"{join_id}__{rework.back_to}", join_id, entry)

    process.insert(list(process).index(task) + 1, _gateway(decision_id, task.get("name", "")))
    outgoing.set("sourceRef", decision_id)
    _flow(process, taken, f"{activity.element_id}__{decision_id}", activity.element_id, decision_id)
    back = _flow(process, taken, f"{decision_id}__back", decision_id, join_id)

    # Dopo k completamenti il contatore vale k - 1: si torna indietro finche' k <= max_repeats.
    below_limit = Rule(attribute=counter, operator="<", value=float(rework.max_repeats))
    groups = rework.condition.any_of if rework.condition is not None else ((),)
    gateway = Gateway(element_id=decision_id, branches=(
        Branch(flow_id=outgoing.get("id", ""), probability=1 - rework.probability,
               condition=_always(Condition(any_of=((below_limit,),)))),
        Branch(flow_id=back, probability=rework.probability, provenance=rework.provenance,
               condition=Condition(any_of=tuple((*group, below_limit) for group in groups))),
    ))
    return gateway, AttributeUpdate(element_id=activity.element_id, name=counter, expression=f"{counter} + 1")


def _always(condition: Condition) -> Condition:
    """Una regola vera per ogni caso che ha l'attributo della prima regola di ``condition``.

    Il motore confronta come numero quando il valore lo e', altrimenti come testo:
    la coppia di operatori deve essere complementare in entrambi i casi.
    """
    rule = condition.any_of[0][0]
    pair = (">=", "<") if _numeric(rule.value) else ("=", "!=")
    return Condition(any_of=tuple(
        (Rule(attribute=rule.attribute, operator=operator, value=rule.value),) for operator in pair
    ))


def _numeric(value: str | float) -> bool:
    if isinstance(value, float):
        return True
    try:
        float(value)
    except ValueError:
        return False
    return True


def _check_reachable_backwards(process: ET.Element, target_id: str, activity: Activity) -> None:
    if target_id == activity.element_id:
        return
    kinds = {child.get("id"): _local(child.tag) for child in process}
    incoming: dict[str, list[str]] = {}
    for flow in _flows(process):
        incoming.setdefault(flow.get("targetRef", ""), []).append(flow.get("sourceRef", ""))
    pending, seen = list(incoming.get(activity.element_id, [])), set()
    while pending:
        node = pending.pop()
        if node == target_id:
            return
        if node in seen or kinds.get(node) not in _BACKWARD_OK:
            continue
        seen.add(node)
        pending.extend(incoming.get(node, []))
    label = activity.name or activity.element_id
    raise ValueError(
        f"«{label}»: la rilavorazione può tornare solo a un'attività che la precede, "
        "senza passare da rami paralleli o inclusivi."
    )


def _entry(process: ET.Element, activity_id: str) -> str:
    """Da dove entra un caso nell'attivita': la scelta del timer, se ha un'escalation.

    Chi salta l'attivita' non scade, e chi torna a rifarla puo' scadere di nuovo.
    """
    split = timer_split_id(activity_id)
    return split if any(child.get("id") == split for child in process) else activity_id


def _single_outgoing(process: ET.Element, activity: Activity) -> ET.Element:
    outgoing = [flow for flow in _flows(process) if flow.get("sourceRef") == activity.element_id]
    if len(outgoing) != 1:
        label = activity.name or activity.element_id
        raise ValueError(f"«{label}»: salto e rilavorazione richiedono un solo flusso in uscita dall'attività.")
    return outgoing[0]


def _flows(process: ET.Element) -> list[ET.Element]:
    return process.findall(f"{{{_BPMN}}}sequenceFlow")


def _flow(process: ET.Element, taken: set[str], flow_id: str, source: str, target: str) -> str:
    process.append(ET.Element(f"{{{_BPMN}}}sequenceFlow", {
        "id": _claim(taken, flow_id), "sourceRef": source, "targetRef": target,
    }))
    return flow_id


def _gateway(element_id: str, name: str = "") -> ET.Element:
    attributes = {"id": element_id}
    if name:
        attributes["name"] = name
    return ET.Element(f"{{{_BPMN}}}exclusiveGateway", attributes)


def _claim(taken: set[str], element_id: str) -> str:
    """Un id generato non deve esistere gia' nel BPMN: altrimenti si fallisce con il motivo."""
    if element_id in taken:
        raise ValueError(f"il BPMN contiene già l'id {element_id}: rinomina quell'elemento per usare salti e rilavorazioni")
    taken.add(element_id)
    return element_id


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(root: ET.Element, element_id: str) -> tuple[ET.Element, ET.Element]:
    for process in root.iter(f"{{{_BPMN}}}process"):
        for child in process:
            if child.get("id") == element_id:
                return process, child
    raise ValueError(f"l'attività {element_id} non è nel BPMN")
