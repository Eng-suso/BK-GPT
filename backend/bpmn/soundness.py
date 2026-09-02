"""Deterministic control-flow analysis of a compiled `BPMNSemanticModel`.

`validate_bpmn_semantic_model` answers "is this well-formed BPMN?" (dangling
refs, gateway arity). This module answers the harder question the OMG spec and
workflow-net theory care about: "is the control flow *sound*?" — every node
reachable from a start, every node able to reach an end, no uncontrolled
parallel split from a plain activity, no gateway that both splits and joins.

Pure functions, hand-rolled graph traversal, no external dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from backend.bpmn.models import BPMNSemanticModel

IssueCode = Literal[
    "no_start_event",
    "no_end_event",
    "multiple_start_events",
    "unreachable_node",
    "dead_end_node",
    "implicit_parallel_split",
    "uncontrolled_merge",
    "gateway_splits_and_joins",
    "idle_gateway",
    "parallel_split_without_join",
]

_GATEWAY_TYPES = {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway"}


@dataclass(frozen=True)
class ControlFlowIssue:
    code: IssueCode
    node_id: str | None
    node_name: str | None
    message: str


@dataclass
class ControlFlowReport:
    errors: list[ControlFlowIssue] = field(default_factory=list)
    warnings: list[ControlFlowIssue] = field(default_factory=list)
    reachable_node_ids: set[str] = field(default_factory=set)
    coreachable_node_ids: set[str] = field(default_factory=set)

    @property
    def is_sound(self) -> bool:
        return not self.errors

    def messages(self) -> list[str]:
        return [f"Soundness: {issue.message}" for issue in (*self.errors, *self.warnings)]


def analyze_control_flow(model: BPMNSemanticModel) -> ControlFlowReport:
    report = ControlFlowReport()
    nodes_by_id = {node.id: node for node in model.flowNodes}

    successors: dict[str, list[str]] = {node_id: [] for node_id in nodes_by_id}
    predecessors: dict[str, list[str]] = {node_id: [] for node_id in nodes_by_id}
    out_degree: dict[str, int] = {node_id: 0 for node_id in nodes_by_id}
    in_degree: dict[str, int] = {node_id: 0 for node_id in nodes_by_id}
    for flow in model.sequenceFlows:
        if flow.sourceRef not in nodes_by_id or flow.targetRef not in nodes_by_id:
            continue
        successors[flow.sourceRef].append(flow.targetRef)
        predecessors[flow.targetRef].append(flow.sourceRef)
        out_degree[flow.sourceRef] += 1
        in_degree[flow.targetRef] += 1

    starts = [node.id for node in model.flowNodes if node.type == "startEvent"]
    ends = [node.id for node in model.flowNodes if node.type == "endEvent"]
    if not starts:
        report.errors.append(ControlFlowIssue("no_start_event", None, None, "il processo non ha un evento iniziale."))
    if not ends:
        report.errors.append(ControlFlowIssue("no_end_event", None, None, "il processo non ha un evento finale."))
    if len(starts) > 1:
        report.warnings.append(
            ControlFlowIssue(
                "multiple_start_events", None, None,
                f"il processo ha {len(starts)} eventi iniziali: verificare che sia voluto.",
            )
        )

    boundary_host: dict[str, str | None] = {
        node.id: node.attachedToRef for node in model.flowNodes if node.type == "boundaryEvent"
    }

    # A boundary event is reachable once its host is; its handler subtree can in
    # turn make another host reachable (nested boundary events), so iterate to a
    # fixpoint rather than a single flowNodes-order pass.
    reachable = _traverse(starts, successors)
    grew = True
    while grew:
        grew = False
        for boundary_id, host in boundary_host.items():
            if host in reachable and boundary_id not in reachable:
                reachable |= _traverse([boundary_id], successors)
                grew = True
    report.reachable_node_ids = reachable

    coreachable = _traverse(ends, predecessors)
    grew = True
    while grew:
        grew = False
        for boundary_id, host in boundary_host.items():
            if boundary_id in coreachable and host in nodes_by_id and host not in coreachable:
                coreachable |= _traverse([host], predecessors)
                grew = True
    report.coreachable_node_ids = coreachable

    for node in model.flowNodes:
        if node.type == "boundaryEvent":
            continue
        if node.id not in reachable:
            report.errors.append(
                ControlFlowIssue("unreachable_node", node.id, node.name, f"'{node.name}' non e' raggiungibile dall'inizio.")
            )
        if node.id not in coreachable and node.type != "endEvent":
            report.errors.append(
                ControlFlowIssue("dead_end_node", node.id, node.name, f"'{node.name}' non puo' raggiungere una fine del processo.")
            )

        if node.type in _GATEWAY_TYPES:
            _classify_gateway(node, in_degree[node.id], out_degree[node.id], report)
            continue

        if out_degree[node.id] > 1 and node.type != "endEvent":
            report.errors.append(
                ControlFlowIssue(
                    "implicit_parallel_split", node.id, node.name,
                    f"'{node.name}' ha {out_degree[node.id]} frecce in uscita senza gateway: "
                    "in BPMN e' uno split parallelo implicito, serve un gateway esplicito.",
                )
            )
        if in_degree[node.id] > 1 and node.type != "endEvent":
            report.warnings.append(
                ControlFlowIssue(
                    "uncontrolled_merge", node.id, node.name,
                    f"'{node.name}' e' un merge non controllato ({in_degree[node.id]} ingressi): "
                    "si attiva a ogni token in arrivo, verificare se serve un gateway di join.",
                )
            )

    _check_parallel_balance(model, in_degree, out_degree, report)
    return report


def _classify_gateway(node, in_deg: int, out_deg: int, report: ControlFlowReport) -> None:
    if in_deg <= 1 and out_deg <= 1:
        report.warnings.append(
            ControlFlowIssue("idle_gateway", node.id, node.name, f"il gateway '{node.name}' non divide ne' unisce il flusso.")
        )
    elif in_deg > 1 and out_deg > 1:
        report.errors.append(
            ControlFlowIssue(
                "gateway_splits_and_joins", node.id, node.name,
                f"il gateway '{node.name}' unisce e divide allo stesso tempo: separare join e split.",
            )
        )


def _check_parallel_balance(model, in_degree, out_degree, report: ControlFlowReport) -> None:
    parallel_splits = 0
    parallel_joins = 0
    for node in model.flowNodes:
        if node.type != "parallelGateway":
            continue
        if out_degree[node.id] > 1 and in_degree[node.id] <= 1:
            parallel_splits += 1
        elif in_degree[node.id] > 1 and out_degree[node.id] <= 1:
            parallel_joins += 1
    if parallel_splits > parallel_joins:
        report.warnings.append(
            ControlFlowIssue(
                "parallel_split_without_join", None, None,
                f"{parallel_splits} split paralleli ma solo {parallel_joins} join: "
                "rami paralleli senza sincronizzazione possono lasciare lavoro in sospeso.",
            )
        )


def _traverse(seeds: list[str], adjacency: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, []))
    return seen
