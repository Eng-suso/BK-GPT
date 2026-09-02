from backend.bpmn import resolve_pool_topology
from backend.process_understanding import (
    BpmnLaneCandidate,
    BpmnMessageFlowCandidate,
    BpmnParticipantTopology,
    BpmnPoolCandidate,
    ProcessActor,
    ProcessParticipant,
)


def _actor(actor_id: str, kind: str = "role") -> ProcessActor:
    return ProcessActor(id=actor_id, label=actor_id.replace("Actor_", ""), kind=kind)


def test_explicit_topology_resolves_primary_pool_and_message_flow():
    actors = [
        _actor("Actor_Richiedente", "person"),
        _actor("Actor_Patronato", "organization"),
        _actor("Actor_INPS", "organization"),
    ]
    topology = BpmnParticipantTopology(
        pools=[
            BpmnPoolCandidate(
                id="Pool_Patronato",
                label="Canale patronato",
                participant_id="Participant_Patronato",
                actor_ids=["Actor_Richiedente", "Actor_Patronato"],
            ),
            BpmnPoolCandidate(
                id="Pool_INPS",
                label="INPS",
                participant_id="Participant_INPS",
                actor_ids=["Actor_INPS"],
                is_external=True,
                rendering_intent="black_box",
            ),
        ],
        lanes=[
            BpmnLaneCandidate(
                id="Lane_Richiedente",
                label="Richiedente",
                pool_id="Pool_Patronato",
                actor_ids=["Actor_Richiedente"],
            ),
            BpmnLaneCandidate(
                id="Lane_Patronato",
                label="Patronato",
                pool_id="Pool_Patronato",
                actor_ids=["Actor_Patronato"],
            ),
        ],
        message_flows=[
            BpmnMessageFlowCandidate(
                id="MessageFlow_Domanda",
                label="Domanda a INPS",
                from_participant_id="Participant_Patronato",
                to_participant_id="Participant_INPS",
                source_ref="Task_InoltraDomanda",
                artifact="Domanda pensione",
            )
        ],
        black_box_participant_ids=["Participant_INPS"],
    )

    resolved = resolve_pool_topology(topology=topology, participants=[], actors=actors)

    assert resolved.is_collaboration is True
    primary = resolved.primary_pool
    assert primary is not None and primary.key == "Pool_Patronato"
    assert primary.rendering == "expanded"
    external = [pool for pool in resolved.pools if not pool.is_primary]
    assert [pool.key for pool in external] == ["Pool_INPS"]
    assert external[0].is_external is True
    assert external[0].rendering == "black_box"
    assert resolved.pool_for_actor("Actor_Richiedente") == "Pool_Patronato"
    assert resolved.pool_for_actor("Actor_INPS") == "Pool_INPS"
    assert {lane.key for lane in resolved.lanes} == {"Lane_Richiedente", "Lane_Patronato"}
    flow = resolved.message_flows[0]
    assert flow.from_pool_key == "Pool_Patronato"
    assert flow.to_pool_key == "Pool_INPS"
    assert flow.from_node_ref == "Task_InoltraDomanda"


def test_topology_flags_unknown_actor_and_lane_pool():
    topology = BpmnParticipantTopology(
        pools=[
            BpmnPoolCandidate(id="Pool_A", label="A", actor_ids=["Actor_Known", "Actor_Ghost"]),
            BpmnPoolCandidate(id="Pool_B", label="B", actor_ids=["Actor_Other"], is_external=True),
        ],
        lanes=[BpmnLaneCandidate(id="Lane_X", label="X", pool_id="Pool_Missing")],
    )
    resolved = resolve_pool_topology(
        topology=topology,
        participants=[],
        actors=[_actor("Actor_Known"), _actor("Actor_Other")],
    )

    assert any("Actor_Ghost" in warning for warning in resolved.warnings)
    assert any("Pool_Missing" in warning for warning in resolved.warnings)
    assert resolved.lanes == ()


def test_participant_classification_builds_pools_without_explicit_topology():
    participants = [
        ProcessParticipant(
            id="Participant_Ufficio",
            label="Ufficio interno",
            actor_id="Actor_Ufficio",
            kind="role",
            bpmn_container="lane",
            parent_pool_id="Participant_Azienda",
        ),
        ProcessParticipant(
            id="Participant_Azienda",
            label="Azienda",
            actor_id="Actor_Ufficio",
            kind="organization",
            bpmn_container="pool",
        ),
        ProcessParticipant(
            id="Participant_Cliente",
            label="Cliente",
            actor_id="Actor_Cliente",
            kind="individual",
            bpmn_container="black_box",
        ),
    ]
    resolved = resolve_pool_topology(
        topology=None,
        participants=participants,
        actors=[_actor("Actor_Ufficio"), _actor("Actor_Cliente", "external_party")],
    )

    assert resolved.is_collaboration is True
    primary = resolved.primary_pool
    assert primary is not None and primary.key == "Participant_Azienda"
    assert resolved.pool_for_actor("Actor_Ufficio") == "Participant_Azienda"
    assert resolved.pool_for_actor("Actor_Cliente") == "Participant_Cliente"
    black_box = next(pool for pool in resolved.pools if pool.key == "Participant_Cliente")
    assert black_box.is_external is True
    assert black_box.rendering == "black_box"


def test_external_actor_fallback_creates_black_box_pool():
    resolved = resolve_pool_topology(
        topology=None,
        participants=[],
        actors=[
            _actor("Actor_Ops", "team"),
            _actor("Actor_Finance", "team"),
            _actor("Actor_Supplier", "external_party"),
        ],
    )

    assert resolved.is_collaboration is True
    primary = resolved.primary_pool
    assert primary is not None and primary.is_primary
    assert set(primary.actor_ids) == {"Actor_Ops", "Actor_Finance"}
    supplier = next(pool for pool in resolved.pools if pool.key == "Actor_Supplier")
    assert supplier.is_external and supplier.rendering == "black_box"


def test_single_party_process_is_not_a_collaboration():
    resolved = resolve_pool_topology(
        topology=None,
        participants=[],
        actors=[_actor("Actor_Ops", "team"), _actor("Actor_Finance", "team")],
    )

    assert resolved.pools == ()
    assert resolved.is_collaboration is False
    assert resolved.primary_pool is None
