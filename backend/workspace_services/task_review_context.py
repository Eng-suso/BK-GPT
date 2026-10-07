"""Resolve the selected review task from saved, tenant-owned process authority."""
import json

from defusedxml.ElementTree import fromstring
from fastapi import HTTPException

from backend import workspace_database
from backend.schemas.chat import CanvasChatScope
from backend.workspace_services.impact_review import ReviewNotFound, read_impact_review


def read_task_review_context(scope: CanvasChatScope) -> dict:
    if not scope.review_node_id or not scope.review_base_revision:
        raise HTTPException(422, "Il task e la revisione sono necessari per la chat di review.")
    process = workspace_database.get_process(scope.process_id)
    if not process or process["project_id"] != scope.project_id or process["bpmn_model_id"] != scope.bpmn_model_id:
        raise HTTPException(404, "Processo non trovato.")
    try:
        state = read_impact_review(scope.process_id)
    except ReviewNotFound as exc:
        raise HTTPException(404, "Processo non trovato.") from exc
    if state.base_revision != scope.review_base_revision:
        raise HTTPException(409, "Il processo è cambiato. Ricarica la review prima di continuare.")
    ns = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
    root = fromstring(state.xml) if state.xml else None
    nodes = {e.get("id"): e for e in root.iter() if e.get("id")} if root is not None else {}
    node = nodes.get(scope.review_node_id)
    tags = {ns + name for name in ("task", "userTask", "manualTask", "serviceTask", "sendTask", "receiveTask", "businessRuleTask", "scriptTask")}
    if node is None or node.tag not in tags:
        raise HTTPException(404, "Il task non appartiene al processo salvato.")
    refs: list[str] = []
    documentation = "\n".join(e.text or "" for e in node.findall(ns + "documentation"))
    for e in node.findall(ns + "documentation"):
        text = e.text or ""
        if "DeliR traceability:" in text:
            try:
                value = json.loads(text.split("DeliR traceability:", 1)[1]).get("source_refs", [])
                refs.extend(ref for ref in value if isinstance(ref, str))
            except (ValueError, AttributeError, TypeError):
                pass
    plan = state.plan.model_dump(mode="json") if state.plan else {}
    steps = [step for step in plan.get("steps", []) if f"steps:{step['id']}" in refs]
    flows = [e for e in nodes.values() if e.tag == ns + "sequenceFlow"]

    def related(direction: str) -> list[dict]:
        incoming, outgoing = ("targetRef", "sourceRef") if direction == "upstream" else ("sourceRef", "targetRef")
        visited = {scope.review_node_id}
        pending = [scope.review_node_id]
        found = []
        while pending:
            current = pending.pop()
            for flow in flows:
                target = flow.get(outgoing)
                if flow.get(incoming) != current or not target or target in visited:
                    continue
                visited.add(target)
                pending.append(target)
                item = nodes.get(target)
                if item is not None and item.tag in tags:
                    found.append({"id": target, "name": item.get("name") or target})
        return found

    lane = next((e.get("name") for e in nodes.values() if e.tag == ns + "lane" and any(ref.text == scope.review_node_id for ref in e.findall(ns + "flowNodeRef"))), None)
    return {
        "id": scope.review_node_id, "name": node.get("name") or scope.review_node_id,
        "lane": lane, "documentation": documentation, "source_refs": refs,
        "canonical_steps": steps, "upstream": related("upstream"), "downstream": related("downstream"),
        "base_revision": state.base_revision,
        "recorded_actions": [{**a.model_dump(mode="json", exclude={"proposal_xml"}), "has_diagram": bool(a.proposal_xml)} for a in state.actions if a.node_id == scope.review_node_id],
    }
