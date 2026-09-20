"""Il selettore "Ragionamento" arriva al modello, invece di fermarsi nella UI.

Il controllo esisteva nella chat da mesi: cambiava uno stato locale che nessuno
inviava, e il grafo costruiva comunque l'LLM con `reasoning_effort="none"`.
Chiedere "Profondo" e ricevere la stessa risposta rapida e' peggio di non avere
il controllo, perche' il consulente crede di aver cambiato qualcosa.

Qui si verifica la catena: la richiesta porta il livello, il runtime lo passa al
grafo, e il grafo lo traduce nel valore del fornitore. Il router resta al minimo
in ogni caso: scegliere una via fra quattro non migliora pensandoci di piu'.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.chat import (
    DEFAULT_REASONING_EFFORT,
    PROVIDER_REASONING_EFFORT,
)
from backend.schemas.chat_api import ChatRequest, SendMessageRequest
from backend.settings import settings


_needs_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
@pytest.mark.parametrize("schema", [ChatRequest, SendMessageRequest])
def test_the_request_carries_the_level_the_consultant_picked(schema, effort):
    payload = (
        {"messages": [], "thread_id": "contract-test"}
        if schema is ChatRequest
        else {"message": "Analizza le contraddizioni fra le interviste"}
    )

    assert schema(**payload, reasoning_effort=effort).reasoning_effort == effort


@pytest.mark.parametrize("schema", [ChatRequest, SendMessageRequest])
def test_a_request_without_the_field_costs_what_it_has_always_cost(schema):
    payload = (
        {"messages": [], "thread_id": "contract-test"}
        if schema is ChatRequest
        else {"message": "Ciao"}
    )

    # Un client vecchio non deve far salire la spesa di ogni turno.
    assert schema(**payload).reasoning_effort == DEFAULT_REASONING_EFFORT
    assert PROVIDER_REASONING_EFFORT[DEFAULT_REASONING_EFFORT] == "none"


def test_an_unknown_level_is_refused_at_the_boundary():
    with pytest.raises(ValidationError):
        SendMessageRequest(message="Test", reasoning_effort="massimo")


def test_the_graph_is_built_once_per_level_and_reused(monkeypatch):
    from backend import agent as agent_module

    built: list[tuple[str, str]] = []

    def _fake_build(model_name=None, reasoning_effort=DEFAULT_REASONING_EFFORT):
        built.append((model_name, reasoning_effort))
        return object()

    monkeypatch.setattr(agent_module, "build_agent", _fake_build)
    monkeypatch.setattr(agent_module, "_AGENT_CACHE", {})

    first = agent_module.get_agent("gpt-5.6-luna", reasoning_effort="high")
    again = agent_module.get_agent("gpt-5.6-luna", reasoning_effort="high")
    other = agent_module.get_agent("gpt-5.6-luna", reasoning_effort="low")

    assert first is again, "lo stesso livello non deve ricompilare il grafo"
    assert other is not first, "livelli diversi sono grafi diversi"
    assert [effort for _model, effort in built] == ["high", "low"]


def test_an_unknown_level_falls_back_instead_of_building_a_broken_graph(monkeypatch):
    from backend import agent as agent_module

    built: list[str] = []

    def _fake_build(model_name=None, reasoning_effort=DEFAULT_REASONING_EFFORT):
        built.append(reasoning_effort)
        return object()

    monkeypatch.setattr(agent_module, "build_agent", _fake_build)
    monkeypatch.setattr(agent_module, "_AGENT_CACHE", {})

    # Il confine Pydantic lo rifiuta, ma `get_agent` e' chiamabile anche da
    # codice interno: un livello inventato non deve arrivare al fornitore.
    agent_module.get_agent("gpt-5.6-luna", reasoning_effort="massimo")

    assert built == [DEFAULT_REASONING_EFFORT]


def test_the_runtime_hands_the_level_to_the_graph(monkeypatch):
    from backend.services import agent_runtime

    seen: dict[str, object] = {}

    class _Agent:
        def stream(self, *args, **kwargs):
            return iter(())

    def _fake_get_agent(model_name=None, scope_type=None, reasoning_effort=None):
        seen["model"] = model_name
        seen["effort"] = reasoning_effort
        return _Agent()

    monkeypatch.setattr(agent_runtime, "get_agent", _fake_get_agent)
    monkeypatch.setattr(agent_runtime.settings, "delir_fake_llm", False)

    events = agent_runtime.stream_agent_events(
        thread_id="thread-effort",
        model_name="gpt-5.6-luna",
        messages=[{"role": "user", "content": "Analizza"}],
        reasoning_effort="high",
    )
    # Basta la prima fase: il grafo viene scelto prima di qualunque token.
    next(events)
    events.close()

    assert seen["effort"] == "high"


@_needs_db
def test_the_endpoint_passes_the_level_on_to_the_runtime(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.api.routes import chat as chat_routes

    seen: dict[str, object] = {}

    def _fake_stream_agent_text(**kwargs):
        seen.update(kwargs)
        return "risposta"

    monkeypatch.setattr(chat_routes, "stream_agent_text", _fake_stream_agent_text)

    from backend.app import app

    with TestClient(app) as client:
        created = client.post(
            "/v1/consultant-chat/sessions",
            json={"model_name": "gpt-test", "scope": {"type": "consultant"}},
        ).json()
        response = client.post(
            f"/v1/consultant-chat/sessions/{created['thread_id']}/messages",
            json={"message": "Analizza", "reasoning_effort": "medium"},
        )

    assert response.status_code == 200
    # Senza questo anello il livello si fermava al confine Pydantic: accettato
    # dalla richiesta e mai passato a chi costruisce il grafo.
    assert seen["reasoning_effort"] == "medium"


def test_the_answering_model_thinks_as_asked_and_the_router_does_not(monkeypatch):
    from backend import agent as agent_module

    built: list[dict] = []

    class _Recorder:
        def __init__(self, **kwargs):
            built.append(kwargs)

        def __getattr__(self, name):  # pragma: no cover - il grafo non gira qui
            raise AssertionError(f"il test non costruisce il grafo: {name}")

    monkeypatch.setattr(agent_module, "DeliRChatOpenAI", _Recorder)

    try:
        # La costruzione del grafo si ferma appena oltre i due LLM - il finto
        # client non sa fare altro. Cio' che si verifica e' come sono stati
        # creati, non che il grafo compili, quindi il resto non interessa.
        agent_module.build_agent("gpt-5.6-luna", "high")
    except Exception:  # noqa: BLE001 - oltre i due LLM il finto client si ferma
        pass

    assert len(built) >= 2, "il grafo costruisce chi risponde e il router"

    efforts = {
        tuple(kwargs["tags"])[-1] if kwargs.get("tags") else "": kwargs["reasoning_effort"]
        for kwargs in built
    }
    assert built[0]["reasoning_effort"] == "high", "chi risponde pensa quanto richiesto"
    assert built[1]["reasoning_effort"] == "none", "il router resta al minimo"
    assert efforts  # i tag distinguono i due client nel tracing
