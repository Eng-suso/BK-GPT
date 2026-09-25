from fastapi.testclient import TestClient
import pytest
import time

from backend.schemas.api import AgentStreamEvent, ApiError
from backend.agent import DeliRChatOpenAI
from backend.services.eval_runner import run_observability_smoke_eval
from backend.services import agent_runtime, trace_recorder
from backend.security import get_current_tenant_id
from backend.services.trace_recorder import new_trace_context, read_trace, trace_event
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


def test_agent_stream_event_contract_serializes_activity():
    event = AgentStreamEvent(type="activity", message="Leggo il contesto")

    payload = event.model_dump()

    assert payload["type"] == "activity"
    assert payload["message"] == "Leggo il contesto"


def test_trace_recorder_stores_events():
    context = new_trace_context(thread_id="thread-1", scope_type="consultant", scope_key="consultant")
    event = trace_event(context, "node", node="consult_router", message="Entered router")

    events = read_trace(context.trace_id, tenant_id=get_current_tenant_id())

    assert events[-1].node == "consult_router"
    assert events[-1].trace_id == event.trace_id


def test_trace_recorder_forgets_the_oldest_traces_instead_of_growing():
    """La memoria delle tracce ha un tetto: senza, il processo non lo raggiunge mai."""
    first = new_trace_context(thread_id="thread-oldest")
    trace_event(first, "node", node="consult_router")

    for index in range(trace_recorder.MAX_TRACES):
        context = new_trace_context(thread_id=f"thread-{index}")
        trace_event(context, "node", node="consult_router")

    assert trace_recorder.traced_count() == trace_recorder.MAX_TRACES
    # La piu' vecchia e' uscita per prima, non una a caso.
    assert read_trace(first.trace_id, tenant_id=get_current_tenant_id()) is None


def test_an_evicted_trace_does_not_come_back_from_the_dead():
    """Un evento in ritardo non deve riaprire una traccia gia' dimenticata.

    Ricrearla sembrava innocuo: la riga nuova nasceva pero' senza lo spazio di
    lavoro di chi l'aveva generata, quindi nessuno poteva piu' leggerla, e
    intanto occupava un posto - sfrattando una traccia viva al suo posto.
    """
    tenant = get_current_tenant_id()
    evicted = new_trace_context(thread_id="thread-evicted")

    for index in range(trace_recorder.MAX_TRACES):
        new_trace_context(thread_id=f"thread-filler-{index}")

    assert read_trace(evicted.trace_id, tenant_id=tenant) is None

    # Il turno sfrattato sta ancora girando e scrive: l'evento cade, la memoria
    # non cresce e nessuna traccia viva viene buttata fuori per fargli posto.
    before = trace_recorder.traced_count()
    trace_event(evicted, "node", node="consult_router")

    assert trace_recorder.traced_count() == before
    assert read_trace(evicted.trace_id, tenant_id=tenant) is None


def test_trace_recorder_keeps_the_tail_of_a_runaway_turn():
    """Un turno che non termina non porta con se' tutta la RAM del processo."""
    context = new_trace_context(thread_id="thread-runaway")

    for index in range(trace_recorder.MAX_EVENTS_PER_TRACE + 25):
        trace_event(context, "node", node=f"step-{index}")

    events = read_trace(context.trace_id, tenant_id=get_current_tenant_id())

    assert len(events) == trace_recorder.MAX_EVENTS_PER_TRACE
    # Di un ciclo che non finisce interessa dove e' arrivato, non da dove partiva.
    assert events[-1].node == f"step-{trace_recorder.MAX_EVENTS_PER_TRACE + 24}"


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
            assert stream_mode == ["messages", "updates"]
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


class FakeToolCallMessage:
    """Un messaggio dell'agente che sta per chiamare dei tool."""

    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


def test_stream_agent_events_narrates_the_phases_the_agent_actually_goes_through(monkeypatch):
    class FakeChunk:
        type = "AIMessageChunk"

        def __init__(self, content=""):
            self.content = content
            self.usage_metadata = None

    class ToolUsingAgent:
        def stream(self, _input, *, config, stream_mode):
            assert stream_mode == ["messages", "updates"]
            time.sleep(0.02)
            yield "updates", {
                "consult_macro_agent": {
                    "messages": [
                        FakeToolCallMessage(
                            [{"name": "retrieve_consulting_context", "args": {"query": "intervista Laura"}}]
                        )
                    ]
                }
            }
            # Due tool della stessa famiglia: una sola riga di progresso.
            yield "updates", {
                "consult_macro_agent": {
                    "messages": [
                        FakeToolCallMessage([{"name": "retrieve_consulting_graph_context", "args": {}}])
                    ]
                }
            }
            yield "updates", {
                "consult_macro_agent": {
                    "messages": [
                        FakeToolCallMessage(
                            [{"name": "list_workspace_project_sources", "args": {"project_id": "p-1"}}]
                        )
                    ]
                }
            }
            yield "messages", (FakeChunk("Ecco "), {"langgraph_node": "consult_macro_agent"})
            yield "messages", (FakeChunk("il quadro."), {"langgraph_node": "consult_macro_agent"})

    monkeypatch.setattr(agent_runtime, "get_agent", lambda *_args, **_kwargs: ToolUsingAgent())
    monkeypatch.setattr(agent_runtime, "langsmith_tracing_enabled", lambda: False)

    events = list(
        agent_runtime.stream_agent_events(
            thread_id="thread-activity",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "cosa sappiamo di Esaote"}],
            scope=None,
        )
    )
    activities = [event for event in events if event.type == "activity"]
    phases = [event.payload["phase"] for event in activities]

    assert phases == ["understanding", "recalling", "reading_sources", "drafting"]
    # Una fase per riga: nessuna frase ripetuta, mai.
    assert len(phases) == len(set(phases))
    assert any(event.type == "delta" and event.content == "Ecco " for event in events)


def test_progress_updates_never_leak_internal_names(monkeypatch):
    class FakeChunk:
        type = "AIMessageChunk"

        def __init__(self, content=""):
            self.content = content
            self.usage_metadata = None

    class CanvasAgent:
        def stream(self, _input, *, config, stream_mode):
            yield "messages", (FakeChunk(""), {"langgraph_node": "canvas_construction_agent"})
            yield "messages", (FakeChunk("Pronto"), {"langgraph_node": "canvas_drawing_agent"})

    monkeypatch.setattr(agent_runtime, "get_agent", lambda *_args, **_kwargs: CanvasAgent())
    monkeypatch.setattr(agent_runtime, "langsmith_tracing_enabled", lambda: False)

    events = list(
        agent_runtime.stream_agent_events(
            thread_id="thread-internal-names",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "aggiorna il canvas"}],
            scope=None,
        )
    )
    activities = [event for event in events if event.type == "activity"]

    assert activities
    for event in activities:
        rendered = f"{event.message} {event.payload.get('detail', '')}".lower()
        for leak in ("agent", "subgraph", "node", "router", "canvas_", "xml", "tool"):
            assert leak not in rendered
        # Il livello di traccia porta il nodo; il livello utente no.
        assert event.node is None
    # Il nodo interno resta comunque visibile nella traccia.
    assert any(event.type == "node" and event.node == "canvas_drawing_agent" for event in events)


def test_stream_agent_events_streams_canvas_subagent_text_but_hides_internal_chunks(monkeypatch):
    class FakeChunk:
        type = "AIMessageChunk"

        def __init__(self, content=""):
            self.content = content
            self.usage_metadata = None

    class FakeAgent:
        def stream(self, _input, *, config, stream_mode):
            assert stream_mode == ["messages", "updates"]
            yield FakeChunk('{"rows":[["Start","Task"]]}'), {
                "langgraph_node": "canvas_layout_consultant_agent",
                "delir_stream_visibility": "internal",
            }
            yield FakeChunk("Sto aggiornando il canvas"), {"langgraph_node": "canvas_patch_edit_agent"}

    monkeypatch.setattr(agent_runtime, "get_agent", lambda *_args, **_kwargs: FakeAgent())
    monkeypatch.setattr(agent_runtime, "langsmith_tracing_enabled", lambda: False)

    events = list(
        agent_runtime.stream_agent_events(
            thread_id="thread-canvas-stream",
            model_name="gpt-5.6-luna",
            messages=[{"role": "user", "content": "aggiorna il canvas"}],
            scope=None,
        )
    )

    assert any(event.type == "node" and event.node == "canvas_layout_consultant_agent" for event in events)
    assert not any(event.type == "delta" and "rows" in (event.content or "") for event in events)
    assert any(event.type == "delta" and event.content == "Sto aggiornando il canvas" for event in events)


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


def test_a_trace_does_not_leave_its_workspace(client: TestClient):
    """Il `trace_id` arriva al client: da solo non deve bastare per leggere il turno."""
    mine = client.post("/v1/evals/observability-smoke", headers={"X-DeliR-Tenant-ID": "studio-uno"})
    trace_id = mine.json()["trace_id"]

    same = client.get(
        f"/v1/observability/traces/{trace_id}",
        headers={"X-DeliR-Tenant-ID": "studio-uno"},
    )
    other = client.get(
        f"/v1/observability/traces/{trace_id}",
        headers={"X-DeliR-Tenant-ID": "studio-due"},
    )

    assert same.status_code == 200
    assert same.json()["trace_id"] == trace_id
    # Una traccia di un altro spazio risponde come una che non esiste: chi prova
    # un id altrui non scopre nemmeno che e' valido.
    assert other.status_code == 404
    assert other.json()["error"]["message"] == "Traccia non trovata."
