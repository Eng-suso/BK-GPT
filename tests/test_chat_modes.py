"""The user's chat mode (plan / edit / agent) as a runtime constraint.

The mode is a choice about how much of the workflow the user is handing over. It
arrives from the UI, never from the model, and it is enforced in two places: the
router may only propose capabilities the mode includes, and the writes the mode
forbids are refused where they happen.
"""

import pytest

from backend.agents.chat_mode import (
    WriteNotAllowedInMode,
    active_mode,
    assert_write_allowed,
    bind_active_mode,
)
from backend.agents.primary_scope import agent_scope_state, build_scope_system_prompt
from backend.graphs.canvas_edit.graph import canvas_router_prompt, parse_canvas_router_json
from backend.graphs.process.graph import parse_process_router_json
from backend.graphs.routing_contracts import (
    ALL_CHAT_MODES,
    CAPABILITY_REGISTRY,
    capabilities_for,
)


def test_every_capability_is_available_in_agent_mode():
    # agent mode is the full loop: nothing may be unreachable in it, or the
    # capability would be dead code no user could ever get to.
    for spec in CAPABILITY_REGISTRY.values():
        assert "agent" in spec.modes, f"{spec.id} is unreachable in agent mode"
        assert spec.modes <= ALL_CHAT_MODES, f"{spec.id} declares an unknown mode"


def test_plan_mode_cannot_route_to_a_canvas_edit():
    result = parse_canvas_router_json(
        """
        {
          "route": "patch_edit",
          "confidence": 0.9,
          "suggested_capability": "canvas.patch_edit",
          "reason": "User asked to rename a task."
        }
        """,
        state={
            "chat_mode": "plan",
            "bpmn_model_id": "bpmn-1",
            "effective_bpmn_xml": "<bpmn />",
        },
    )

    assert result["canvas_route"] != "patch_edit"
    assert result["orchestration_status"] == "capability_not_in_mode"
    assert any("not available in plan mode" in item for item in result["blocking_conditions"])


def test_edit_mode_can_apply_a_plan_it_did_not_write():
    """Applying a prepared preview is executing a decision, not re-planning it.

    Construction used to be blocked outside plan/agent, which left a preview the
    user had just approved impossible to apply: "inseriscila nel canvas" came back
    as "what should I insert?". The mode governs the *write*, and the write guard
    in `agents/chat_mode.py` enforces that - plan mode still cannot save.
    """
    result = parse_canvas_router_json(
        """
        {
          "route": "construction",
          "confidence": 0.9,
          "suggested_capability": "canvas.construction",
          "reason": "Apply the prepared preview."
        }
        """,
        state={"chat_mode": "edit", "bpmn_model_id": "bpmn-1"},
    )

    assert result["canvas_route"] == "construction"
    assert result["orchestration_status"] == "authorized"


def test_plan_mode_can_prepare_a_canvas_but_not_save_it():
    # The route is open in plan mode - preparing and previewing is exactly what
    # plan mode is for - and the write is what stays shut.
    result = parse_canvas_router_json(
        """
        {
          "route": "construction",
          "confidence": 0.9,
          "suggested_capability": "canvas.construction",
          "reason": "Prepare the plan."
        }
        """,
        state={"chat_mode": "plan", "bpmn_model_id": "bpmn-1"},
    )
    assert result["canvas_route"] == "construction"

    with bind_active_mode("plan"):
        with pytest.raises(WriteNotAllowedInMode):
            assert_write_allowed("update_bpmn_model")


def test_edit_mode_still_allows_the_edit_it_exists_for():
    result = parse_canvas_router_json(
        """
        {
          "route": "patch_edit",
          "confidence": 0.9,
          "suggested_capability": "canvas.patch_edit",
          "reason": "User asked to rename a task."
        }
        """,
        state={
            "chat_mode": "edit",
            "bpmn_model_id": "bpmn-1",
            "effective_bpmn_xml": "<bpmn />",
        },
    )

    assert result["canvas_route"] == "patch_edit"
    assert result["orchestration_status"] == "authorized"


def test_plan_mode_still_allows_the_planning_work():
    result = parse_process_router_json(
        """
        {
          "route": "discovery",
          "confidence": 0.9,
          "suggested_capability": "process.discovery",
          "process_mode": "discovery",
          "reason": "Map the boundaries first."
        }
        """,
        state={"chat_mode": "plan", "process_id": "proc-1"},
    )

    assert result["process_route"] == "discovery"
    assert result["orchestration_status"] == "authorized"


