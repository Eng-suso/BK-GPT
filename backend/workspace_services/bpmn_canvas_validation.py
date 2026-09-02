from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from collections import Counter

from pydantic import ValidationError

from backend.bpmn import BPMNSemanticModel
from backend.process_understanding import ProcessUnderstanding
from backend.workspace_services.bpmn_canvas_edit import (
    BPMN_NS,
    list_bpmn_elements,
    validate_bpmn_xml,
)

logger = logging.getLogger(__name__)


FLOW_NODE_TYPES = {
    "startEvent",
    "endEvent",
    "intermediateCatchEvent",
    "intermediateThrowEvent",
    "boundaryEvent",
    "task",
    "userTask",
    "serviceTask",
    "sendTask",
    "receiveTask",
    "manualTask",
    "businessRuleTask",
    "scriptTask",
    "subProcess",
    "exclusiveGateway",
    "parallelGateway",
    "inclusiveGateway",
    "eventBasedGateway",
}

GATEWAY_TYPES = {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway"}


def validate_canvas_against_process(
    *,
    xml: str,
    process_understanding: dict | ProcessUnderstanding | None = None,
    bpmn_semantic_model: dict | BPMNSemanticModel | None = None,
) -> dict:
    technical = validate_bpmn_xml(xml)
    elements = list_bpmn_elements(xml)
    element_names = [_normalize(item.get("name", "")) for item in elements]
    element_text = " ".join(
        _normalize(" ".join([str(item.get("name", "")), str(item.get("documentation", ""))]))
        for item in elements
    )
    element_type_counts = Counter(item.get("type", "") for item in elements)
    issues = list(technical.get("issues") or [])
    warnings = list(technical.get("warnings") or [])
    coverage = {
        "technical_valid": bool(technical.get("valid")),
        "semantic_model_available": False,
        "process_understanding_available": False,
        "matched_semantic_nodes": 0,
        "missing_semantic_nodes": [],
        "matched_lanes": 0,
        "missing_lanes": [],
    }

    root = _parse_xml(xml)
    semantic_payload = _extract_semantic_payload(root)
    gateway_issues = _gateway_path_issues(root)
    issues.extend(gateway_issues)

    semantic_model = _coerce_semantic_model(bpmn_semantic_model)
    if semantic_model is not None:
        coverage["semantic_model_available"] = True
        _validate_semantic_model_coverage(
            semantic_model=semantic_model,
            element_names=element_names,
            element_type_counts=element_type_counts,
            coverage=coverage,
            issues=issues,
            warnings=warnings,
        )
    else:
        warnings.append("BPMNSemanticModel non disponibile: validazione semantica limitata.")

    understanding = _coerce_understanding(process_understanding)
    if understanding is None and semantic_model is not None and semantic_model.sourceProcessUnderstanding:
        understanding = _coerce_understanding(semantic_model.sourceProcessUnderstanding)
    if understanding is not None:
        coverage["process_understanding_available"] = True
        _validate_lossless_semantic_payload(
            semantic_payload=semantic_payload,
            process=understanding,
            issues=issues,
            warnings=warnings,
        )
        _validate_process_understanding_coverage(
            process=understanding,
            element_text=element_text,
            element_type_counts=element_type_counts,
            issues=issues,
            warnings=warnings,
        )
    else:
        warnings.append("ProcessUnderstanding non disponibile: impossibile verificare path, loop, handoff e data object.")

    return {
        "valid": not issues,
        "technical": technical,
        "semantic_valid": not issues,
        "issues": _unique(issues),
        "warnings": _unique(warnings),
        "coverage": coverage,
        "counts": {
            **technical.get("counts", {}),
            "lanes": element_type_counts.get("lane", 0),
            "gateways": sum(element_type_counts.get(item, 0) for item in GATEWAY_TYPES),
            "data_objects": element_type_counts.get("dataObjectReference", 0),
            "annotations": element_type_counts.get("textAnnotation", 0),
        },
    }


def _validate_lossless_semantic_payload(
    *,
    semantic_payload: dict | None,
    process: ProcessUnderstanding,
    issues: list[str],
    warnings: list[str],
) -> None:
    if semantic_payload is None:
        issues.append("Payload semantico DeliR mancante: il canvas non e' lossless rispetto al ProcessUnderstanding.")
        return

    stored_understanding = semantic_payload.get("process_understanding")
    if not stored_understanding:
        issues.append("Payload semantico DeliR incompleto: ProcessUnderstanding sorgente mancante.")
        return

    try:
        stored_model = ProcessUnderstanding.model_validate(stored_understanding)
    except Exception:
        issues.append("Payload semantico DeliR non validabile come ProcessUnderstanding.")
        return

    if stored_model.model_dump(mode="json") != process.model_dump(mode="json"):
        warnings.append("Il payload semantico DeliR non coincide esattamente con il ProcessUnderstanding corrente.")

    plan = semantic_payload.get("bpmn_compilation_plan") or {}
    coverage = plan.get("coverage") or {}
    losses = coverage.get("losses") or []
    if losses:
        issues.append("Compilazione BPMN non lossless: " + "; ".join(str(item) for item in losses[:8]))

    represented = int(coverage.get("represented_source_items") or 0)
    total = int(coverage.get("total_source_items") or 0)
    if total and represented < total:
        issues.append(f"Traceability incompleta: {represented}/{total} elementi sorgente rappresentati.")


def _extract_semantic_payload(root: ET.Element) -> dict | None:
    process = next(
        (
            element
            for element in root.iter()
            if _namespace(element.tag) == BPMN_NS and _local_name(element.tag) == "process"
        ),
        None,
    )
    if process is None:
        return None

    for child in process:
        if _namespace(child.tag) != BPMN_NS or _local_name(child.tag) != "documentation":
            continue
        text = child.text or ""
        marker = "DeliR semantic payload:"
        if marker not in text:
            continue
        _, _, payload_text = text.partition(marker)
        try:
            payload = json.loads(payload_text.strip())
        except json.JSONDecodeError:
            return None
        if payload.get("schema") == "delir.semantic_payload.v1":
            return payload

    return None


def _validate_semantic_model_coverage(
    *,
    semantic_model: BPMNSemanticModel,
    element_names: list[str],
    element_type_counts: Counter,
    coverage: dict,
    issues: list[str],
    warnings: list[str],
) -> None:
    canvas_name_set = {name for name in element_names if name}
    missing_nodes = []
    matched_nodes = 0

    for node in semantic_model.flowNodes:
        normalized = _normalize(node.name)
        if not normalized:
            continue
        if normalized in canvas_name_set:
            matched_nodes += 1
        else:
            missing_nodes.append(node.name)

    coverage["matched_semantic_nodes"] = matched_nodes
    coverage["missing_semantic_nodes"] = missing_nodes
    if missing_nodes:
        warnings.append(
            "Il canvas non rappresenta tutti i nodi del BPMNSemanticModel: "
            + ", ".join(missing_nodes[:8])
        )

    lane_names = {_normalize(item.name) for item in semantic_model.lanes if item.name.strip()}
    canvas_lanes = {name for name in element_names if name}
    missing_lanes = [lane.name for lane in semantic_model.lanes if _normalize(lane.name) not in canvas_lanes]
    coverage["matched_lanes"] = len(lane_names) - len(missing_lanes)
    coverage["missing_lanes"] = missing_lanes
    if missing_lanes:
        warnings.append("Lane semantiche non rappresentate nel canvas: " + ", ".join(missing_lanes[:8]))

    semantic_gateways = sum(1 for node in semantic_model.flowNodes if node.type in GATEWAY_TYPES)
    canvas_gateways = sum(element_type_counts.get(item, 0) for item in GATEWAY_TYPES)
    if semantic_gateways and canvas_gateways < semantic_gateways:
        warnings.append("Il canvas contiene meno gateway del BPMNSemanticModel.")

    if len(semantic_model.sequenceFlows) > element_type_counts.get("sequenceFlow", 0):
        warnings.append("Il canvas contiene meno sequence flow del BPMNSemanticModel.")


def _validate_process_understanding_coverage(
    *,
    process: ProcessUnderstanding,
    element_text: str,
    element_type_counts: Counter,
    issues: list[str],
    warnings: list[str],
) -> None:
    missing_steps = [
        step.label
        for step in process.steps
        if step.label.strip() and _normalize(step.label) not in element_text
    ]
    if missing_steps:
        warnings.append("Step del ProcessUnderstanding non visibili nel canvas: " + ", ".join(missing_steps[:8]))

    if process.decisions and not any(element_type_counts.get(item, 0) for item in GATEWAY_TYPES):
        issues.append("Il processo contiene decisioni ma il canvas non contiene gateway.")

    if process.alternative_paths and not any(element_type_counts.get(item, 0) for item in GATEWAY_TYPES):
        issues.append("Il processo contiene alternative path ma il canvas non contiene gateway.")

    if process.loops:
        warnings.append("Il processo contiene loop: verificare che il canvas abbia un ritorno o una gestione retry esplicita.")

    if process.handoffs and element_type_counts.get("lane", 0) < 2:
        warnings.append("Il processo contiene handoff ma il canvas ha meno di due lane.")

    external_pool_candidates = [
        relation.actor_id
        for relation in process.actor_relationships
        if relation.bpmn_pool_candidate
    ]
    if external_pool_candidates:
        warnings.append(
            "Sono presenti candidati pool esterni non verificabili con la validazione lane-only: "
            + ", ".join(external_pool_candidates[:8])
        )


def _gateway_path_issues(root: ET.Element) -> list[str]:
    issues = []
    outgoing_by_id: dict[str, int] = {}

    for element in root.iter():
        if _namespace(element.tag) != BPMN_NS:
            continue
        element_id = element.attrib.get("id")
        if not element_id or _local_name(element.tag) not in GATEWAY_TYPES:
            continue
        outgoing_by_id[element_id] = sum(
            1
            for child in element
            if _namespace(child.tag) == BPMN_NS and _local_name(child.tag) == "outgoing"
        )

    for gateway_id, outgoing_count in outgoing_by_id.items():
        if outgoing_count < 2:
            issues.append(f"Gateway {gateway_id} ha meno di due uscite.")

    return issues


def _coerce_semantic_model(value: dict | BPMNSemanticModel | None) -> BPMNSemanticModel | None:
    if value is None:
        return None
    if isinstance(value, BPMNSemanticModel):
        return value
    try:
        return BPMNSemanticModel.model_validate(value)
    except ValidationError as exc:
        logger.warning("bpmn canvas validation: semantic model payload rejected: %s", exc)
        return None


def _coerce_understanding(value: dict | ProcessUnderstanding | None) -> ProcessUnderstanding | None:
    if value is None:
        return None
    if isinstance(value, ProcessUnderstanding):
        return value
    try:
        return ProcessUnderstanding.model_validate(value)
    except ValidationError as exc:
        logger.warning("bpmn canvas validation: process understanding payload rejected: %s", exc)
        return None


def _parse_xml(xml: str) -> ET.Element:
    return ET.fromstring(xml.strip())


def _normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _namespace(tag: str) -> str:
    if tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return ""


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag
