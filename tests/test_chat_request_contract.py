"""Il turno porta due scelte del consulente: postura (per chat) e autonomia (ovunque)."""

import pytest
from pydantic import ValidationError

from backend.schemas.chat_api import ChatRequest, SendMessageRequest


def _payload(schema) -> dict:
    return (
        {"messages": [], "thread_id": "contract-test"}
        if schema is ChatRequest
        else {"message": "Riepiloga lo stato dei progetti a rischio"}
    )


@pytest.mark.parametrize(
    ("autonomy", "internal_mode"),
    [("auto", "agent"), ("ask", "plan"), ("manual", "conversation")],
)
@pytest.mark.parametrize("schema", [ChatRequest, SendMessageRequest])
def test_autonomy_becomes_the_internal_mode(schema, autonomy, internal_mode):
    request = schema(**_payload(schema), scope={"type": "consultant"}, autonomy=autonomy)
    assert request.chat_mode == internal_mode


@pytest.mark.parametrize("schema", [ChatRequest, SendMessageRequest])
def test_a_turn_without_choices_is_auto_in_both_axes(schema):
    """Il default e' Auto: il caso Barilla partiva da una modalita' che non scriveva."""
    request = schema(**_payload(schema))
    assert (request.posture, request.autonomy, request.chat_mode) == ("auto", "auto", "agent")


@pytest.mark.parametrize(
    ("scope", "posture"),
    [
        ({"type": "consultant"}, "desk"),
        ({"type": "consultant"}, "prepare"),
        ({"type": "project", "project_id": "p"}, "deliver"),
        ({"type": "process", "project_id": "p", "process_id": "q"}, "discover"),
        ({"type": "canvas", "project_id": "p", "process_id": "q", "bpmn_model_id": "b"}, "compare"),
    ],
)
def test_each_chat_accepts_its_own_postures(scope, posture):
    assert SendMessageRequest(message="x", scope=scope, posture=posture).posture == posture


@pytest.mark.parametrize(
    ("scope", "posture"),
    [
        ({"type": "consultant"}, "map"),
        ({"type": "canvas", "project_id": "p", "process_id": "q", "bpmn_model_id": "b"}, "desk"),
    ],
)
def test_a_posture_from_another_chat_is_refused(scope, posture):
    with pytest.raises(ValidationError):
        SendMessageRequest(message="x", scope=scope, posture=posture)


@pytest.mark.parametrize("field", [{"autonomy": "agent"}, {"posture": "unknown"}])
def test_unknown_values_are_refused(field):
    with pytest.raises(ValidationError):
        SendMessageRequest(message="Test", **field)


@pytest.mark.parametrize(
    ("level", "provider"),
    [("low", "none"), ("medium", "medium"), ("high", "high")],
)
def test_reasoning_level_reaches_the_provider_vocabulary(level, provider):
    from backend.schemas.chat import PROVIDER_REASONING_EFFORT

    # La richiesta porta il livello della UI; la traduzione vive in un punto solo.
    request = SendMessageRequest(message="x", reasoning_effort=level)
    assert request.reasoning_effort == level
    assert PROVIDER_REASONING_EFFORT[request.reasoning_effort] == provider


def test_the_default_reasoning_costs_what_a_turn_has_always_cost():
    from backend.schemas.chat import PROVIDER_REASONING_EFFORT

    request = SendMessageRequest(message="x")
    assert request.reasoning_effort == "low"
    assert PROVIDER_REASONING_EFFORT[request.reasoning_effort] == "none"
