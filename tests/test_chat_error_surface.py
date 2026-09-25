"""Cosa arriva al consulente quando l'agente fallisce.

B9. Le rotte di chat catturavano `Exception` nuda e mandavano `str(exc)` al
client. Un'eccezione qualunque - il provider, il driver del database, un
percorso di file - finiva cosi' in interfaccia parola per parola, e a chi legge
non diceva niente che potesse usare.

Le altre rotte del workspace non hanno questo problema e non sono state
toccate: la' `str(exc)` e' il messaggio di una `ValueError` sollevata apposta,
scritto in italiano per il consulente.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.api.routes import chat as chat_routes
from backend.settings import settings


#: Un'eccezione come quelle vere: dentro c'e' roba che non deve uscire.
LEAKY_EXCEPTION = RuntimeError(
    "connection to postgresql://delir_app:pw-segretissima@10.0.0.4:5432/delir failed"
)

_needs_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


def new_thread(client: TestClient) -> str:
    created = client.post(
        "/v1/consultant-chat/sessions",
        json={"model_name": "gpt-5.6-luna", "scope": {"type": "consultant"}},
    )
    return created.json()["thread_id"]


@_needs_db
def test_a_failed_turn_says_what_to_do_not_what_broke(client: TestClient, monkeypatch):
    def _raise(*_args, **_kwargs):
        raise LEAKY_EXCEPTION

    monkeypatch.setattr(chat_routes, "stream_agent_text", _raise)
    thread_id = new_thread(client)

    response = client.post(
        f"/v1/consultant-chat/sessions/{thread_id}/messages",
        json={
            "message": "analizza il processo",
            "model_name": "gpt-5.6-luna",
            "scope": {"type": "consultant"},
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["message"] == chat_routes.AGENT_FAILED_MESSAGE
    assert "segretissima" not in response.text
    assert "postgresql" not in response.text


@_needs_db
def test_a_turn_over_time_is_told_apart_from_a_turn_that_broke(
    client: TestClient, monkeypatch
):
    def _timeout(*_args, **_kwargs):
        raise TimeoutError("deadline di 90s superata da consult_macro_agent")

    monkeypatch.setattr(chat_routes, "stream_agent_text", _timeout)
    thread_id = new_thread(client)

    response = client.post(
        f"/v1/consultant-chat/sessions/{thread_id}/messages",
        json={
            "message": "analizza il processo",
            "model_name": "gpt-5.6-luna",
            "scope": {"type": "consultant"},
        },
    )

    # 503, non 502: al consulente si dice di riprovare, e il nodo interno resta
    # fuori dalla frase.
    assert response.status_code == 503
    assert response.json()["error"]["message"] == chat_routes.AGENT_TIMEOUT_MESSAGE
    assert "consult_macro_agent" not in response.text


@_needs_db
def test_a_broken_stream_carries_the_trace_id_instead_of_the_exception(
    client: TestClient, monkeypatch
):
    def _raise(*_args, **_kwargs):
        raise LEAKY_EXCEPTION

    monkeypatch.setattr(chat_routes, "stream_agent_events", _raise)
    thread_id = new_thread(client)

    with client.stream(
        "POST",
        f"/v1/consultant-chat/sessions/{thread_id}/messages/stream",
        json={
            "message": "analizza il processo",
            "model_name": "gpt-5.6-luna",
            "scope": {"type": "consultant"},
        },
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line.strip()]

    errors = [event for event in events if event["type"] == "error"]

    assert errors
    assert errors[-1]["detail"] == chat_routes.AGENT_FAILED_MESSAGE
    assert "segretissima" not in json.dumps(events)
    # Il modo di ritrovare l'errore vero c'e', ed e' un id, non un'eccezione.
    assert errors[-1]["trace_id"]
