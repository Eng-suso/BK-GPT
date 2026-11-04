"""A message flow only ever joins two different pools.

Gemini extracted, for the Facility golden case, a step of the "Direzione" pool
that sends a message to "Direzione" itself. BPMN forbids it, and the layout
could not draw it either: the route had to leave a shape from inside the pool
it was heading for.
"""

from __future__ import annotations

from backend.bpmn.collaboration import CollaborationLayer, MessageFlowSpec, finalize_message_flows
from backend.bpmn.models import BPMNParticipant


def _spec(**kwargs) -> MessageFlowSpec:
    fields = {"from_pool_key": None, "to_pool_key": None, "from_node_ref": None, "to_node_ref": None, "artifact": None}
    return MessageFlowSpec(**{**fields, **kwargs})


def _layer(*specs: MessageFlowSpec) -> CollaborationLayer:
    return CollaborationLayer(
        collaboration_id="Collaboration_P",
        participants=[
            BPMNParticipant(id="Participant_direzione", name="Direzione", processRef="P"),
            BPMNParticipant(id="Participant_fornitore", name="Fornitore", processRef=None, isExternal=True),
        ],
        lanes=[],
        lane_by_actor_id={},
        message_flow_specs=list(specs),
        pool_id_by_key={"direzione": "Participant_direzione", "fornitore": "Participant_fornitore"},
        external_actor_ids=set(),
    )


def _finalize(layer: CollaborationLayer) -> tuple[list, list[str]]:
    warnings: list[str] = []
    flows = finalize_message_flows(
        collaboration=layer,
        step_node_by_original_id={"step_richiesta": "Task_richiesta", "step_ordine": "Task_ordine"},
        node_ids={"Task_richiesta", "Task_ordine"},
        used_ids=set(),
        warnings=warnings,
    )
    return flows, warnings


def test_a_step_cannot_message_the_pool_it_belongs_to():
    flows, warnings = _finalize(
        _layer(_spec(key="m1", label="Richiesta", from_node_ref="step_richiesta", to_pool_key="direzione"))
    )

    assert flows == []
    assert any("stesso pool" in warning for warning in warnings), "the consultant is told why it is gone"


def test_two_steps_of_the_one_process_cannot_exchange_a_message():
    flows, _ = _finalize(
        _layer(_spec(key="m1", label="Inoltro", from_node_ref="step_richiesta", to_node_ref="step_ordine"))
    )

    assert flows == []


def test_a_step_messaging_an_external_pool_is_kept():
    flows, warnings = _finalize(
        _layer(_spec(key="m1", label="Ordine", from_node_ref="step_ordine", to_pool_key="fornitore"))
    )

    assert [(flow.sourceRef, flow.targetRef) for flow in flows] == [("Task_ordine", "Participant_fornitore")]
    assert warnings == []


def test_a_reply_from_an_external_pool_to_a_step_is_kept():
    flows, _ = _finalize(
        _layer(_spec(key="m1", label="Conferma", from_pool_key="fornitore", to_node_ref="step_ordine"))
    )

    assert [(flow.sourceRef, flow.targetRef) for flow in flows] == [("Participant_fornitore", "Task_ordine")]
