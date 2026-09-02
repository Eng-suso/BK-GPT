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

# --- What Prosimos 1.2.6 actually understands (parse_simulation_model) ---------
# Flow nodes: task, startEvent, endEvent, exclusiveGateway, parallelGateway,
# inclusiveGateway, eventBasedGateway, intermediateCatchEvent.
# Everything else either raises a bare KeyError mid-simulation or is silently
# dropped, so every DeliR element has to be mapped onto that vocabulary here.

# Activities -> plain <task>.
_ACTIVITY_TAGS = frozenset(
    {
        "userTask",
        "serviceTask",
        "scriptTask",
        "businessRuleTask",
        "manualTask",
        "sendTask",
        "receiveTask",
        "callActivity",
    }
)

# Container activities -> black-box <task> (inner elements discarded).
_SUBPROCESS_TAGS = frozenset({"subProcess", "transaction", "adHocSubProcess"})

# Gateways Prosimos cannot run -> exclusiveGateway.
_GATEWAY_REWRITE = {"complexGateway": "exclusiveGateway"}

# Events Prosimos cannot run without an event_distribution entry -> spliced out
# (modelled as a zero-duration pass-through).
_PASSTHROUGH_EVENT_TAGS = frozenset(
    {
        "intermediateCatchEvent",
        "intermediateThrowEvent",
    }
)

# Attached / decorative elements Prosimos ignores -> removed outright.
_NOISE_TAGS = frozenset(
    {
        "laneSet",
        "dataObject",
        "dataObjectReference",
        "dataStoreReference",
        "textAnnotation",
        "association",
        "group",
        "extensionElements",
    }
)


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _seq_flows(process: ElementTree.Element) -> list[ElementTree.Element]:
    return process.findall(_q(BPMN_MODEL_NS, "sequenceFlow"))


def normalize_bpmn_for_prosimos(bpmn_xml: str) -> str:
    """Rewrite a DeliR BPMN into the subset Prosimos 1.2.6 can simulate.

    Per process, in order:
      1. strip decorative elements (lanes, data objects, annotations)
      2. down-cast every activity kind to <task>; black-box sub-processes
      3. rewrite unsupported gateways to exclusiveGateway
      4. splice out boundary events (and their exception flow)
      5. splice out intermediate catch/throw events
      6. collapse multiple start events into one
      7. collapse multiple end events into one
    Finally, drop DI shapes/edges that no longer reference a live element.

    Best effort: any parse error returns the original XML so Prosimos reports it.
    """
    for prefix, uri in _PREFIXES.items():
        ElementTree.register_namespace(prefix, uri)

    try:
        root = ElementTree.fromstring(bpmn_xml)
    except ElementTree.ParseError:
        return bpmn_xml

    changed = False
    for process in root.iter(_q(BPMN_MODEL_NS, "process")):
        changed |= _strip_noise(process)
        changed |= _downcast_activities(process)
        changed |= _rewrite_gateways(process)
        changed |= _drop_boundary_events(process)
        changed |= _splice_passthrough_events(process)
        changed |= _collapse_start_events(process)
        changed |= _collapse_end_events(process)
        changed |= _drop_unreachable(process)

    if not changed:
        return bpmn_xml

    _strip_orphan_di(root)
    return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)


def _drop_unreachable(process: ElementTree.Element) -> bool:
    """Remove flow nodes and sequence flows no longer reachable from a start event.

    Dropping boundary events (and their exception flow) leaves the synthesized
    handler task / handler end / handler flow behind as an island; Prosimos would
    either KeyError on it or model an activity that can never fire.
    """
    flow_node_tags = {
        "task",
        "startEvent",
        "endEvent",
        "exclusiveGateway",
        "parallelGateway",
        "inclusiveGateway",
        "eventBasedGateway",
        "intermediateCatchEvent",
        "intermediateThrowEvent",
    }
    starts = [
        element.get("id")
        for element in process
        if _local(element.tag) == "startEvent" and element.get("id")
    ]
    if not starts:
        return False

    successors: dict[str, list[str]] = {}
    for flow in _seq_flows(process):
        successors.setdefault(flow.get("sourceRef", ""), []).append(flow.get("targetRef", ""))

    reachable: set[str] = set()
    queue = list(starts)
    while queue:
        node = queue.pop()
        if node in reachable:
            continue
        reachable.add(node)
        queue.extend(successors.get(node, []))

    removed = False
    for element in list(process):
        local = _local(element.tag)
        element_id = element.get("id")
        if local in flow_node_tags and element_id and element_id not in reachable:
            process.remove(element)
            removed = True
        elif local == "sequenceFlow" and (
            element.get("sourceRef") not in reachable or element.get("targetRef") not in reachable
        ):
            process.remove(element)
            removed = True
    return removed


def _strip_noise(process: ElementTree.Element) -> bool:
    changed = False
    for element in list(process):
        if _local(element.tag) in _NOISE_TAGS:
            process.remove(element)
            changed = True
    return changed


