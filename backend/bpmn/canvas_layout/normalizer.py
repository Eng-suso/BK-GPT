"""Normalize semantic references and discard all incoming agent geometry."""
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring

from .policy import BPMN, BPMNDI, FLOW_TYPES, local_name, tag


def normalize_semantics(xml: str, process_name: str | None = None) -> ET.Element:
    root = fromstring(xml)
    if root.tag != tag("definitions"):
        raise ValueError("Il modello deve essere un documento BPMN definitions.")
    ids = [element.get("id") for element in root.iter() if element.get("id") and not element.tag.startswith("{" + BPMNDI + "}")]
    if len(ids) != len(set(ids)):
        raise ValueError("Il modello semantico contiene identificativi duplicati.")
    for child in list(root):
        if child.tag.startswith("{" + BPMNDI + "}"):
            root.remove(child)
    processes = root.findall(tag("process"))
    if not processes:
        raise ValueError("Il modello semantico non contiene un processo.")
    for process in processes:
        if not process.get("id"):
            raise ValueError("Il processo deve avere un identificativo stabile.")
        if process_name and not process.get("name"):
            process.set("name", process_name)
        nodes = {e.get("id"): e for e in process if local_name(e) in FLOW_TYPES and e.tag.startswith("{" + BPMN + "}")}
        if None in nodes:
            raise ValueError("Ogni nodo del processo deve avere un identificativo.")
        flows = sorted(process.findall(tag("sequenceFlow")), key=lambda e: e.get("id", ""))
        for node in nodes.values():
            for child in list(node):
                if child.tag in {tag("incoming"), tag("outgoing")}:
                    node.remove(child)
        for flow in flows:
            source, target = flow.get("sourceRef"), flow.get("targetRef")
            if not flow.get("id") or source not in nodes or target not in nodes:
                raise ValueError(f"Collegamento {flow.get('id')} con estremi non validi nel processo.")
            ET.SubElement(nodes[source], tag("outgoing")).text = flow.get("id")
            ET.SubElement(nodes[target], tag("incoming")).text = flow.get("id")
        assigned: set[str] = set()
        for lane in process.iter(tag("lane")):
            if not lane.get("id") or not lane.get("name", "").strip():
                raise ValueError("Una lane deve identificare un owner semantico esplicito.")
            refs = [ref.text for ref in lane.findall(tag("flowNodeRef"))]
            if any(ref not in nodes for ref in refs) or len(refs) != len(set(refs)):
                raise ValueError(f"Lane {lane.get('id')} con riferimenti non validi.")
            if assigned.intersection(refs):
                raise ValueError("Un task non può appartenere a due owner/lane.")
            assigned.update(refs)
        for node in nodes.values():
            if local_name(node) == "boundaryEvent" and node.get("attachedToRef") not in nodes:
                raise ValueError(f"Evento boundary {node.get('id')} senza attività ospite.")
    # A lane is a role within a process, never an implicit independent pool.
    # A single-process document with lanes gets the process boundary; existing
    # explicit participants and external pools remain semantic authority.
    collaboration = root.find(tag("collaboration"))
    participants = list(root.iter(tag("participant")))
    for process in processes:
        if process.find(tag("laneSet")) is None or any(p.get("processRef") == process.get("id") for p in participants):
            continue
        if collaboration is None:
            collaboration = ET.SubElement(root, tag("collaboration"), {"id": _unique_id(root, "DeliR_Collaboration")})
        participant = ET.SubElement(collaboration, tag("participant"), {
            "id": _unique_id(root, f"DeliR_Pool_{process.get('id')}"),
            "name": process.get("name") or process.get("id"), "processRef": process.get("id"),
        })
        participants.append(participant)
    return root


def _unique_id(root: ET.Element, seed: str) -> str:
    ids = {e.get("id") for e in root.iter()}
    candidate, number = seed, 1
    while candidate in ids:
        candidate = f"{seed}_{number}"
        number += 1
    return candidate
