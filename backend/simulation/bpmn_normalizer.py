from __future__ import annotations

import xml.etree.ElementTree as ElementTree

from backend.simulation.timers import (
    DELIR_SIM_NS,
    ESCALATION_AFTER,
    ESCALATION_NORMAL_FLOW,
    ESCALATION_OF,
    duration_seconds,
)

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
    "delirsim": DELIR_SIM_NS,
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

# SIM-11d: catch events whose wait the consultant sets in the panel.
WAITING_DEFINITIONS = frozenset({"messageEventDefinition", "signalEventDefinition", "conditionalEventDefinition"})

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
      2. inline simple embedded sub-processes (SIM-11e); down-cast every
         activity kind to <task>; the other sub-processes become black boxes
      3. rewrite unsupported gateways to exclusiveGateway
      4. turn interrupting timers on an activity into a decision after it
         (SIM-35); splice out the other boundary events and their exception flow
      5. splice out intermediate catch/throw events, except timers with a fixed
         duration and message, signal or conditional catches, which the engine
         runs as a wait (SIM-11c/d)
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
        changed |= _drop_event_started_activities(process)
        changed |= _expand_subprocesses(process)
        changed |= _downcast_activities(process)
        changed |= _rewrite_gateways(process)
        changed |= _start_instantiating_gateways(process)
        changed |= _timer_escalations(process)
        exception_nodes = _exception_branch_ids(process)
        changed |= _drop_boundary_events(process)
        changed |= _join_link_events(process)
        changed |= _splice_passthrough_events(process)
        changed |= _collapse_start_events(process)
        changed |= _collapse_end_events(process)
        changed |= _drop_unreachable(process, exception_nodes)

    if not changed:
        return bpmn_xml

    _strip_orphan_di(root)
    return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)


def _exception_branch_ids(process: ElementTree.Element) -> set[str]:
    """Only exception branches intentionally removed by normalization may be pruned."""
    pending = [event.get("id") for event in process.findall(_q(BPMN_MODEL_NS, "boundaryEvent"))]
    successors: dict[str, list[str]] = {}
    for flow in _seq_flows(process):
        successors.setdefault(flow.get("sourceRef", ""), []).append(flow.get("targetRef", ""))
    reached: set[str] = set()
    while pending:
        node = pending.pop()
        if node and node not in reached:
            reached.add(node)
            pending.extend(successors.get(node, []))
    return reached