def _downcast_activities(process: ElementTree.Element) -> bool:
    task_tag = _q(BPMN_MODEL_NS, "task")
    targets = [
        element
        for element in list(process.iter())
        if _local(element.tag) in _ACTIVITY_TAGS or _local(element.tag) in _SUBPROCESS_TAGS
    ]
    for element in targets:
        element.tag = task_tag
        _keep_only_flow_refs(element)
    return bool(targets)


def _keep_only_flow_refs(element: ElementTree.Element) -> None:
    """Reduce an element to a black box: keep just <incoming>/<outgoing> hints."""
    keep = {_q(BPMN_MODEL_NS, "incoming"), _q(BPMN_MODEL_NS, "outgoing")}
    for child in list(element):
        if child.tag not in keep:
            element.remove(child)


def _rewrite_gateways(process: ElementTree.Element) -> bool:
    changed = False
    for element in process.iter():
        new_local = _GATEWAY_REWRITE.get(_local(element.tag))
        if new_local:
            element.tag = _q(BPMN_MODEL_NS, new_local)
            changed = True
    return changed


def _drop_boundary_events(process: ElementTree.Element) -> bool:
    boundary_ids = {
        element.get("id")
        for element in process.findall(_q(BPMN_MODEL_NS, "boundaryEvent"))
        if element.get("id")
    }
    if not boundary_ids:
        return False

    for element in process.findall(_q(BPMN_MODEL_NS, "boundaryEvent")):
        process.remove(element)

    for flow in _seq_flows(process):
        if flow.get("sourceRef") in boundary_ids or flow.get("targetRef") in boundary_ids:
            process.remove(flow)

    return True


def _splice_passthrough_events(process: ElementTree.Element) -> bool:
    changed = False
    for element in list(process):
        if _local(element.tag) in _PASSTHROUGH_EVENT_TAGS:
            _splice_node(process, element.get("id"))
            process.remove(element)
            changed = True
    return changed


def _splice_node(process: ElementTree.Element, node_id: str | None) -> None:
    """Remove node_id from the flow, reconnecting its predecessors to its
    successors so the graph stays connected."""
    if not node_id:
        return

    flows = _seq_flows(process)
    in_flows = [f for f in flows if f.get("targetRef") == node_id]
    out_flows = [f for f in flows if f.get("sourceRef") == node_id]

    if len(out_flows) == 1:
        successor = out_flows[0].get("targetRef")
        for flow in in_flows:
            flow.set("targetRef", successor)
        process.remove(out_flows[0])
    elif len(in_flows) == 1:
        predecessor = in_flows[0].get("sourceRef")
        for flow in out_flows:
            flow.set("sourceRef", predecessor)
        process.remove(in_flows[0])
    else:
        # M-to-N (unexpected for a plain event): collapse onto the first exit.
        successor = out_flows[0].get("targetRef") if out_flows else None
        for flow in in_flows:
            if successor is not None:
                flow.set("targetRef", successor)
            else:
                process.remove(flow)
        for flow in out_flows:
            process.remove(flow)


def _collapse_start_events(process: ElementTree.Element) -> bool:
    starts = process.findall(_q(BPMN_MODEL_NS, "startEvent"))
    if len(starts) <= 1:
        return False

    survivor_id = starts[0].get("id")
    dropped_ids = {s.get("id") for s in starts[1:] if s.get("id")}

    for flow in _seq_flows(process):
        if flow.get("sourceRef") in dropped_ids:
            flow.set("sourceRef", survivor_id)
            outgoing = ElementTree.SubElement(starts[0], _q(BPMN_MODEL_NS, "outgoing"))
            outgoing.text = flow.get("id")

    for start in starts[1:]:
        process.remove(start)
    return True


def _collapse_end_events(process: ElementTree.Element) -> bool:
    ends = process.findall(_q(BPMN_MODEL_NS, "endEvent"))
    if len(ends) <= 1:
        return False

    survivor_id = ends[0].get("id")
    dropped_ids = {e.get("id") for e in ends[1:] if e.get("id")}

    for flow in _seq_flows(process):
        if flow.get("targetRef") in dropped_ids:
            flow.set("targetRef", survivor_id)
            incoming = ElementTree.SubElement(ends[0], _q(BPMN_MODEL_NS, "incoming"))
            incoming.text = flow.get("id")

    for end in ends[1:]:
        process.remove(end)
    return True


def _strip_orphan_di(root: ElementTree.Element) -> None:
    live_ids = {
        element.get("id")
        for element in root.iter()
        if element.tag.startswith(f"{{{BPMN_MODEL_NS}}}") and element.get("id")
    }
    for plane in root.iter(_q(BPMN_DI_NS, "BPMNPlane")):
        for di_element in list(plane):
            referenced = di_element.get("bpmnElement")
            if referenced and referenced not in live_ids:
                plane.remove(di_element)
