"""Control-flow graph of a (Prosimos-normalized) BPMN, used to attribute observed
`activity A -> activity B` transitions in the event log to the sequence flow(s)
that actually connect them.

The Prosimos event log only records activities (no gateway / event rows), so a
consecutive pair in a case path is *not* an edge: the real route may run through
one or more gateways. We attribute a transition's volume to sequence flows only
when there is exactly one activity-free path between the two activities. When the
route is ambiguous (parallel / inclusive splits, equivalent branches) we record
the count at node level and leave the flows unattributed rather than inventing an
arrow.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from xml.etree import ElementTree

ACTIVITY_TAGS = {
    "task",
    "userTask",
    "serviceTask",
    "scriptTask",
    "businessRuleTask",
    "manualTask",
    "sendTask",
    "receiveTask",
    "callActivity",
    "subProcess",
}

# Everything the log can skip over between two activities.
PASSTHROUGH_TAGS = {
    "exclusiveGateway",
    "inclusiveGateway",
    "parallelGateway",
    "complexGateway",
    "eventBasedGateway",
    "startEvent",
    "endEvent",
    "intermediateCatchEvent",
    "intermediateThrowEvent",
    "boundaryEvent",
}

_MAX_PATH_NODES = 12


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@dataclass
class FlowGraph:
    # node id -> local tag name
    node_kind: dict[str, str] = field(default_factory=dict)
    # sequence flow id -> (source id, target id)
    flow_ends: dict[str, tuple[str, str]] = field(default_factory=dict)
    # source id -> list of (flow id, target id)
    _out: dict[str, list[tuple[str, str]]] = field(default_factory=lambda: defaultdict(list))

    def is_activity(self, node_id: str) -> bool:
        return self.node_kind.get(node_id) in ACTIVITY_TAGS

    def unique_flow_path(self, src_activity: str, dst_activity: str) -> list[str] | None:
        """Sequence-flow ids on the single activity-free path src -> dst, or None
        when there are zero or more than one such paths."""
        found: list[list[str]] = []

        def walk(node: str, flows: list[str], visited: frozenset[str]) -> None:
            if len(found) > 1 or len(flows) > _MAX_PATH_NODES:
                return
            for flow_id, target in self._out.get(node, ()):
                if target == dst_activity:
                    found.append([*flows, flow_id])
                    continue
                if (
                    target in visited
                    or self.node_kind.get(target) not in PASSTHROUGH_TAGS
                ):
                    # hit another activity, an unknown node, or a loop -> dead end
                    continue
                walk(target, [*flows, flow_id], visited | {target})

        walk(src_activity, [], frozenset({src_activity}))
        return found[0] if len(found) == 1 else None


def build_flow_graph(bpmn_xml: str) -> FlowGraph:
    graph = FlowGraph()
    try:
        root = ElementTree.fromstring(bpmn_xml.encode("utf-8"))
    except ElementTree.ParseError:
        return graph

    for element in root.iter():
        tag = _local(element.tag)
        node_id = element.attrib.get("id")
        if not node_id:
            continue
        if tag == "sequenceFlow":
            source = element.attrib.get("sourceRef") or ""
            target = element.attrib.get("targetRef") or ""
            if source and target:
                graph.flow_ends[node_id] = (source, target)
                graph._out[source].append((node_id, target))
        elif tag in ACTIVITY_TAGS or tag in PASSTHROUGH_TAGS:
            graph.node_kind[node_id] = tag

    return graph