def test_a_turn_without_a_mode_is_unconstrained():
    # Existing callers that never set a mode must keep the behaviour they had.
    result = parse_canvas_router_json(
        """
        {
          "route": "patch_edit",
          "confidence": 0.9,
          "suggested_capability": "canvas.patch_edit",
          "reason": "User asked to rename a task."
        }
        """,
        state={"bpmn_model_id": "bpmn-1", "effective_bpmn_xml": "<bpmn />"},
    )

    assert result["canvas_route"] == "patch_edit"


def test_the_router_menu_only_lists_what_the_mode_allows():
    plan_menu = canvas_router_prompt("plan")
    edit_menu = canvas_router_prompt("edit")

    # Local canvas edits are the one thing plan mode does not offer.
    assert "canvas.patch_edit" not in plan_menu
    assert "canvas.layout" not in plan_menu
    assert "canvas.patch_edit" in edit_menu
    # Construction is in both: what changes between the modes is whether the
    # result can be written, not whether a plan can be drawn up.
    assert "canvas.construction" in plan_menu
    assert "canvas.construction" in edit_menu


def test_capabilities_for_narrows_by_mode():
    plan_ids = {spec.id for spec in capabilities_for("canvas", "plan")}
    agent_ids = {spec.id for spec in capabilities_for("canvas", "agent")}

    assert plan_ids < agent_ids
    assert "canvas.layout" not in plan_ids


def test_plan_mode_refuses_the_writes_that_would_change_the_process_model():
    # The prompt is not the guard: in plan mode the model must not be able to change
    # the canvas even if it decides that would be helpful.
    with bind_active_mode("plan"):
        assert active_mode() == "plan"
        for operation in ("update_bpmn_model", "approve_bpmn_review", "restore_bpmn_version"):
            with pytest.raises(WriteNotAllowedInMode):
                assert_write_allowed(operation)


def test_plan_mode_still_allows_preparing_and_reworking_the_plan():
    with bind_active_mode("plan"):
        assert_write_allowed("prepare_bpmn_review")
        assert_write_allowed("update_bpmn_review_brief")


def test_edit_mode_allows_canvas_writes_but_not_approval():
    with bind_active_mode("edit"):
        assert_write_allowed("update_bpmn_model")
        with pytest.raises(WriteNotAllowedInMode):
            assert_write_allowed("approve_bpmn_review")


def test_agent_mode_and_no_bound_mode_allow_everything():
    with bind_active_mode("agent"):
        assert_write_allowed("approve_bpmn_review")

    # Outside an agent run - workers, the UI's own approve button, tests - there is
    # no mode to enforce.
    assert active_mode() is None
    assert_write_allowed("approve_bpmn_review")


def test_the_mode_reaches_the_agent_state_and_its_contract_reaches_the_prompt():
    state = agent_scope_state(None, "plan")
    assert state["chat_mode"] == "plan"

    prompt = build_scope_system_prompt({**state, "scope_key": "consultant"})
    assert "chat_mode: plan" in prompt
    assert "Modalita' Piano" in prompt

    assert agent_scope_state(None)["chat_mode"] == "agent"


# --- the mode survives the whole request path -------------------------------

def test_the_mode_sent_with_a_request_reaches_the_agent_run(monkeypatch):
    """The mode has to travel API -> runtime -> graph state, not just exist."""
    from backend.services import agent_runtime

    seen: dict = {}

    class FakeAgent:
        def stream(self, state, config=None, stream_mode=None):
            seen["chat_mode"] = state.get("chat_mode")
            seen["bound_mode"] = active_mode()
            return iter(())

    monkeypatch.setattr(agent_runtime.settings, "delir_fake_llm", False)
    monkeypatch.setattr(agent_runtime, "get_agent", lambda *args, **kwargs: FakeAgent())

    events = list(
        agent_runtime.stream_agent_events(
            thread_id="t-mode-1",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "rinomina il task"}],
            scope=None,
            chat_mode="plan",
            emit_activity=False,
        )
    )

    assert seen["chat_mode"] == "plan"
    # Bound for the duration of the run, so a tool write is refused where it happens
    # and not only where the router decided.
    assert seen["bound_mode"] == "plan"

    start = next(event for event in events if event.type == "start")
    assert start.payload["chat_mode"] == "plan"


def test_a_request_without_a_mode_runs_as_agent(monkeypatch):
    from backend.services import agent_runtime

    seen: dict = {}

    class FakeAgent:
        def stream(self, state, config=None, stream_mode=None):
            seen["chat_mode"] = state.get("chat_mode")
            return iter(())

    monkeypatch.setattr(agent_runtime.settings, "delir_fake_llm", False)
    monkeypatch.setattr(agent_runtime, "get_agent", lambda *args, **kwargs: FakeAgent())

    list(
        agent_runtime.stream_agent_events(
            thread_id="t-mode-2",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "ciao"}],
            scope=None,
            emit_activity=False,
        )
    )

    assert seen["chat_mode"] == "agent"
