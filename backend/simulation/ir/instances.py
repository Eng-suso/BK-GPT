"""Le attivita' multi-istanza con un numero fisso (SIM-11f) compilate in copie.

Prosimos 2.1 esegue ogni attivita' una volta per caso: "firma ognuno dei 3
documenti" diventava una firma sola. Con un numero fisso di istanze
l'attivita' diventa, nel BPMN del motore:

- in sequenza: l'attivita' e le sue copie una dopo l'altra;
- in parallelo: una divisione parallela verso l'attivita' e le sue copie, poi
  un'unione. Ogni istanza prende la sua risorsa, come nella realta'.

Le copie hanno lo stesso nome e le stesse risorse e durate: nel log
l'attivita' resta una sola e i KPI per attivita' contano tutte le istanze. Le
copie seguono l'originale nel BPMN, cosi' il nome si riconduce all'id
originale (vince la prima occorrenza), come per le varianti di durata.

Un'attivita' con durate per categoria, salti, rilavorazioni o un'escalation
resta eseguita una volta: le due compilazioni insieme non sono definite.

Funzioni pure: il modello e il BPMN in ingresso non cambiano.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring as safe_fromstring

from backend.simulation.ir.model import Activity, SimulationModel

_BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def expandable(model: SimulationModel) -> list[Activity]:
    """Le attivita' con piu' istanze che si possono compilare in copie."""
    escalated = {gateway.escalation.activity_id for gateway in model.gateways if gateway.escalation}
    return [
        activity for activity in model.activities
        if activity.instances > 1 and activity.duration_by is None and activity.skip is None
        and activity.rework is None and activity.element_id not in escalated
    ]


def expand_instances(bpmn_xml: str, model: SimulationModel) -> tuple[str, SimulationModel]:
    """Il BPMN e il modello con le istanze al posto delle multi-istanze. Senza, gli stessi oggetti."""
    targets = {activity.element_id for activity in expandable(model)}
    if not targets:
        return bpmn_xml, model

    ET.register_namespace("", _BPMN)
    root = safe_fromstring(bpmn_xml)
    taken = {element.get("id") for element in root.iter() if element.get("id")}
    activities: list[Activity] = []
    for activity in model.activities:
        if activity.element_id not in targets:
            activities.append(activity)
            continue
        copies = _expand(root, activity, taken)
        activities.append(activity.model_copy(update={"instances": 1}))
        activities.extend(
            activity.model_copy(update={"element_id": copy_id, "instances": 1}) for copy_id in copies
        )
    updates = list(model.attribute_updates) + [
        update.model_copy(update={"element_id": f"{update.element_id}__mi_{index}"})
        for update in model.attribute_updates
        if update.element_id in targets
        for index in range(2, next(a.instances for a in model.activities if a.element_id == update.element_id) + 1)
    ]
    expanded = model.model_copy(update={"activities": tuple(activities), "attribute_updates": tuple(updates)})
    xml = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml, SimulationModel.model_validate(expanded.model_dump())


def _expand(root: ET.Element, activity: Activity, taken: set[str]) -> list[str]:
    """Riscrive il BPMN intorno al task e restituisce gli id delle copie."""
    process, task = _find(root, activity.element_id)
    element_id = activity.element_id
    copy_ids = [_claim(taken, f"{element_id}__mi_{index}") for index in range(2, activity.instances + 1)]
    elements = []
    for copy_id in copy_ids:
        element = copy.deepcopy(task)
        element.set("id", copy_id)
        for ref in [child for child in element if child.tag in {f"{{{_BPMN}}}incoming", f"{{{_BPMN}}}outgoing"}]:
            element.remove(ref)
        elements.append(element)
    previous = task
    for element in elements:
        process.insert(list(process).index(previous) + 1, element)
        previous = element

    flows = process.findall(f"{{{_BPMN}}}sequenceFlow")
    def flow(source: str, target: str) -> None:
        process.append(ET.Element(f"{{{_BPMN}}}sequenceFlow", {
            "id": _claim(taken, f"{source}__to__{target}"), "sourceRef": source, "targetRef": target,
        }))

    if activity.sequential_instances:
        # Chi usciva dall'attivita' ora esce dall'ultima istanza.
        for f in flows:
            if f.get("sourceRef") == element_id:
                f.set("sourceRef", copy_ids[-1])
        for source, target in zip([element_id, *copy_ids], copy_ids, strict=False):
            flow(source, target)
        return copy_ids

    split, join = _claim(taken, f"{element_id}__mi_split"), _claim(taken, f"{element_id}__mi_join")
    for f in flows:
        if f.get("targetRef") == element_id:
            f.set("targetRef", split)
        if f.get("sourceRef") == element_id:
            f.set("sourceRef", join)
    process.insert(list(process).index(task), ET.Element(f"{{{_BPMN}}}parallelGateway", {"id": split}))
    process.insert(list(process).index(previous) + 1, ET.Element(f"{{{_BPMN}}}parallelGateway", {"id": join}))
    for target in [element_id, *copy_ids]:
        flow(split, target)
        flow(target, join)
    return copy_ids


def _claim(taken: set[str], element_id: str) -> str:
    if element_id in taken:
        raise ValueError(f"il BPMN contiene già l'id {element_id}: rinomina quell'elemento per simulare le istanze multiple")
    taken.add(element_id)
    return element_id


def _find(root: ET.Element, element_id: str) -> tuple[ET.Element, ET.Element]:
    for process in root.iter(f"{{{_BPMN}}}process"):
        for child in process:
            if child.get("id") == element_id:
                return process, child
    raise ValueError(f"l'attività {element_id} non è nel BPMN")