def _drop_unreachable(process: ElementTree.Element, candidates: set[str]) -> bool:
    """
    Remove unreachable exception branches, preserving unrelated disconnected nodes
    so preflight can report them instead of silently simulating a partial model.
    
    Parameters:
        process (ElementTree.Element): BPMN process element to update.
    
    Returns:
        bool: `True` if any unreachable elements were removed, `False` otherwise.
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

    dropped = candidates - reachable
    removed = False
    for element in list(process):
        local = _local(element.tag)
        element_id = element.get("id")
        if local in flow_node_tags and element_id in dropped:
            process.remove(element)
            removed = True
        elif local == "sequenceFlow" and (
            element.get("sourceRef") in dropped or element.get("targetRef") in dropped
        ):
            process.remove(element)
            removed = True
    return removed


def _strip_noise(process: ElementTree.Element) -> bool:
    """Remove decorative and unsupported child elements from a BPMN process.
    
    Parameters:
    	process (ElementTree.Element): The BPMN process element to clean.
    
    Returns:
    	bool: `True` if any elements were removed, `False` otherwise.
    """
    changed = False
    for element in list(process):
        if _local(element.tag) in _NOISE_TAGS:
            process.remove(element)
            changed = True
    return changed


def expandable_subprocess_ids(process: ElementTree.Element) -> set[str]:
    """SIM-11e: i sottoprocessi che si possono srotolare nel processo che li contiene.

    Uno solo inizio e una sola fine senza eventi, un flusso che entra e uno che
    esce, nessun evento sul bordo, nessun ciclo o multi-istanza, nessun
    sottoprocesso a evento dentro: allora i passi interni sono il percorso del
    caso, uno dopo l'altro, e il motore li simula ciascuno con la sua durata, le
    sue risorse e i suoi rami. Gli altri restano una scatola nera.
    """
    flows = _seq_flows(process)
    attached = {e.get("attachedToRef") for e in process if _local(e.tag) == "boundaryEvent"}
    result = set()
    for sub in process:
        sub_id = sub.get("id", "")
        if _local(sub.tag) != "subProcess" or not sub_id or sub_id in attached:
            continue
        children = list(sub)
        if any(_local(c.tag) in {"standardLoopCharacteristics", "multiInstanceLoopCharacteristics"} for c in children):
            continue
        if any(c.get("triggeredByEvent") == "true" or c.get("isForCompensation") == "true" for c in children):
            continue
        starts = [c for c in children if _local(c.tag) == "startEvent"]
        ends = [c for c in children if _local(c.tag) == "endEvent"]
        if len(starts) != 1 or len(ends) != 1 or any(_has_definition(e) for e in (*starts, *ends)):
            continue
        inner = [c for c in children if _local(c.tag) == "sequenceFlow"]
        out_of_start = [f for f in inner if f.get("sourceRef") == starts[0].get("id")]
        into_end = [f for f in inner if f.get("targetRef") == ends[0].get("id")]
        if len(out_of_start) != 1 or len(into_end) != 1 or out_of_start[0].get("targetRef") == ends[0].get("id"):
            continue
        if sum(f.get("targetRef") == sub_id for f in flows) != 1 or sum(f.get("sourceRef") == sub_id for f in flows) != 1:
            continue
        result.add(sub_id)
    return result


def _has_definition(event: ElementTree.Element) -> bool:
    return any(_local(child.tag).endswith("EventDefinition") for child in event)


def _expand_subprocesses(process: ElementTree.Element) -> bool:
    """Inline the expandable sub-processes, outermost first, until none is left."""
    changed = False
    while True:
        expandable = expandable_subprocess_ids(process)
        sub = next((e for e in process if e.get("id") in expandable), None)
        if sub is None:
            return changed
        _inline_subprocess(process, sub)
        changed = True


def _inline_subprocess(process: ElementTree.Element, sub: ElementTree.Element) -> None:
    sub_id = sub.get("id", "")
    flows = _seq_flows(process)
    entering = next(f for f in flows if f.get("targetRef") == sub_id)
    leaving = next(f for f in flows if f.get("sourceRef") == sub_id)
    start = next(c for c in sub if _local(c.tag) == "startEvent")
    end = next(c for c in sub if _local(c.tag) == "endEvent")
    inner = [c for c in sub if _local(c.tag) == "sequenceFlow"]
    first = next(f for f in inner if f.get("sourceRef") == start.get("id"))
    last = next(f for f in inner if f.get("targetRef") == end.get("id"))
    # The flow into the sub-process now reaches its first step; its last step
    # leaves on the flow that left the sub-process.
    entering.set("targetRef", first.get("targetRef", ""))
    leaving.set("sourceRef", last.get("sourceRef", ""))
    renamed = {first.get("id"): entering.get("id"), last.get("id"): leaving.get("id")}
    position = list(process).index(sub)
    moved = [c for c in sub if c not in (start, end, first, last) and _local(c.tag) not in _SUBPROCESS_ONLY_TAGS]
    for child in moved:
        for ref in child:
            if _local(ref.tag) in {"incoming", "outgoing"} and ref.text in renamed:
                ref.text = renamed[ref.text]
        process.insert(position, child)
        position += 1
    process.remove(sub)


# Children that describe the sub-process itself, not a step of it.
_SUBPROCESS_ONLY_TAGS = frozenset({"incoming", "outgoing", "documentation", "extensionElements", "ioSpecification",
                                   "property", "dataInputAssociation", "dataOutputAssociation"})


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


def _drop_event_started_activities(process: ElementTree.Element) -> bool:
    """Event sub-processes and compensation activities are off the sequence flow.

    The engine only runs what the flow reaches; left in, they would be
    disconnected tasks that fail preflight.
    """
    dropped = [
        element for element in list(process)
        if element.get("triggeredByEvent") == "true" or element.get("isForCompensation") == "true"
    ]
    for element in dropped:
        process.remove(element)
    return bool(dropped)


def _rewrite_gateways(process: ElementTree.Element) -> bool:
    changed = False
    for element in process.iter():
        new_local = _GATEWAY_REWRITE.get(_local(element.tag))
        if new_local:
            element.tag = _q(BPMN_MODEL_NS, new_local)
            for child in [c for c in element if _local(c.tag) == "activationCondition"]:
                element.remove(child)
            changed = True
    return changed


def _start_instantiating_gateways(process: ElementTree.Element) -> bool:
    """An event-based gateway that starts the process gets a start event in front.

    Prosimos starts every case from a start event; the gateway then routes as a
    plain event-based gateway (a parallel one takes a single branch).
    """
    changed = False
    for gateway in process.findall(_q(BPMN_MODEL_NS, "eventBasedGateway")):
        if gateway.get("instantiate") != "true":
            continue
        gateway_id = gateway.get("id", "")
        start = ElementTree.Element(_q(BPMN_MODEL_NS, "startEvent"), {"id": f"{gateway_id}_start"})
        flow = ElementTree.Element(
            _q(BPMN_MODEL_NS, "sequenceFlow"),
            {"id": f"{gateway_id}_start_flow", "sourceRef": start.get("id"), "targetRef": gateway_id},
        )
        ElementTree.SubElement(start, _q(BPMN_MODEL_NS, "outgoing")).text = flow.get("id")
        incoming = ElementTree.Element(_q(BPMN_MODEL_NS, "incoming"))
        incoming.text = flow.get("id")
        gateway.insert(0, incoming)
        for attribute in ("instantiate", "eventGatewayType"):
            gateway.attrib.pop(attribute, None)
        process.insert(list(process).index(gateway), start)
        process.append(flow)
        changed = True
    return changed


def _timer_escalations(process: ElementTree.Element) -> bool:
    """An interrupting timer on an activity becomes an exclusive gateway after it.

    The gateway keeps the boundary's id and name, so its exception flow keeps
    its source; the activity's only outgoing flow now leaves from the gateway
    and is marked as the normal path. ``ir/escalations.py`` compiles the share
    of cases that outlast the timer. Anything else (non-interrupting, a date or
    a cycle, several flows out) is left to ``_drop_boundary_events``.
    """
    flows = _seq_flows(process)
    activities = {element.get("id") for element in process if _local(element.tag) == "task"}
    changed = False
    for event in process.findall(_q(BPMN_MODEL_NS, "boundaryEvent")):
        event_id, activity_id = event.get("id", ""), event.get("attachedToRef", "")
        timer = event.find(_q(BPMN_MODEL_NS, "timerEventDefinition"))
        after = duration_seconds(None if timer is None else timer.findtext(_q(BPMN_MODEL_NS, "timeDuration")))
        exception = [flow for flow in flows if flow.get("sourceRef") == event_id]
        normal = [flow for flow in flows if flow.get("sourceRef") == activity_id]
        if (
            after is None or event.get("cancelActivity") == "false" or activity_id not in activities
            or len(exception) != 1 or len(normal) != 1
        ):
            continue
        gateway = ElementTree.Element(_q(BPMN_MODEL_NS, "exclusiveGateway"), {
            "id": event_id,
            **({"name": event.get("name", "")} if event.get("name") else {}),
            ESCALATION_OF: activity_id,
            ESCALATION_AFTER: repr(after),
            ESCALATION_NORMAL_FLOW: normal[0].get("id", ""),
        })
        process.insert(list(process).index(event), gateway)
        process.remove(event)
        normal[0].set("sourceRef", event_id)
        process.append(ElementTree.Element(_q(BPMN_MODEL_NS, "sequenceFlow"), {
            "id": f"{event_id}__from", "sourceRef": activity_id, "targetRef": event_id,
        }))
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


def _join_link_events(process: ElementTree.Element) -> bool:
    """Draw the flow a link pair stands for, so splicing the pair out keeps the path.

    A link throw and the link catch with the same name are one flow drawn in two
    pieces (OMG BPMN 2.0, 10.4.5); the engine needs it as a real flow.
    """
    def link_name(event: ElementTree.Element) -> str | None:
        definition = event.find(_q(BPMN_MODEL_NS, "linkEventDefinition"))
        return None if definition is None else " ".join((definition.get("name") or "").split()).casefold()

    catches = {
        link_name(event): event.get("id")
        for event in process.findall(_q(BPMN_MODEL_NS, "intermediateCatchEvent"))
        if link_name(event) is not None
    }
    changed = False
    for throw in process.findall(_q(BPMN_MODEL_NS, "intermediateThrowEvent")):
        target = catches.get(link_name(throw)) if link_name(throw) is not None else None
        if target is None:
            continue
        process.append(
            ElementTree.Element(
                _q(BPMN_MODEL_NS, "sequenceFlow"),
                {"id": f"{throw.get('id')}_link", "sourceRef": throw.get("id", ""), "targetRef": target},
            )
        )
        changed = True
    return changed


def _splice_passthrough_events(process: ElementTree.Element) -> bool:
    waits = wait_event_ids(process)
    changed = False
    for element in list(process):
        if _local(element.tag) in _PASSTHROUGH_EVENT_TAGS and element.get("id") not in waits:
            _splice_node(process, element.get("id"))
            process.remove(element)
            changed = True
    return changed


def wait_event_ids(process: ElementTree.Element) -> set[str]:
    """SIM-11c/d: gli eventi intermedi che il motore simula come un'attesa.

    Un timer con una durata fissa (``PT48H``) resta nel BPMN: il caso aspetta
    quella durata, a qualsiasi ora (il timer conta l'orologio, non il
    calendario). Restano anche messaggi, segnali e condizioni: quanto si
    aspetta lo dice il consulente nel pannello, e finche' non lo dice il caso
    prosegue subito, come prima. Si tolgono i timer con una data o un ciclo e
    ogni evento dopo un gateway a eventi, dove l'evento decide il ramo.
    """
    event_gateways = {g.get("id") for g in process if _local(g.tag) == "eventBasedGateway"}
    after_event_gateway = {f.get("targetRef") for f in _seq_flows(process) if f.get("sourceRef") in event_gateways}
    waits = set()
    for event in process.findall(_q(BPMN_MODEL_NS, "intermediateCatchEvent")):
        if event.get("id") in after_event_gateway:
            continue
        definitions = {_local(child.tag) for child in event}
        timer = event.find(_q(BPMN_MODEL_NS, "timerEventDefinition"))
        if timer is not None:
            if duration_seconds(timer.findtext(_q(BPMN_MODEL_NS, "timeDuration"))) is not None:
                waits.add(event.get("id", ""))
        elif len(definitions & WAITING_DEFINITIONS) == 1:
            waits.add(event.get("id", ""))
    return waits


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
