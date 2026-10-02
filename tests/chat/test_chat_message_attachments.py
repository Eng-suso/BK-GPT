"""Un messaggio della chat ricorda gli allegati con cui e' partito.

Prima la conversazione salvava solo il testo: un file caricato dal composer
partiva con il turno, ma ricaricando la sessione non se ne vedeva traccia.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.routes import chat as chat_routes
from backend.settings import settings

pytestmark = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


def test_a_sent_message_keeps_its_attachments_when_the_session_is_read_again(monkeypatch):
    from backend.app import app

    monkeypatch.setattr(chat_routes, "stream_agent_text", lambda **_kwargs: "Ricevuto.")

    with TestClient(app) as client:
        thread = client.post(
            "/v1/consultant-chat/sessions",
            json={"model_name": "gpt-test", "scope": {"type": "consultant"}},
        ).json()["thread_id"]
        sent = client.post(
            f"/v1/consultant-chat/sessions/{thread}/messages",
            json={
                "message": "Ecco la procedura",
                "attachments": [
                    {"kind": "source", "id": "src-procedura", "label": "procedura.pdf", "project_id": "p-1"},
                    {"kind": "note", "id": "note-1", "label": "Appunti", "text": "testo lungo della nota"},
                ],
            },
        )
        assert sent.status_code == 200, sent.text

        session = client.get(f"/v1/consultant-chat/sessions/{thread}").json()

    user_message = next(message for message in session["messages"] if message["role"] == "user")
    # Quanto basta per mostrarli: tipo, id, etichetta. Il testo della nota no.
    assert user_message["attachments"] == [
        {"kind": "source", "id": "src-procedura", "label": "procedura.pdf"},
        {"kind": "note", "id": "note-1", "label": "Appunti"},
    ]
    assistant = next(message for message in session["messages"] if message["role"] == "assistant")
    assert assistant["attachments"] == []
