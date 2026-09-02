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

    def map(self, original_id: str | None, compiled_id: str) -> None:
        if original_id:
            self._compiled_by_original.setdefault(original_id, compiled_id)

    def compiled_for(self, original_id: str) -> str | None:
        return self._compiled_by_original.get(original_id)

    def outgoing_count(self, node_id: str) -> int:
        return sum(1 for flow in self.flows if flow.sourceRef == node_id)

    def incoming_count(self, node_id: str) -> int:
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
        for source, target in zip(chain, chain[1:]):
            self.add(source, target)

    def apply_edge_overlay(self) -> None:
        for (origin_source, origin_target), edge in self.edges_by_original.items():
            source = self._compiled_by_original.get(origin_source)
            target = self._compiled_by_original.get(origin_target)
            if source is None or target is None:
                continue
            flow = self._flow_by_pair.get((source, target))
            if flow is None:
                continue
            self._enrich(
                flow,
                name=edge.label.strip() or None,
                source_refs=[source_ref_id("flow_edges", edge.id)],
            )
            if edge.condition and source in self.gateway_ids and not flow.conditionExpression:
                flow.conditionExpression = edge.condition

    @staticmethod
    def _enrich(
        flow: BPMNSequenceFlow,
        *,
        name: str | None = None,
        documentation: str | None = None,
        source_refs: list[str] | None = None,
    ) -> None:
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
    index: dict[tuple[str, str], ProcessFlowEdge] = {}
    for edge in process.flow_edges:
        if edge.kind == "sequence":
            index.setdefault((edge.source_id, edge.target_id), edge)
    return index
