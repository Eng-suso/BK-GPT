"""Le pagine del frontend servite dal backend, come in produzione.

In sviluppo le pagine le serve Vite, che sa da solo che `/projects/abc` e' una
pagina di React. In produzione le serve il backend, che conosceva solo `/`: un
refresh o un link salvato davano 404, e il link del cruscotto mandato al
cliente (`/share.html#codice`) non si apriva.

Il lifespan non parte: queste prove non toccano nessun database.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app as app_module

pytestmark = pytest.mark.smoke


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app_module.app)


@pytest.fixture()
def built_frontend(tmp_path: Path, monkeypatch) -> Path:
    """Un build finto: le prove non dipendono da `npm run build` fatto prima."""
    dist = tmp_path / "dist"
    (dist / "tokens").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (dist / "share.html").write_text("<!doctype html><title>cruscotto</title>", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (dist / "tokens" / "colors.css").write_text(":root{}", encoding="utf-8")
    monkeypatch.setattr(app_module, "DIST_DIR", dist)
    monkeypatch.setattr(app_module, "FRONTEND_INDEX", dist / "index.html")
    return dist


@pytest.mark.parametrize(
    "path",
    [
        "/projects",
        "/projects/abc/processes/x/simulation/overview",
        "/clients/42",
        "/settings",
    ],
)
def test_a_page_of_the_app_opens_on_refresh(client: TestClient, built_frontend: Path, path: str):
    response = client.get(path)

    assert response.status_code == 200
    assert response.text == "<!doctype html><title>app</title>"
    assert response.headers["content-type"].startswith("text/html")
    # La pagina cambia a ogni rilascio: non va in cache, i suoi asset si'.
    assert response.headers["cache-control"] == "no-store"


def test_the_link_sent_to_the_client_opens_the_dashboard(client: TestClient, built_frontend: Path):
    response = client.get("/share.html")

    assert response.status_code == 200
    assert response.text == "<!doctype html><title>cruscotto</title>"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize("path", ["/favicon.svg", "/tokens/colors.css"])
def test_the_files_next_to_the_page_are_served(client: TestClient, built_frontend: Path, path: str):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/workspace/nope"),
        ("POST", "/v1/nope"),
        ("POST", "/projects"),
        ("GET", "/chat"),
        ("GET", "/health/nope"),
    ],
)
def test_an_api_that_does_not_exist_still_says_not_found(
    client: TestClient, built_frontend: Path, method: str, path: str
):
    """Il ripiego vale per le pagine: un'API sbagliata non riceve una pagina HTML."""
    response = client.request(method, path)

    assert response.status_code in {404, 405}
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", ["/assets/missing.js", "/missing.css", "/projects/report.pdf"])
def test_a_missing_file_is_not_answered_with_the_page(client: TestClient, built_frontend: Path, path: str):
    """Un `.js` mancante che riceve HTML rompe il browser con un errore che non dice niente."""
    response = client.get(path)

    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/..%2f..%2fpyproject.toml", "/tokens/..%2f..%2f..%2fpyproject.toml"])
def test_a_path_cannot_leave_the_build_folder(client: TestClient, built_frontend: Path, path: str):
    response = client.get(path)

    assert response.status_code == 404
    assert "suso-gpt" not in response.text


@pytest.mark.parametrize(
    "path",
    ["/src/lib/security.ts", "/src/main.tsx", "/styles/tokens/primitive.css", "/index.html"],
)
def test_the_source_code_of_the_frontend_is_not_published(client: TestClient, path: str):
    """Il backend pubblicava `frontend/src`: chiunque leggeva il codice, autenticazione compresa.

    Serviva a un `index.html` sorgente che carica TypeScript grezzo, cioe' a una
    pagina bianca: in sviluppo quei file li serve Vite. Senza build (`dist`) non
    c'e' nessuna pagina da servire.
    """
    if (app_module.DIST_DIR / "index.html").is_file() and path == "/index.html":
        pytest.skip("con un build presente /index.html e' la pagina dell'app")
    response = client.get(path)

    assert response.status_code == 404
    assert "import" not in response.text


def test_without_a_build_a_page_says_so_instead_of_a_blank_screen(
    client: TestClient, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(app_module, "DIST_DIR", tmp_path / "dist")
    monkeypatch.setattr(app_module, "FRONTEND_INDEX", tmp_path / "dist" / "index.html")

    for path in ("/", "/projects"):
        response = client.get(path)
        assert response.status_code == 404
        assert "npm run build" in response.json()["detail"]
