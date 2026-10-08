"""Deterministic BPMN changes on a separate review proposal, never the baseline."""
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from backend.schemas.chat import CanvasChatScope
from backend.schemas.impact_review import CreateImpactReviewAction
from backend.workspace_services import bpmn_canvas_edit as edit
from backend.workspace_services.impact_review import create_impact_review_action, read_impact_review
from backend.workspace_services.task_review_context import read_task_review_context


class ReviewBpmnOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["update", "add", "delete", "connect", "reconnect", "assign_lane", "layout"]
    element_id: str | None = None
    element_type: str | None = None
    name: str | None = None
    documentation: str | None = None
    source_id: str | None = None
    target_id: str | None = None
    lane_id: str | None = None


def build_review_proposal(scope: CanvasChatScope, *, target: Literal["as_is", "to_be"], title: str, detail: str,
                          operations: list[ReviewBpmnOperation], base_proposal_id: str | None = None) -> dict:
    read_task_review_context(scope)  # validates tenant, model, task and current revision
    state = read_impact_review(scope.process_id)
    xml = state.xml
    if base_proposal_id:
        base = next((a for a in state.actions if a.id == base_proposal_id), None)
        if base is None or not base.proposal_xml or base.base_revision != scope.review_base_revision:
            raise ValueError("La proposta di partenza non esiste o deriva da una revisione precedente.")
        xml = base.proposal_xml
    if not xml or not operations or len(operations) > 30:
        raise ValueError("Servono un diagramma di partenza e da 1 a 30 modifiche.")
    changes = []
    for operation in operations:
        op = operation
        if op.action == "update" and op.element_id:
            # Preserve compiler provenance when updating human documentation.
            documentation = op.documentation
            if documentation is not None:
                previous = next((e for e in edit.list_bpmn_elements(xml) if e["id"] == op.element_id), None)
                old = previous["documentation"] if previous else ""
                marker = "DeliR traceability:"
                if marker in old:
                    documentation = documentation.split(marker, 1)[0].rstrip() + "\n\n" + marker + old.split(marker, 1)[1]
            xml, change = edit.update_bpmn_element(xml, op.element_id, op.name, documentation)
        elif op.action == "add" and op.element_type and op.name:
            xml, change = edit.add_bpmn_element(xml, op.element_type, op.name, op.element_id, op.documentation)
        elif op.action == "delete" and op.element_id:
            xml, change = edit.delete_bpmn_element(xml, op.element_id)
        elif op.action == "connect" and op.source_id and op.target_id:
            xml, change = edit.connect_bpmn_elements(xml, op.source_id, op.target_id, op.element_id, op.name)
        elif op.action == "reconnect" and op.element_id:
            xml, change = edit.reconnect_bpmn_flow(xml, op.element_id, op.source_id, op.target_id)
        elif op.action == "assign_lane" and op.element_id and op.lane_id:
            # Change ownership in the proposal without rewriting the canonical plan.
            from defusedxml.ElementTree import fromstring
            import xml.etree.ElementTree as ET
            root = fromstring(xml)
            ns = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
            lanes = list(root.iter(ns + "lane"))
            lane = next((e for e in lanes if e.get("id") == op.lane_id), None)
            if lane is None or not any(e.get("id") == op.element_id and e.tag.removeprefix(ns) in edit.FLOW_NODE_TYPES for e in root.iter()):
                raise ValueError("Lane o attività non trovata nella proposta.")
            for item in lanes:
                for ref in list(item.findall(ns + "flowNodeRef")):
                    if ref.text == op.element_id:
                        item.remove(ref)
            ET.SubElement(lane, ns + "flowNodeRef").text = op.element_id
            xml = edit.layout_bpmn_di(ET.tostring(root, encoding="unicode"))
            change = {"action": "assign_lane", "id": op.element_id, "lane_id": op.lane_id}
        elif op.action == "layout":
            xml = edit.layout_bpmn_di(xml)
            change = {"action": "layout"}
        else:
            raise ValueError(f"Parametri incompleti per {op.action}.")
        changes.append(change)
    report = edit.validate_bpmn_xml(xml)
    if not report["valid"]:
        raise ValueError("La proposta contiene collegamenti non validi: " + "; ".join(report["issues"]))
    from backend.bpmn.canvas_layout import apply_enterprise_layout
    xml = apply_enterprise_layout(xml)
    layout = edit.validate_bpmn_layout(xml)
    if not layout["valid"]:
        raise ValueError("Il disegno della proposta richiede correzioni: " + "; ".join(layout["issues"]))
    report["layout"] = layout
    action = create_impact_review_action(scope.process_id, CreateImpactReviewAction(
        id=uuid4(), node_id=scope.review_node_id or "", base_revision=scope.review_base_revision or "",
        kind="as_is_proposal" if target == "as_is" else "candidate", title=title, detail=detail, proposal_xml=xml,
    ), "DeliR Review")
    return {"id": action.id, "target": target, "title": title, "changes": changes, "validation": report,
            "base_revision": action.base_revision, "saved_separately": True, "baseline_unchanged": True}
