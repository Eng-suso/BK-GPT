"""Le durate condizionali (SIM-32) compilate in varianti dell'attivita'.

Prosimos 2.1 non sa far dipendere una durata da un attributo del caso (spike G1).
Sa pero' instradare per regola. Un'attivita' con ``duration_by`` diventa:

    -> [divisione] -> attivita' originale (casi con altre categorie)  -> [unione] ->
                   -> copia per "premium" (durata premium)            ->
                   -> copia per "standard" (durata standard)          ->

Le copie hanno lo stesso nome dell'originale e le stesse risorse: nel log
l'attivita' resta una sola, e i KPI per attivita' non si spezzano. Le copie
seguono l'originale nel BPMN, cosi' il nome si riconduce all'id originale
(``activity_name_to_element_id``: vince la prima occorrenza). I rami sono
esclusivi per costruzione: "tipo = premium" verso la sua copia, "tipo != ogni
categoria elencata" verso l'originale.

Funzioni pure: il modello e il BPMN in ingresso non cambiano.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring as safe_fromstring

from backend.simulation.ir.model import (
    Activity,
    Assignment,
    Branch,
    Condition,
    DurationByAttribute,
    Gateway,
    Rule,
    SimulationModel,
)

_BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def check_duration_rules(model: SimulationModel) -> None:
    """Ogni durata condizionale usa un attributo a categorie del caso, con categorie che esistono."""
    attributes = {attribute.name: attribute for attribute in model.case_attributes}
    for activity in model.activities:
        rule = activity.duration_by
        if rule is None:
            continue
        attribute = attributes.get(rule.attribute)
        label = activity.name or activity.element_id
        if attribute is None:
            raise ValueError(f"«{label}»: la durata dipende da «{rule.attribute}», che il caso non ha.")
        if attribute.options is None:
            raise ValueError(f"«{label}»: la durata può dipendere solo da un attributo a categorie.")
        known = {option.value for option in attribute.options}
        missing = sorted({variant.value for variant in rule.variants} - known)
        if missing:
            raise ValueError(f"«{label}»: categorie che «{rule.attribute}» non ha: {', '.join(missing)}.")


def expand_duration_variants(bpmn_xml: str, model: SimulationModel) -> tuple[str, SimulationModel]:
    """Il BPMN e il modello con le varianti al posto delle durate condizionali.

    Senza durate condizionali restituisce gli stessi oggetti.
    """
    conditional = [activity for activity in model.activities if activity.duration_by is not None]
    if not conditional:
        return bpmn_xml, model
    check_duration_rules(model)

    ET.register_namespace("", _BPMN)
    # Il BPMN viene dal consulente: letto senza entita' esterne ne' espansioni.
    root = safe_fromstring(bpmn_xml)
    taken = {element.get("id") for element in root.iter() if element.get("id")}
    activities: list[Activity] = []
    gateways = list(model.gateways)
    for activity in model.activities:
        if activity.duration_by is None:
            activities.append(activity)
            continue
        copies = _expand_activity(root, activity, taken)
        activities.append(activity.model_copy(update={"duration_by": None}))
        activities.extend(copies)
        gateways.append(_split_gateway(activity, copies))

    expanded = model.model_copy(update={"activities": tuple(activities), "gateways": tuple(gateways)})
    xml = ET.tostring(root, encoding="unicode")
    # Rivalidato: un id generato che collide con uno esistente deve fallire qui, non nel motore.
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml, SimulationModel.model_validate(expanded.model_dump())


def _ids(activity: Activity) -> tuple[str, str]:
    return f"{activity.element_id}__dur_split", f"{activity.element_id}__dur_join"


def _variant_id(activity: Activity, index: int) -> str:
    return f"{activity.element_id}__dur_{index + 1}"


def _claim(taken: set[str], element_id: str) -> str:
    """Un id generato non deve esistere gia' nel BPMN: altrimenti si fallisce con il motivo."""
    if element_id in taken:
        raise ValueError(f"il BPMN contiene già l'id {element_id}: rinomina quell'elemento per usare le durate per categoria")
    taken.add(element_id)
    return element_id


def _expand_activity(root: ET.Element, activity: Activity, taken: set[str]) -> list[Activity]:
    """Riscrive il BPMN intorno al task e restituisce le attivita' copia."""
    process, task = _find(root, activity.element_id)
    split_id, join_id = (_claim(taken, element_id) for element_id in _ids(activity))
    for flow in process.findall(f"{{{_BPMN}}}sequenceFlow"):
        if flow.get("targetRef") == activity.element_id:
            flow.set("targetRef", split_id)
        if flow.get("sourceRef") == activity.element_id:
            flow.set("sourceRef", join_id)

    split = ET.Element(f"{{{_BPMN}}}exclusiveGateway", {"id": split_id, "name": task.get("name", "")})
    process.insert(list(process).index(task), split)
    new_tasks = []
    copies: list[Activity] = []
    rule = _rule(activity)
    for index, variant in enumerate(rule.variants):
        element = copy.deepcopy(task)
        element.set("id", _claim(taken, _variant_id(activity, index)))
        new_tasks.append(element)
        copies.append(Activity(
            element_id=_variant_id(activity, index),
            name=activity.name,
            assignments=tuple(
                Assignment(resource_id=a.resource_id, duration=variant.duration, provenance=variant.provenance or a.provenance)
                for a in activity.assignments
            ),
        ))
    # Le copie subito dopo l'originale, poi l'unione: il nome nel log si riconduce
    # all'id originale (vince la prima occorrenza).
    previous = task
    for element in [*new_tasks, ET.Element(f"{{{_BPMN}}}exclusiveGateway", {"id": join_id})]:
        process.insert(list(process).index(previous) + 1, element)
        previous = element

    targets = [activity.element_id, *(c.element_id for c in copies)]
    for target in targets:
        process.append(ET.Element(f"{{{_BPMN}}}sequenceFlow", {"id": _claim(taken, f"{split_id}__{target}"), "sourceRef": split_id, "targetRef": target}))
        process.append(ET.Element(f"{{{_BPMN}}}sequenceFlow", {"id": _claim(taken, f"{target}__{join_id}"), "sourceRef": target, "targetRef": join_id}))
    return copies


def _rule(activity: Activity) -> DurationByAttribute:
    if activity.duration_by is None:
        raise ValueError(f"l'attività {activity.element_id} non ha durate condizionali")
    return activity.duration_by


def _split_gateway(activity: Activity, copies: list[Activity]) -> Gateway:
    rule = _rule(activity)
    split_id, _ = _ids(activity)
    share = 1 / (len(copies) + 1)
    others = Condition(any_of=(tuple(Rule(attribute=rule.attribute, operator="!=", value=v.value) for v in rule.variants),))
    return Gateway(
        element_id=split_id,
        branches=(
            Branch(flow_id=f"{split_id}__{activity.element_id}", probability=share, condition=others),
            *(
                Branch(flow_id=f"{split_id}__{copy_.element_id}", probability=share,
                       condition=Condition(any_of=((Rule(attribute=rule.attribute, operator="=", value=variant.value),),)))
                for copy_, variant in zip(copies, rule.variants, strict=True)
            ),
        ),
    )


def _find(root: ET.Element, element_id: str) -> tuple[ET.Element, ET.Element]:
    for process in root.iter(f"{{{_BPMN}}}process"):
        for child in process:
            if child.get("id") == element_id:
                return process, child
    raise ValueError(f"l'attività {element_id} non è nel BPMN")
