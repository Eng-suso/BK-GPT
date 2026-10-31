"""`/health/ready`: il processo puo' servire richieste, non solo e' vivo.

`/health` risponde anche con il database spento, ed e' giusto: dice che il
processo non e' bloccato. Chi decide se mandargli traffico (il controllo di
uptime, il rilascio senza interruzione) deve sapere un'altra cosa: i database
rispondono e sono allo schema che il codice si aspetta.
"""
import pytest
from fastapi.testclient import TestClient

from backend import readiness
from backend.app import app
from backend.settings import settings

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not settings.workspace_database_url, reason="serve lo stack di test"),
]

CLOSED_PORT_DSN = "postgresql+psycopg://nessuno:nessuna@127.0.0.1:9/workspace"


@pytest.fixture()
def client() -> TestClient:
    # Senza lifespan: la prontezza la decide la rotta, non l'avvio.
    return TestClient(app)


def test_with_databases_up_and_migrated_the_app_is_ready(client: TestClient):
    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["workspace"] == "ok"
    if settings.canonical_database_url:
        assert body["checks"]["canonical"] == "ok"


def test_with_the_database_down_the_app_is_not_ready(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "workspace_database_url", CLOSED_PORT_DSN)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["workspace"] == "down"
    # La rotta e' pubblica: niente DSN, utenti o messaggi del driver.
    assert "nessuno" not in response.text
    assert "127.0.0.1" not in response.text


def test_with_a_migration_missing_the_app_is_not_ready(client: TestClient, monkeypatch):
    """Il codice nuovo su uno schema vecchio fallisce a meta' richiesta: meglio non riceverle."""
    monkeypatch.setattr(readiness, "expected_head", lambda ini: "una-revisione-futura")

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["workspace"] == "behind"


def test_liveness_does_not_depend_on_the_database(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "workspace_database_url", CLOSED_PORT_DSN)

    assert client.get("/health").status_code == 200
