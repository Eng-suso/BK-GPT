"""Review has task-specific history and a server-enforced baseline boundary."""
import pytest
from pydantic import ValidationError

from backend.schemas.chat import CanvasChatScope, chat_scope_key
from backend.schemas.chat_api import ChatRequest, SendMessageRequest


def scope(**changes):
    return CanvasChatScope(type="canvas", project_id="p", process_id="process", bpmn_model_id="m",
                           review_node_id="verify", review_base_revision="a" * 64, **changes)


def test_task_history_is_separate_from_canvas_and_other_tasks():
    review = scope()
    assert chat_scope_key(review) == "canvas:p:process:m:review:verify"
    assert chat_scope_key(review.model_copy(update={"review_base_revision": "b" * 64})) == chat_scope_key(review)
    assert chat_scope_key(review.model_copy(update={"review_node_id": "approve"})) != chat_scope_key(review)
    assert chat_scope_key(review.model_copy(update={"review_node_id": None, "review_base_revision": None})) != chat_scope_key(review)


@pytest.mark.parametrize("autonomy", ["auto", "ask", "manual"])
def test_client_cannot_enable_baseline_writes_in_review(autonomy):
    assert SendMessageRequest(message="Explain", scope=scope(), autonomy=autonomy).chat_mode == "conversation"
    assert ChatRequest(messages=[], thread_id="test", scope=scope(), autonomy=autonomy).chat_mode == "conversation"


@pytest.mark.parametrize("changes", [{"review_node_id": "verify"}, {"review_base_revision": "a" * 64}])
def test_partial_review_scope_is_invalid(changes):
    with pytest.raises(ValidationError):
        CanvasChatScope(type="canvas", project_id="p", process_id="process", bpmn_model_id="m", **changes)


def test_review_tools_do_not_accept_model_or_process_identifiers_from_the_llm():
    from backend.graphs.task_review import REVIEW_TOOLS
    for tool in REVIEW_TOOLS:
        properties = tool.tool_call_schema.model_json_schema()["properties"]
        assert not {"project_id", "process_id", "bpmn_model_id", "state"} & properties.keys()
    assert not any(tool.name in {"manage_canvas_bpmn_model", "approve_canvas_bpmn_review"} for tool in REVIEW_TOOLS)


def test_review_prompt_allows_requested_copies_without_conflicting_manual_policy():
    from backend.agents.primary_scope import build_scope_system_prompt

    prompt = build_scope_system_prompt({
        "scope_type": "canvas", "chat_mode": "conversation",
        "review_task_context": {"id": "verify", "name": "Verificare dati"},
    })
    assert "create_review_bpmn_proposal" in prompt
    assert "Una domanda di lettura o parere non autorizza scritture" in prompt
    assert "Non modificare l'As-Is originale" in prompt
    assert "non creare record" not in prompt
    ordinary = build_scope_system_prompt({"scope_type": "canvas", "chat_mode": "conversation"})
    assert "non creare record" in ordinary
