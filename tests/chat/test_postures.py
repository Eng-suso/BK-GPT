"""La postura orienta il router e torna alla UI; non vieta mai una scrittura."""

from __future__ import annotations

from backend.graphs.routing_contracts import (
    ConsultingRoutingDecision,
    ProcessRoutingDecision,
    _settle_posture,
    posture_prompt_block,
)
from backend.services.agent_runtime import detected_posture


def test_auto_asks_the_router_to_choose_among_the_chat_postures():
    block = posture_prompt_block("process", "auto")
    assert "automatica" in block
    for posture in ("discover", "improve", "validate"):
        assert f"- {posture}:" in block
    assert "- desk:" not in block


def test_a_forced_posture_is_stated_and_wins_over_what_the_model_says():
    assert "Postura scelta dal consulente: prepare" in posture_prompt_block("consultant", "prepare")

    decision = ConsultingRoutingDecision(route="direct", posture="desk")
    _settle_posture(decision, "consultant", "prepare")
    assert decision.posture == "prepare"


def test_a_detected_posture_from_another_chat_is_dropped():
    decision = ProcessRoutingDecision(route="direct", posture="map")
    _settle_posture(decision, "process", "auto")
    assert decision.posture is None

    decision = ProcessRoutingDecision(route="discovery", posture="discover")
    _settle_posture(decision, "process", "auto")
    assert decision.posture == "discover"


def test_the_runtime_finds_the_posture_in_a_subgraph_update():
    assert detected_posture({"process_subgraph": {"detected_posture": "improve", "messages": []}}) == "improve"
    assert detected_posture({"consult_router": {"detected_posture": None}}) is None
    assert detected_posture(("not", "a", "dict")) is None


def test_a_routed_turn_streams_its_posture_to_the_ui(monkeypatch):
    from backend.services import agent_runtime

    class FakeAgent:
        def stream(self, state, config=None, stream_mode=None):
            yield ("updates", {"process_subgraph": {"detected_posture": "validate"}})

    monkeypatch.setattr(agent_runtime.settings, "delir_fake_llm", False)
    monkeypatch.setattr(agent_runtime, "get_agent", lambda *args, **kwargs: FakeAgent())

    events = list(
        agent_runtime.stream_agent_events(
            thread_id="t-posture-1",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "questo To-Be regge?"}],
            scope=None,
            chat_mode="agent",
            posture="auto",
            emit_activity=False,
        )
    )

    postures = [
        event.payload["payload"]["posture"]
        for event in events
        if event.type == "trace" and event.payload.get("event_type") == "posture"
    ]
    assert postures == ["validate"]


def test_the_chosen_reasoning_selects_the_agent_build(monkeypatch):
    from backend.services import agent_runtime

    seen: dict = {}

    class FakeAgent:
        def stream(self, state, config=None, stream_mode=None):
            return iter(())

    def fake_get_agent(model_name=None, scope_type=None, reasoning_effort=None):
        seen["reasoning_effort"] = reasoning_effort
        return FakeAgent()

    monkeypatch.setattr(agent_runtime.settings, "delir_fake_llm", False)
    monkeypatch.setattr(agent_runtime, "get_agent", fake_get_agent)
    list(
        agent_runtime.stream_agent_events(
            thread_id="t-effort-1",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "analizza"}],
            scope=None,
            chat_mode="agent",
            reasoning_effort="high",
            emit_activity=False,
        )
    )
    assert seen["reasoning_effort"] == "high"
