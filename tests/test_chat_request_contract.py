import pytest
from pydantic import ValidationError

from backend.schemas.chat_api import ChatRequest, SendMessageRequest


@pytest.mark.parametrize("mode", ["conversation", "plan", "edit", "agent"])
@pytest.mark.parametrize("schema", [ChatRequest, SendMessageRequest])
def test_frontend_modes_are_accepted(schema, mode):
    payload = (
        {"messages": [], "thread_id": "contract-test"}
        if schema is ChatRequest
        else {"message": "Riepiloga lo stato dei progetti a rischio"}
    )
    assert schema(**payload, scope={"type": "consultant"}, mode=mode).mode == mode
    assert schema(**payload).mode == "conversation"


@pytest.mark.parametrize("mode", ["unknown", "canvas.plan", "consultant.full"])
def test_modes_without_runtime_support_are_rejected(mode):
    with pytest.raises(ValidationError):
        SendMessageRequest(message="Test", mode=mode)
