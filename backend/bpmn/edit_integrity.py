"""Fail closed when a local canvas tool changes unrelated BPMN semantics."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring

from backend.bpmn.canvas_layout.normalizer import normalize_semantics
from backend.bpmn.canvas_layout.policy import BPMN

_DERIVED = {f"{{{BPMN}}}incoming", f"{{{BPMN}}}outgoing"}
_DOCUMENTATION = f"{{{BPMN}}}documentation"
_FLOW_NODE_REF = f"{{{BPMN}}}flowNodeRef"


def _semantic_projection(
    xml: str,
    *,
    omit_ids: frozenset[str] = frozenset(),
    mask_id: str | None = None,
    mask_attributes: frozenset[str] = frozenset(),
    mask_documentation: bool = False,
    omit_new_lane_set: bool = False,
    omit_new_auto_pool: bool = False,
) -> tuple:
    root = normalize_semantics(xml)
    process_ids = {process.get("id") for process in root.findall(f"{{{BPMN}}}process")}

    def visit(element: ET.Element) -> tuple | None:
        if element.tag in _DERIVED or element.attrib.get("id") in omit_ids:
            return None
        if omit_new_auto_pool and element.tag == f"{{{BPMN}}}collaboration":
            participants = list(element)
            if (
                element.get("id", "").startswith("DeliR_Collaboration")
                and len(participants) == 1
                and participants[0].tag == f"{{{BPMN}}}participant"
                and participants[0].get("id", "").startswith("DeliR_Pool_")
                and participants[0].get("processRef") in process_ids
            ):
                return None
        if element.tag == _FLOW_NODE_REF and (element.text or "").strip() in omit_ids:
            return None
        attrs = dict(element.attrib)
        if attrs.get("id") == mask_id:
            for key in mask_attributes:
                attrs.pop(key, None)
        children = []
        for child in element:
            if attrs.get("id") == mask_id and mask_documentation and child.tag == _DOCUMENTATION:
                continue
            projected = visit(child)
            if projected is not None:
                children.append(projected)
        if omit_new_lane_set and element.tag == f"{{{BPMN}}}laneSet" and not children:
            return None
        return element.tag, tuple(sorted(attrs.items())), (element.text or "").strip(), tuple(children)

    result = visit(root)
    if result is None:
        raise ValueError("Il documento BPMN non contiene una radice semantica.")
    return result


def assert_local_edit_integrity(
    *,
    before_xml: str,
    after_xml: str,
    operation: str,
    change: dict | None = None,
    element_id: str | None = None,
) -> None:
    """Compare full semantic trees after masking only the declared local delta."""
    change = change or {}
    element_id = str(element_id or change.get("id") or "")
    if operation == "update_element":
        if not element_id:
            raise ValueError("Modifica locale senza ID dell'elemento.")
        options = {"mask_id": element_id, "mask_attributes": frozenset({"name"}),
                   "mask_documentation": True}
        before = _semantic_projection(before_xml, **options)
        after = _semantic_projection(after_xml, **options)
    elif operation == "add_element":
        if not element_id:
            raise ValueError("Aggiunta locale senza ID dell'elemento.")
        original_root = fromstring(before_xml)
        new_lane = change.get("type") == "lane"
        had_lane_set = original_root.find(f".//{{{BPMN}}}laneSet") is not None
        before = _semantic_projection(before_xml)
        after = _semantic_projection(
            after_xml,
            omit_ids=frozenset({element_id}),
            omit_new_lane_set=new_lane and not had_lane_set,
            omit_new_auto_pool=(new_lane and not had_lane_set
                                and original_root.find(f"{{{BPMN}}}collaboration") is None),
        )
    elif operation == "delete_element":
        if not element_id:
            raise ValueError("Eliminazione locale senza ID dell'elemento.")
        connectors = tuple(change.get("removed_connectors", ()))
        if "" in connectors:
            raise ValueError("Eliminazione locale con collegamenti senza ID: canvas invariato.")
        removed = frozenset({element_id, *change.get("removed_connected_flows", ()),
                             *change.get("removed_boundary_events", ()), *connectors})
        before = _semantic_projection(before_xml, omit_ids=removed)
        after = _semantic_projection(after_xml)
    elif operation == "clear_canvas":
        removed = frozenset(str(item.get("id") or "") for item in change.get("removed", ()))
        if "" in removed:
            raise ValueError("Svuotamento canvas senza elenco completo degli elementi rimossi.")
        before = _semantic_projection(before_xml, omit_ids=removed)
        after = _semantic_projection(after_xml)
    elif operation == "connect_elements":
        if not element_id:
            raise ValueError("Collegamento locale senza ID del flow.")
        before = _semantic_projection(before_xml)
        after = _semantic_projection(after_xml, omit_ids=frozenset({element_id}))
    elif operation == "reconnect_flow":
        if not element_id:
            raise ValueError("Riconnessione locale senza ID del flow.")
        options = {"mask_id": element_id,
                   "mask_attributes": frozenset({"sourceRef", "targetRef"})}
        before = _semantic_projection(before_xml, **options)
        after = _semantic_projection(after_xml, **options)
    elif operation == "layout":
        before = _semantic_projection(before_xml)
        after = _semantic_projection(after_xml)
    else:
        raise ValueError(f"Operazione locale non coperta dal controllo di integrita': {operation}")
    if before != after:
        raise ValueError(
            f"La modifica {operation} ha alterato dati BPMN non richiesti: canvas invariato."
        )
