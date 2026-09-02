"""Deterministic resolution of BPMN collaboration topology.

`ProcessUnderstanding` carries three overlapping descriptions of "who takes
part": `actors`, `participants` (with a `bpmn_container` classification) and an
optional `bpmn_topology` (explicit pool / lane / message-flow candidates from the
modelling LLM). The BPMN compiler needs a single normalised view of that:

- which pools exist,
- which one is the modelled ("primary") process,
- which actors sit in which pool,
- which lanes partition the primary pool,
- which message flows cross pool boundaries.

This module owns that reconciliation as pure functions over the source model.
No id allocation, no XML, no side effects: the compiler turns the result into
`BPMNParticipant` / `BPMNMessageFlow` / `BPMNLane` records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from backend.process_understanding import (
    BpmnParticipantTopology,
    ProcessActor,
    ProcessParticipant,
)

PoolRendering = Literal["expanded", "black_box", "out_of_scope"]

_EXTERNAL_ACTOR_KINDS = {"external_party"}


@dataclass(frozen=True)
class ResolvedLane:
    key: str
    label: str
    pool_key: str
    actor_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedPool:
    key: str
    label: str
    actor_ids: tuple[str, ...]
    is_primary: bool
    is_external: bool
    rendering: PoolRendering
    participant_id: str | None = None


@dataclass(frozen=True)
class ResolvedMessageFlow:
    key: str
    label: str
    from_pool_key: str | None
    to_pool_key: str | None
    from_node_ref: str | None
    to_node_ref: str | None
    artifact: str | None


@dataclass
class PoolTopology:
    pools: tuple[ResolvedPool, ...]
    lanes: tuple[ResolvedLane, ...]
    message_flows: tuple[ResolvedMessageFlow, ...]
    actor_to_pool: dict[str, str]
    warnings: list[str] = field(default_factory=list)

    @property
    def is_collaboration(self) -> bool:
        return len(self.pools) >= 2

    @property
    def primary_pool(self) -> ResolvedPool | None:
        return next((pool for pool in self.pools if pool.is_primary), None)

    def pool_for_actor(self, actor_id: str) -> str | None:
        return self.actor_to_pool.get(actor_id)


def resolve_pool_topology(
    *,
    topology: BpmnParticipantTopology | None,
    participants: list[ProcessParticipant],
    actors: list[ProcessActor],
) -> PoolTopology:
    """Reconcile pool/lane/message-flow intent into one normalised topology.

    Precedence: an explicit `bpmn_topology.pools` wins; otherwise pools are
    derived from `participants` whose `bpmn_container` is pool-like; otherwise
    from `actors` classified as external parties. When fewer than two pools can
    be identified the result still carries lanes/message-flows but
    `is_collaboration` is False and the compiler keeps single-process rendering.
    """
    actor_ids = {actor.id for actor in actors if actor.id}
    if topology is not None and topology.pools:
        return _resolve_from_topology(topology, participants, actors, actor_ids)
    if any(_participant_is_pool(item) for item in participants):
        return _resolve_from_participants(participants, actors, actor_ids)
    return _resolve_from_actors(actors, actor_ids)


# --- topology-driven -------------------------------------------------------


def _resolve_from_topology(
    topology: BpmnParticipantTopology,
    participants: list[ProcessParticipant],
    actors: list[ProcessActor],
    actor_ids: set[str],
) -> PoolTopology:
    warnings: list[str] = []
    external_participant_ids = set(topology.black_box_participant_ids) | set(
        topology.out_of_scope_participant_ids
    )
    participant_by_id = {item.id: item for item in participants}

    raw_pools: list[ResolvedPool] = []
    for pool in topology.pools:
        known_actor_ids = tuple(
            actor_id for actor_id in pool.actor_ids if actor_id in actor_ids
        )
        unknown = [actor_id for actor_id in pool.actor_ids if actor_id not in actor_ids]
        if unknown:
            warnings.append(
                f"Pool '{pool.label}' cita attori non definiti: {', '.join(sorted(unknown))}."
            )
        is_external = bool(pool.is_external) or (
            pool.participant_id in external_participant_ids
        )
        rendering: PoolRendering = pool.rendering_intent
        if pool.participant_id in topology.out_of_scope_participant_ids:
            rendering = "out_of_scope"
        elif pool.participant_id in topology.black_box_participant_ids:
            rendering = "black_box"
        raw_pools.append(
            ResolvedPool(
                key=pool.id,
                label=pool.label or pool.id,
                actor_ids=known_actor_ids,
                is_primary=False,
                is_external=is_external,
                rendering=rendering,
                participant_id=pool.participant_id,
            )
        )

    pools = _mark_primary(raw_pools, participant_by_id)
    actor_to_pool = _actor_pool_index(pools)

    lanes: list[ResolvedLane] = []
    pool_keys = {pool.key for pool in pools}
    for lane in topology.lanes:
        if lane.pool_id not in pool_keys:
            warnings.append(
                f"Lane '{lane.label}' collegata a pool non definito: {lane.pool_id}."
            )
            continue
        lanes.append(
            ResolvedLane(
                key=lane.id,
                label=lane.label or lane.id,
                pool_key=lane.pool_id,
                actor_ids=tuple(
                    actor_id for actor_id in lane.actor_ids if actor_id in actor_ids
                ),
            )
        )

    message_flows = _resolve_message_flows(
        topology,
        pool_by_participant={
            pool.participant_id: pool.key for pool in pools if pool.participant_id
        },
        pool_by_actor=actor_to_pool,
        warnings=warnings,
    )
    return PoolTopology(
        pools=tuple(pools),
        lanes=tuple(lanes),
        message_flows=message_flows,
        actor_to_pool=actor_to_pool,
        warnings=warnings,
    )


def _resolve_message_flows(
    topology: BpmnParticipantTopology,
    *,
    pool_by_participant: dict[str, str],
    pool_by_actor: dict[str, str],
    warnings: list[str],
) -> tuple[ResolvedMessageFlow, ...]:
    resolved: list[ResolvedMessageFlow] = []
    for flow in topology.message_flows:
        from_pool = _pool_for_message_end(
            flow.from_participant_id, flow.from_actor_id, pool_by_participant, pool_by_actor
        )
        to_pool = _pool_for_message_end(
            flow.to_participant_id, flow.to_actor_id, pool_by_participant, pool_by_actor
        )
        if from_pool is None and to_pool is None:
            warnings.append(
                f"Message flow '{flow.label}' senza pool sorgente o destinazione risolvibile."
            )
        resolved.append(
            ResolvedMessageFlow(
                key=flow.id,
                label=flow.label or flow.id,
                from_pool_key=from_pool,
                to_pool_key=to_pool,
                from_node_ref=flow.source_ref,
                to_node_ref=flow.target_ref,
                artifact=flow.artifact,
            )
        )
    return tuple(resolved)


def _pool_for_message_end(
    participant_id: str | None,
    actor_id: str | None,
    pool_by_participant: dict[str, str],
    pool_by_actor: dict[str, str],
) -> str | None:
    if participant_id and participant_id in pool_by_participant:
        return pool_by_participant[participant_id]
    if actor_id and actor_id in pool_by_actor:
        return pool_by_actor[actor_id]
    return None


# --- participant-driven --------------------------------------------------


def _participant_is_pool(participant: ProcessParticipant) -> bool:
    return participant.bpmn_container in {"pool", "black_box"}


def _resolve_from_participants(
    participants: list[ProcessParticipant],
    actors: list[ProcessActor],
    actor_ids: set[str],
) -> PoolTopology:
    warnings: list[str] = []
    actor_by_id = {actor.id: actor for actor in actors}
    lane_participants = [
        item for item in participants if item.bpmn_container == "lane"
    ]

    raw_pools: list[ResolvedPool] = []
    for participant in participants:
        if not _participant_is_pool(participant):
            continue
        pool_actor_ids = tuple(
            actor_id
            for actor_id in ([participant.actor_id] if participant.actor_id else [])
            if actor_id in actor_ids
        )
        rendering: PoolRendering = (
            "black_box"
            if participant.bpmn_container == "black_box"
            else "expanded"
        )
        actor = actor_by_id.get(participant.actor_id or "")
        is_external = participant.bpmn_container == "black_box" or (
            actor is not None and actor.kind in _EXTERNAL_ACTOR_KINDS
        )
        raw_pools.append(
            ResolvedPool(
                key=participant.id,
                label=participant.label or participant.id,
                actor_ids=pool_actor_ids,
                is_primary=False,
                is_external=is_external,
                rendering=rendering,
                participant_id=participant.id,
            )
        )

    # Lane participants that name a parent pool attach their actor to that pool.
    for lane_participant in lane_participants:
        parent = lane_participant.parent_pool_id
        if not parent or not lane_participant.actor_id:
            continue
        for index, pool in enumerate(raw_pools):
            if pool.key == parent and lane_participant.actor_id in actor_ids:
                raw_pools[index] = ResolvedPool(
                    key=pool.key,
                    label=pool.label,
                    actor_ids=tuple(
                        dict.fromkeys((*pool.actor_ids, lane_participant.actor_id))
                    ),
                    is_primary=pool.is_primary,
                    is_external=pool.is_external,
                    rendering=pool.rendering,
                    participant_id=pool.participant_id,
                )

    participant_by_id = {item.id: item for item in participants}
    pools = _mark_primary(raw_pools, participant_by_id)
    actor_to_pool = _actor_pool_index(pools)

    lanes = tuple(
        ResolvedLane(
            key=lane_participant.id,
            label=lane_participant.label or lane_participant.id,
            pool_key=lane_participant.parent_pool_id or _primary_key(pools),
            actor_ids=(lane_participant.actor_id,)
            if lane_participant.actor_id in actor_ids
            else (),
        )
        for lane_participant in lane_participants
        if (lane_participant.parent_pool_id or _primary_key(pools))
    )
    return PoolTopology(
        pools=tuple(pools),
        lanes=lanes,
        message_flows=(),
        actor_to_pool=actor_to_pool,
        warnings=warnings,
    )


# --- actor-driven -------------------------------------------------------


def _resolve_from_actors(
    actors: list[ProcessActor],
    actor_ids: set[str],
) -> PoolTopology:
    external = [actor for actor in actors if actor.kind in _EXTERNAL_ACTOR_KINDS]
    internal = [actor for actor in actors if actor.kind not in _EXTERNAL_ACTOR_KINDS]
    if not external or not internal:
        return PoolTopology(
            pools=(), lanes=(), message_flows=(), actor_to_pool={}, warnings=[]
        )

    primary = ResolvedPool(
        key="__primary__",
        label="Processo interno",
        actor_ids=tuple(actor.id for actor in internal),
        is_primary=True,
        is_external=False,
        rendering="expanded",
    )
    pools = [primary]
    for actor in external:
        pools.append(
            ResolvedPool(
                key=actor.id,
                label=actor.label or actor.id,
                actor_ids=(actor.id,),
                is_primary=False,
                is_external=True,
                rendering="black_box",
            )
        )
    return PoolTopology(
        pools=tuple(pools),
        lanes=(),
        message_flows=(),
        actor_to_pool=_actor_pool_index(pools),
        warnings=[],
    )


# --- shared helpers ----------------------------------------------------


def _mark_primary(
    pools: list[ResolvedPool],
    participant_by_id: dict[str, ProcessParticipant],
) -> list[ResolvedPool]:
    if not pools:
        return []

    def internal_actor_count(pool: ResolvedPool) -> int:
        return len(pool.actor_ids) if not pool.is_external else 0

    ranked = sorted(
        range(len(pools)),
        key=lambda index: (
            pools[index].rendering == "expanded" and not pools[index].is_external,
            internal_actor_count(pools[index]),
            -index,
        ),
        reverse=True,
    )
    primary_index = ranked[0]
    result: list[ResolvedPool] = []
    for index, pool in enumerate(pools):
        is_primary = index == primary_index
        result.append(
            ResolvedPool(
                key=pool.key,
                label=pool.label,
                actor_ids=pool.actor_ids,
                is_primary=is_primary,
                is_external=pool.is_external and not is_primary,
                rendering="expanded" if is_primary else pool.rendering,
                participant_id=pool.participant_id,
            )
        )
    return result


def _actor_pool_index(pools: list[ResolvedPool]) -> dict[str, str]:
    index: dict[str, str] = {}
    for pool in pools:
        for actor_id in pool.actor_ids:
            index.setdefault(actor_id, pool.key)
    return index


def _primary_key(pools: list[ResolvedPool]) -> str:
    primary = next((pool for pool in pools if pool.is_primary), None)
    return primary.key if primary else (pools[0].key if pools else "__primary__")
