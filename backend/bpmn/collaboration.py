"""Pools, lanes and message flows: turning the resolved topology into
`BPMNParticipant` / `BPMNLane` / `BPMNMessageFlow` records.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.bpmn._helpers import json_documentation, source_ref_id, xml_id
from backend.bpmn.models import BPMNFlowNode, BPMNLane, BPMNMessageFlow, BPMNParticipant
from backend.bpmn.topology import PoolTopology, ResolvedPool, resolve_pool_topology
from backend.process_understanding import ProcessActor, ProcessStep, ProcessUnderstanding

# Upper bound on lanes rendered in the primary pool. Kept identical across every
# lane-building path so `actor_lane_map` never points at a lane that was dropped.
_MAX_LANES = 8


@dataclass
class MessageFlowSpec:
    key: str
    label: str
    from_pool_key: str | None
    to_pool_key: str | None
    from_node_ref: str | None
    to_node_ref: str | None
    artifact: str | None


@dataclass
class CollaborationLayer:
    collaboration_id: str | None
    participants: list[BPMNParticipant]
    lanes: list[BPMNLane]
    lane_by_actor_id: dict[str, str]
    message_flow_specs: list[MessageFlowSpec]
    pool_id_by_key: dict[str, str]
    external_actor_ids: set[str]
    warnings: list[str] = field(default_factory=list)


def build_collaboration_layer(
    process: ProcessUnderstanding,
    safe_process_id: str,
    used_ids: set[str],
) -> CollaborationLayer:
    resolved = resolve_pool_topology(
        topology=process.bpmn_topology,
        participants=process.participants,
        actors=process.actors,
    )
    if not resolved.is_collaboration or resolved.primary_pool is None:
        lanes = build_lanes(process.actors, used_ids)
        return CollaborationLayer(
            collaboration_id=None,
            participants=[],
            lanes=lanes,
            lane_by_actor_id=lane_by_actor_id(process.actors, lanes),
            message_flow_specs=[],
            pool_id_by_key={},
            external_actor_ids=set(),
            warnings=list(resolved.warnings),
        )

    primary = resolved.primary_pool
    pool_id_by_key: dict[str, str] = {}
    participants: list[BPMNParticipant] = []
    for pool in resolved.pools:
        participant_id = xml_id(pool.participant_id or pool.label or pool.key, "Participant", used_ids)
        pool_id_by_key[pool.key] = participant_id
        participants.append(
            BPMNParticipant(
                id=participant_id,
                name=pool.label,
                processRef=safe_process_id if pool.is_primary else None,
                isExternal=pool.is_external and not pool.is_primary,
                rendering=pool.rendering,
                sourceRefs=[source_ref_id("bpmn_topology", pool.key)],
            )
        )

    lanes, actor_lane_map = _lanes_for_primary_pool(resolved, primary, process.actors, used_ids)
    external_actor_ids = {
        actor_id
        for actor_id, pool_key in resolved.actor_to_pool.items()
        if pool_key != primary.key
    }
    specs = [
        MessageFlowSpec(
            key=flow.key,
            label=flow.label,
            from_pool_key=flow.from_pool_key,
            to_pool_key=flow.to_pool_key,
            from_node_ref=flow.from_node_ref,
            to_node_ref=flow.to_node_ref,
            artifact=flow.artifact,
        )
        for flow in resolved.message_flows
    ]
    return CollaborationLayer(
        collaboration_id=xml_id(f"Collaboration_{safe_process_id}", "Collaboration", used_ids),
        participants=participants,
        lanes=lanes,
        lane_by_actor_id=actor_lane_map,
        message_flow_specs=specs,
        pool_id_by_key=pool_id_by_key,
        external_actor_ids=external_actor_ids,
        warnings=list(resolved.warnings),
    )


def _lanes_for_primary_pool(
    resolved: PoolTopology,
    primary: ResolvedPool,
    actors: list[ProcessActor],
    used_ids: set[str],
) -> tuple[list[BPMNLane], dict[str, str]]:
    actor_lane_map: dict[str, str] = {}
    lanes: list[BPMNLane] = []
    primary_lanes = [lane for lane in resolved.lanes if lane.pool_key == primary.key]
    if primary_lanes:
        for lane in primary_lanes:
            lane_id = xml_id(lane.key or lane.label, "Lane", used_ids)
            lanes.append(
                BPMNLane(
                    id=lane_id,
                    name=lane.label,
                    sourceRefs=[source_ref_id("bpmn_topology", lane.key)],
                )
            )
            for actor_id in lane.actor_ids:
                actor_lane_map.setdefault(actor_id, lane_id)
        return lanes, actor_lane_map

    actor_labels = {actor.id: actor.label for actor in actors}
    for actor_id in primary.actor_ids:
        label = actor_labels.get(actor_id, actor_id)
        if not label.strip():
            continue
        if len(lanes) >= _MAX_LANES:
            break
        lane_id = xml_id(actor_id or label, "Lane", used_ids)
        lanes.append(BPMNLane(id=lane_id, name=label, sourceRefs=[source_ref_id("actors", actor_id)]))
        actor_lane_map[actor_id] = lane_id
    return lanes, actor_lane_map


def build_lanes(actors: list[ProcessActor], used_ids: set[str]) -> list[BPMNLane]:
    return [
        BPMNLane(
            id=xml_id(actor.id or actor.label, "Lane", used_ids),
            name=actor.label,
            sourceRefs=[source_ref_id("actors", actor.id)],
        )
        for actor in actors
        if actor.label.strip()
    ][:_MAX_LANES]


def lane_by_actor_id(actors: list[ProcessActor], lanes: list[BPMNLane]) -> dict[str, str]:
    lane_by_source_ref: dict[str, str] = {}
    for lane in lanes:
        for ref in lane.sourceRefs:
            lane_by_source_ref[ref] = lane.id
    return {
        actor.id: lane_by_source_ref[source_ref_id("actors", actor.id)]
        for actor in actors
        if source_ref_id("actors", actor.id) in lane_by_source_ref
    }


def lane_for_step(
    step: ProcessStep,
    actors: list[ProcessActor],
    actor_lane_map: dict[str, str],
) -> str | None:
    for actor_id in step.actor_ids:
        if actor_id in actor_lane_map:
            return actor_lane_map[actor_id]
    return None


def populate_lane_refs(lanes: list[BPMNLane], nodes: list[BPMNFlowNode]) -> None:
    lane_by_id = {lane.id: lane for lane in lanes}
    for node in nodes:
        if node.laneId and node.laneId in lane_by_id and node.id not in lane_by_id[node.laneId].flowNodeRefs:
            lane_by_id[node.laneId].flowNodeRefs.append(node.id)


def step_is_external_only(step: ProcessStep, external_actor_ids: set[str]) -> bool:
    if not external_actor_ids or not step.actor_ids:
        return False
    return all(actor_id in external_actor_ids for actor_id in step.actor_ids)


def finalize_message_flows(
    *,
    collaboration: CollaborationLayer,
    step_node_by_original_id: dict[str, str],
    node_ids: set[str],
    used_ids: set[str],
    warnings: list[str],
) -> list[BPMNMessageFlow]:
    result: list[BPMNMessageFlow] = []
    for spec in collaboration.message_flow_specs:
        source_ref = _message_endpoint(
            spec.from_node_ref, spec.from_pool_key, collaboration, step_node_by_original_id, node_ids
        )
        target_ref = _message_endpoint(
            spec.to_node_ref, spec.to_pool_key, collaboration, step_node_by_original_id, node_ids
        )
        if not source_ref or not target_ref or source_ref == target_ref:
            warnings.append(
                f"Message flow '{spec.label}' non collegato: estremi non risolti nel modello BPMN."
            )
            continue
        result.append(
            BPMNMessageFlow(
                id=xml_id(spec.key or f"MessageFlow_{len(result) + 1}", "MessageFlow", used_ids),
                sourceRef=source_ref,
                targetRef=target_ref,
                name=spec.label,
                documentation=json_documentation(
                    "message_flow", {"artifact": spec.artifact, "label": spec.label}
                ),
                sourceRefs=[source_ref_id("bpmn_topology", spec.key)],
            )
        )
    return result


def _message_endpoint(
    node_ref: str | None,
    pool_key: str | None,
    collaboration: CollaborationLayer,
    step_node_by_original_id: dict[str, str],
    node_ids: set[str],
) -> str | None:
    if node_ref:
        if node_ref in node_ids:
            return node_ref
        mapped = step_node_by_original_id.get(node_ref)
        if mapped:
            return mapped
    if pool_key and pool_key in collaboration.pool_id_by_key:
        return collaboration.pool_id_by_key[pool_key]
    return None
