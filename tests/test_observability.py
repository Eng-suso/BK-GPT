from fastapi.testclient import TestClient
import pytest

from backend.schemas.api import AgentStreamEvent, ApiError
from backend.agent import DeliRChatOpenAI
from backend.services.eval_runner import run_observability_smoke_eval
from backend.services import agent_runtime
from backend.services.trace_recorder import get_trace, new_trace_context, trace_event
from backend.settings import effective_langsmith_model_name, langsmith_metadata, langsmith_tags, settings


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


def test_langsmith_metadata_and_tags_are_configurable(monkeypatch):
    monkeypatch.setattr(settings, "langsmith_provider", "openai")
    monkeypatch.setattr(settings, "langsmith_model_name", "gpt-5.4-mini")
    monkeypatch.setattr(settings, "langsmith_tags", "delir,prod")

    assert effective_langsmith_model_name("gpt-5.6-luna") == "gpt-5.4-mini"
    assert langsmith_metadata("gpt-5.6-luna", request_id="req-1") == {
        "ls_provider": "openai",
        "ls_model_name": "gpt-5.4-mini",
        "request_id": "req-1",
    }
    assert langsmith_tags("prod", "scope:consultant") == ["delir", "prod", "scope:consultant"]


def test_delir_chat_openai_overrides_langsmith_model_name():
    model = DeliRChatOpenAI(
        model="gpt-5.6-luna",
        api_key="sk-test",
        langsmith_provider="openai",
        langsmith_model_name="gpt-5.4-mini",
    )

    params = model._get_ls_params()

    assert params["ls_provider"] == "openai"
    assert params["ls_model_name"] == "gpt-5.4-mini"


def test_merge_usage_metadata_aggregates_nested_counts():
    totals = agent_runtime.merge_usage_metadata(
        {},
        {
            "input_tokens": 10,
            "output_tokens": 3,
            "input_token_details": {"cache_read": 4},
        },
    )

    agent_runtime.merge_usage_metadata(
        totals,
        {
            "input_tokens": 7,
            "output_tokens": 2,
            "input_token_details": {"cache_read": 1, "audio": 6},
        },
    )

    assert totals == {
        "input_tokens": 17,
        "output_tokens": 5,
        "input_token_details": {"cache_read": 5, "audio": 6},
    }


def test_stream_agent_events_records_first_token_usage_and_langsmith_config(monkeypatch):
    captured_config = {}

    class FakeChunk:
        type = "AIMessageChunk"

        def __init__(self, content="", usage_metadata=None):
            self.content = content
            self.usage_metadata = usage_metadata

    class FakeAgent:
        def stream(self, _input, *, config, stream_mode):
            captured_config.update(config)
            assert stream_mode == "messages"
            yield FakeChunk("Ciao"), {"langgraph_node": "consult_macro_agent"}
            yield FakeChunk(
                "",
                {
                    "input_tokens": 11,
                    "output_tokens": 4,
                    "total_tokens": 15,
                },
            ), {"langgraph_node": "consult_macro_agent"}

    monkeypatch.setattr(agent_runtime, "get_agent", lambda *_args, **_kwargs: FakeAgent())
    monkeypatch.setattr(agent_runtime, "langsmith_tracing_enabled", lambda: False)
    monkeypatch.setattr(settings, "langsmith_model_name", "gpt-5.4-mini")

    events = list(
        agent_runtime.stream_agent_events(
            thread_id="thread-observability",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "ciao"}],
            scope=None,
        )
    )

    trace_events = [event.payload for event in events if event.type == "trace"]
    first_token = [event for event in trace_events if event["event_type"] == "first_token"]
    usage = [event for event in trace_events if event["event_type"] == "usage"]

    assert first_token
    assert first_token[0]["payload"]["ttft_ms"] >= 0
    assert usage[-1]["payload"]["usage_metadata"] == {
        "input_tokens": 11,
        "output_tokens": 4,
        "total_tokens": 15,
    }
    assert captured_config["metadata"]["ls_provider"] == "openai"
    assert captured_config["metadata"]["ls_model_name"] == "gpt-5.4-mini"
    assert "consultant-chat" in captured_config["tags"]


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
