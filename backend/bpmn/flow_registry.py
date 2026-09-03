"""The single writer for sequence flows during compilation."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.bpmn._helpers import source_ref_id, xml_id
from backend.bpmn.models import BPMNSequenceFlow
from backend.process_understanding import ProcessFlowEdge, ProcessUnderstanding


@dataclass
class FlowRegistry:
    """Single writer for sequence flows.

    Deduplicates by (source, target) so overlapping generators (linear chain,
    alternative-path branches, loop back-edges) cannot emit the same edge twice.
    A generator that hits an already-written pair still contributes its label /
    documentation / traceability to the existing flow instead of losing it.
    Generators call `map()` with the original source-model id of every node they
    create; `apply_edge_overlay()` then folds `flow_edges` labels and gateway
    conditions onto the compiled flows in one final pass.
    """

    used_ids: set[str]
    edges_by_original: dict[tuple[str, str], ProcessFlowEdge] = field(default_factory=dict)
    gateway_ids: set[str] = field(default_factory=set)
    flows: list[BPMNSequenceFlow] = field(default_factory=list)
    seen_pairs: set[tuple[str, str]] = field(default_factory=set)
    _compiled_by_original: dict[str, str] = field(default_factory=dict)
    _flow_by_pair: dict[tuple[str, str], BPMNSequenceFlow] = field(default_factory=dict)
    _source_alias: dict[str, str] = field(default_factory=dict)

    def map(self, original_id: str | None, compiled_id: str) -> None:
        """Register a mapping from source model ID to compiled BPMN node ID.

        Args:
            original_id: The ID in the source ProcessUnderstanding.
            compiled_id: The ID of the corresponding compiled BPMN node.
        """
        if original_id:
            self._compiled_by_original.setdefault(original_id, compiled_id)

    def compiled_for(self, original_id: str) -> str | None:
        """Look up the compiled node ID for a source model ID.

        Args:
            original_id: The ID in the source ProcessUnderstanding.

        Returns:
            The compiled BPMN node ID, or None if not mapped.
        """
        return self._compiled_by_original.get(original_id)

    def outgoing_count(self, node_id: str) -> int:
        """Count the number of outgoing flows from a node.

        Args:
            node_id: The ID of the node to check.

        Returns:
            The count of flows originating from this node.
        """
        return sum(1 for flow in self.flows if flow.sourceRef == node_id)

    def incoming_count(self, node_id: str) -> int:
        """Count the number of incoming flows to a node.

        Args:
            node_id: The ID of the node to check.

        Returns:
            The count of flows targeting this node.
        """
        return sum(1 for flow in self.flows if flow.targetRef == node_id)

    def add(
        self,
        source: str,
        target: str,
        *,
        name: str | None = None,
        documentation: str | None = None,
        source_refs: list[str] | None = None,
    ) -> BPMNSequenceFlow | None:
        """Add or enrich a sequence flow between two nodes.

        Args:
            source: The source node ID.
            target: The target node ID.
            name: Optional flow name/label.
            documentation: Optional documentation text.
            source_refs: Optional traceability references.

        Returns:
            The created or existing BPMNSequenceFlow, or None if invalid.
        """
        if not source or not target or source == target:
            return None
        pair = (source, target)
        existing = self._flow_by_pair.get(pair)
        if existing is not None:
            self._enrich(existing, name=name, documentation=documentation, source_refs=source_refs)
            return existing

        flow = BPMNSequenceFlow(
            id=xml_id(f"Flow_{source}_to_{target}", "Flow", self.used_ids),
            sourceRef=source,
            targetRef=target,
            name=name,
            documentation=documentation,
            sourceRefs=list(source_refs or []),
        )
        self.flows.append(flow)
        self.seen_pairs.add(pair)
        self._flow_by_pair[pair] = flow
        return flow

    def connect_chain(self, chain: list[str]) -> None:
        """Connect a linear sequence of node IDs with sequence flows.

        Args:
            chain: An ordered list of node IDs to connect sequentially.
        """
        for source, target in zip(chain, chain[1:]):
            self.add(source, target)

    def reroute_source(self, from_id: str, to_id: str) -> list[BPMNSequenceFlow]:
        """Move every flow currently leaving `from_id` so it leaves `to_id`.

        Used to splice a gateway in front of a node's existing outgoing flows
        (e.g. a loop back-edge decision) without recreating them. The move is
        recorded so `apply_edge_overlay` still matches a flow_edge that named the
        original `from_id -> successor` transition.
        """
        moved: list[BPMNSequenceFlow] = []
        for flow in self.flows:
            if flow.sourceRef != from_id:
                continue
            old_pair = (from_id, flow.targetRef)
            new_pair = (to_id, flow.targetRef)
            flow.sourceRef = to_id
            self._flow_by_pair.pop(old_pair, None)
            self.seen_pairs.discard(old_pair)
            self._flow_by_pair[new_pair] = flow
            self.seen_pairs.add(new_pair)
            moved.append(flow)
        if moved:
            self._source_alias[from_id] = to_id
        return moved

    def insert_node(self, source: str, target: str, middle: str) -> None:
        """Splice `middle` onto the existing `source -> target` edge, turning it
        into `source -> middle` and adding `middle -> target`. No-op if the edge
        is not present.
        """
        pair = (source, target)
        flow = self._flow_by_pair.pop(pair, None)
        if flow is None:
            return
        self.seen_pairs.discard(pair)
        flow.targetRef = middle
        new_pair = (source, middle)
        self._flow_by_pair[new_pair] = flow
        self.seen_pairs.add(new_pair)
        self.add(middle, target)

    def apply_edge_overlay(self) -> None:
        """Apply flow_edges metadata (labels, conditions) to compiled flows.

        Matches source model flow_edges to their compiled sequence flows and enriches
        them with labels, conditions, and traceability references.
        """
        for (origin_source, origin_target), edge in self.edges_by_original.items():
            source = self._compiled_by_original.get(origin_source)
            target = self._compiled_by_original.get(origin_target)
            if source is None or target is None:
                continue
            flow = self._flow_by_pair.get((source, target))
            if flow is None:
                aliased = self._source_alias.get(source)
                flow = self._flow_by_pair.get((aliased, target)) if aliased else None
            if flow is None:
                continue
            self._enrich(
                flow,
                name=edge.label.strip() or None,
                source_refs=[source_ref_id("flow_edges", edge.id)],
            )
            if edge.condition and flow.sourceRef in self.gateway_ids and not flow.conditionExpression:
                flow.conditionExpression = edge.condition

    @staticmethod
    def _enrich(
        flow: BPMNSequenceFlow,
        *,
        name: str | None = None,
        documentation: str | None = None,
        source_refs: list[str] | None = None,
    ) -> None:
        """Enrich an existing flow with additional metadata.

        Args:
            flow: The BPMNSequenceFlow to enrich.
            name: Optional name to set if not already present.
            documentation: Optional documentation to set if not already present.
            source_refs: Optional traceability references to append.
        """
        if name and not flow.name:
            flow.name = name
        if documentation and not flow.documentation:
            flow.documentation = documentation
        for ref in source_refs or []:
            if ref not in flow.sourceRefs:
                flow.sourceRefs.append(ref)


def sequence_flow_edges_by_endpoint(
    process: ProcessUnderstanding,
) -> dict[tuple[str, str], ProcessFlowEdge]:
    """Build an index of sequence flow edges by their (source, target) endpoints.

    Args:
        process: The ProcessUnderstanding containing flow_edges.

    Returns:
        A dictionary mapping (source_id, target_id) tuples to ProcessFlowEdge instances.
    """
    index: dict[tuple[str, str], ProcessFlowEdge] = {}
    for edge in process.flow_edges:
        if edge.kind == "sequence":
            index.setdefault((edge.source_id, edge.target_id), edge)
    return index
