from __future__ import annotations

import xml.etree.ElementTree as ElementTree

BPMN_MODEL_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMN_DI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

_PREFIXES = {
    "bpmn": BPMN_MODEL_NS,
    "bpmndi": BPMN_DI_NS,
    "dc": DC_NS,
    "di": DI_NS,
    "xsi": XSI_NS,
}


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def normalize_bpmn_for_prosimos(bpmn_xml: str) -> str:
    """Adapt a DeliR BPMN so Prosimos 1.2.6 accepts it.

    Currently: collapse multiple end events per process into one. Prosimos
    rejects models with more than one end event ("Temporarily not supporting
    multiple end events"), but consultant diagrams routinely have several.
    All flows that targeted a dropped end event are rewired to the survivor.

    Best effort: on any parse problem the original XML is returned so Prosimos
    can surface its own error.
    """
    for prefix, uri in _PREFIXES.items():
        ElementTree.register_namespace(prefix, uri)

    try:
        root = ElementTree.fromstring(bpmn_xml)
    except ElementTree.ParseError:
        return bpmn_xml

    removed_ids: set[str] = set()

    for process in root.iter(_q(BPMN_MODEL_NS, "process")):
        end_events = process.findall(_q(BPMN_MODEL_NS, "endEvent"))
        if len(end_events) <= 1:
            continue

        survivor = end_events[0]
        survivor_id = survivor.get("id")
        dropped = end_events[1:]
        dropped_ids = {event.get("id") for event in dropped if event.get("id")}

        for flow in process.findall(_q(BPMN_MODEL_NS, "sequenceFlow")):
            if flow.get("targetRef") in dropped_ids:
                flow.set("targetRef", survivor_id)
                incoming = ElementTree.SubElement(
                    survivor, _q(BPMN_MODEL_NS, "incoming")
                )
                incoming.text = flow.get("id")

        for event in dropped:
            process.remove(event)

        removed_ids |= dropped_ids

    if not removed_ids:
        return bpmn_xml

    for plane in root.iter(_q(BPMN_DI_NS, "BPMNPlane")):
        for shape in list(plane.findall(_q(BPMN_DI_NS, "BPMNShape"))):
            if shape.get("bpmnElement") in removed_ids:
                plane.remove(shape)

    return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)
