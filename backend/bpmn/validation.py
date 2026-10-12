"""Structural validation of a `BPMNSemanticModel`.

Cheap, deterministic well-formedness checks (dangling refs, gateway arity,
dead-end nodes, boundary-event attachment). Control-flow soundness lives in
`backend.bpmn.soundness`.
"""

from __future__ import annotations

from backend.bpmn.models import ACTIVITY_NODE_TYPES, BPMNSemanticModel
from backend.bpmn.soundness import analyze_control_flow


def validate_bpmn_semantic_model(model: BPMNSemanticModel) -> list[str]:
    """Validate the structural integrity of a BPMN semantic model.

    Performs well-formedness checks including duplicate IDs, dangling references,
    gateway arity, boundary event attachment, and control-flow soundness.

    Args:
        model: The BPMNSemanticModel to validate.

    Returns:
        A list of warning messages describing structural issues found.
    """
    warnings: list[str] = []
    node_ids = {node.id for node in model.flowNodes}
    flow_ids = {flow.id for flow in model.sequenceFlows}
    data_ids = {item.id for item in model.dataObjects} | {item.id for item in model.dataStores}
    annotation_ids = {item.id for item in model.textAnnotations}
    semantic_element_ids = node_ids | data_ids | annotation_ids
    if len(node_ids) != len(model.flowNodes) or len(flow_ids) != len(model.sequenceFlows):
        warnings.append("Sono presenti ID duplicati nel modello semantico.")
    # Missing start / end events are reported by analyze_control_flow below.

    outgoing_by_node: dict[str, list] = {node.id: [] for node in model.flowNodes}
    incoming_by_node: dict[str, list] = {node.id: [] for node in model.flowNodes}
    for flow in model.sequenceFlows:
        if flow.sourceRef not in node_ids or flow.targetRef not in node_ids:
            warnings.append(f"Sequence flow {flow.id} punta a un nodo inesistente.")
            continue
        outgoing_by_node[flow.sourceRef].append(flow)
        incoming_by_node[flow.targetRef].append(flow)

    for association in model.associations:
        if association.sourceRef not in semantic_element_ids or association.targetRef not in semantic_element_ids:
            warnings.append(f"Association {association.id} punta a un elemento inesistente.")

    node_type_by_id = {node.id: node.type for node in model.flowNodes}
    compensation_handlers = {node.id for node in model.flowNodes if node.isForCompensation}
    associated = {(item.sourceRef, item.targetRef) for item in model.associations}
    for node in model.flowNodes:
        # An event sub-process runs on its trigger and a compensation activity
        # from its boundary event: neither sits on the sequence flow (OMG 10.3.6, 10.6).
        if node.triggeredByEvent or node.isForCompensation:
            if incoming_by_node.get(node.id) or outgoing_by_node.get(node.id):
                warnings.append(f"Attivita {node.name} non puo' avere frecce di sequenza: parte dal suo evento.")
            if node.isForCompensation and not any(target == node.id for _, target in associated):
                warnings.append(f"Attivita di compensazione {node.name} senza evento di compensazione collegato.")
            continue
        if node.type == "startEvent" and not node.isInterrupting:
            warnings.append(f"Evento iniziale {node.name} non interrompente fuori da un event sub-process.")
        if node.type == "boundaryEvent" and node.eventDefinition == "compensation":
            if node_type_by_id.get(node.attachedToRef or "") not in ACTIVITY_NODE_TYPES:
                warnings.append(f"Boundary event {node.name} non agganciato a un'attivita valida.")
            if outgoing_by_node.get(node.id):
                warnings.append(f"Boundary di compensazione {node.name} non puo' avere frecce di sequenza.")
            if not any(source == node.id and target in compensation_handlers for source, target in associated):
                warnings.append(f"Boundary di compensazione {node.name} senza attivita di compensazione associata.")
            continue
        if (
            node.type in {"exclusiveGateway", "inclusiveGateway", "complexGateway", "parallelGateway", "eventBasedGateway"}
            and len(incoming_by_node.get(node.id, [])) <= 1
            and len(outgoing_by_node.get(node.id, [])) < 2
        ):
            warnings.append(f"Gateway {node.name} senza almeno due uscite.")
        if node.type == "boundaryEvent":
            if node_type_by_id.get(node.attachedToRef or "") not in ACTIVITY_NODE_TYPES:
                warnings.append(f"Boundary event {node.name} non agganciato a un'attivita valida.")
            elif node.eventDefinition == "cancel" and node_type_by_id.get(node.attachedToRef or "") != "transaction":
                warnings.append(f"Boundary event di annullamento {node.name} valido solo su una transazione.")
            if not outgoing_by_node.get(node.id):
                warnings.append(f"Boundary event {node.name} senza gestione collegata.")
            if incoming_by_node.get(node.id):
                warnings.append(f"Boundary event {node.name} non puo' avere frecce in ingresso.")
            continue
        if node.type == "startEvent" and incoming_by_node.get(node.id):
            warnings.append(f"Evento iniziale {node.name} con una freccia in ingresso.")
        instantiating = node.type == "eventBasedGateway" and node.instantiate
        # A link catch continues the flow its throw left off: no incoming flow,
        # and the throw has no outgoing one (OMG BPMN 2.0, 10.4.5).
        link_catch = node.type == "intermediateCatchEvent" and node.eventDefinition == "link"
        link_throw = node.type == "intermediateThrowEvent" and node.eventDefinition == "link"
        if link_catch and incoming_by_node.get(node.id):
            warnings.append(f"Link {node.name} in attesa non puo' avere frecce in ingresso.")
        if link_throw and outgoing_by_node.get(node.id):
            warnings.append(f"Link {node.name} lanciato non puo' avere frecce in uscita.")
        if node.type != "startEvent" and not instantiating and not link_catch and not incoming_by_node.get(node.id):
            warnings.append(f"Nodo {node.name} senza ingresso.")
        if node.type == "endEvent" and outgoing_by_node.get(node.id):
            warnings.append(f"Evento finale {node.name} con una freccia in uscita.")
        if node.type != "endEvent" and not link_throw and not outgoing_by_node.get(node.id):
            warnings.append(f"Nodo {node.name} senza uscita.")
        if node.eventDefinition == "cancel" and node.type == "endEvent":
            warnings.append(f"Fine con annullamento {node.name} valida solo dentro una transazione.")

    warnings.extend(analyze_control_flow(model).messages())
    return warnings
