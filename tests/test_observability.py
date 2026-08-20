from fastapi.testclient import TestClient
import pytest

from backend.schemas.api import AgentStreamEvent, ApiError
from backend.services.eval_runner import run_observability_smoke_eval
from backend.services.trace_recorder import get_trace, new_trace_context, trace_event


@pytest.fixture(scope="module")
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


def test_agent_stream_event_contract_serializes_error():
    error = ApiError(
        code="agent_stream_failed",
        message="Errore agente",
        origin="agent",
        retryable=False,
    )
    event = AgentStreamEvent(type="error", error=error)

    payload = event.model_dump()

    assert payload["type"] == "error"
    assert payload["error"]["code"] == "agent_stream_failed"


def test_trace_recorder_stores_events():
    context = new_trace_context(thread_id="thread-1", scope_type="consultant", scope_key="consultant")
    event = trace_event(context, "node", node="consult_router", message="Entered router")

    events = get_trace(context.trace_id)

    assert events[-1].node == "consult_router"
    assert events[-1].trace_id == event.trace_id


def test_observability_smoke_eval_contract():
    result = run_observability_smoke_eval()

    assert result.ok is True
    assert result.suite == "observability_smoke"
    assert result.checks


def test_observability_endpoints(client: TestClient):
    eval_response = client.post("/v1/evals/observability-smoke")
    assert eval_response.status_code == 200
    eval_payload = eval_response.json()
    assert eval_payload["ok"] is True
    assert eval_payload["trace_id"]

    trace_response = client.get(f"/v1/observability/traces/{eval_payload['trace_id']}")
    assert trace_response.status_code == 200
    assert trace_response.json()["trace_id"] == eval_payload["trace_id"]
