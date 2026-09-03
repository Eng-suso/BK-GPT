"""Structural validation of a `BPMNSemanticModel`.

Cheap, deterministic well-formedness checks (dangling refs, gateway arity,
dead-end nodes, boundary-event attachment). Control-flow soundness lives in
`backend.bpmn.soundness`.
"""

from __future__ import annotations

from backend.bpmn.models import ACTIVITY_NODE_TYPES, BPMNSemanticModel
from backend.bpmn.soundness import analyze_control_flow


def validate_bpmn_semantic_model(model: BPMNSemanticModel) -> list[str]:
    warnings: list[str] = []
    node_ids = {node.id for node in model.flowNodes}
    flow_ids = {flow.id for flow in model.sequenceFlows}
    data_ids = {item.id for item in model.dataObjects}
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
    for node in model.flowNodes:
        if (
            node.type in {"exclusiveGateway", "inclusiveGateway", "eventBasedGateway"}
            and len(incoming_by_node.get(node.id, [])) <= 1
            and len(outgoing_by_node.get(node.id, [])) < 2
        ):
            warnings.append(f"Gateway {node.name} senza almeno due uscite.")
        if node.type == "boundaryEvent":
            if node_type_by_id.get(node.attachedToRef or "") not in ACTIVITY_NODE_TYPES:
                warnings.append(f"Boundary event {node.name} non agganciato a un'attivita valida.")
            if not outgoing_by_node.get(node.id):
                warnings.append(f"Boundary event {node.name} senza gestione collegata.")
            if incoming_by_node.get(node.id):
                warnings.append(f"Boundary event {node.name} non puo' avere frecce in ingresso.")
            continue
        if node.type == "startEvent" and incoming_by_node.get(node.id):
            warnings.append(f"Evento iniziale {node.name} con una freccia in ingresso.")
        if node.type != "startEvent" and not incoming_by_node.get(node.id):
            warnings.append(f"Nodo {node.name} senza ingresso.")
        if node.type == "endEvent" and outgoing_by_node.get(node.id):
            warnings.append(f"Evento finale {node.name} con una freccia in uscita.")
        if node.type != "endEvent" and not outgoing_by_node.get(node.id):
            warnings.append(f"Nodo {node.name} senza uscita.")

    warnings.extend(analyze_control_flow(model).messages())
    return warnings
