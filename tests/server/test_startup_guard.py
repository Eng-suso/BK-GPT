"""Cosa deve succedere prima che l'app accetti la prima richiesta.

B2. `delir_auth_enabled` e' spento di default, e con l'autenticazione spenta il
prodotto risponde a chiunque, da qualunque origine, con permessi di
amministratore. In sviluppo e' il comportamento voluto. Il difetto era che un
ambiente vero partiva esattamente allo stesso modo, senza dire niente.
"""

import pytest

from backend.app import assert_environment_is_defensible
from backend.settings import settings

pytestmark = pytest.mark.smoke


def test_a_declared_environment_refuses_to_start_without_authentication(monkeypatch):
    monkeypatch.setattr(settings, "delir_environment", "prod")
    monkeypatch.setattr(settings, "delir_auth_enabled", False)

    with pytest.raises(RuntimeError) as failure:
        assert_environment_is_defensible()

    # Il messaggio dice la conseguenza e come uscirne, non solo il nome del flag.
    assert "amministratore" in str(failure.value)
    assert "ambienti aperti (dev, local, test)" in str(failure.value)


def test_an_environment_nobody_declared_open_is_treated_as_real(monkeypatch):
    """Un refuso non deve essere un deploy aperto.

    La lista dice dove partire scoperti e' lecito, non dove e' vietato: con
    l'elenco degli ambienti da proteggere, `produzione` - la parola giusta, in
    italiano - sarebbe passata.
    """
    monkeypatch.setattr(settings, "delir_environment", "produzione")
    monkeypatch.setattr(settings, "delir_auth_enabled", False)

    with pytest.raises(RuntimeError) as failure:
        assert_environment_is_defensible()

    assert "produzione" in str(failure.value)


def test_authentication_without_a_token_is_configuration_not_a_fault(monkeypatch):
    monkeypatch.setattr(settings, "delir_environment", "staging")
    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "")

    with pytest.raises(RuntimeError) as failure:
        assert_environment_is_defensible()

    # Senza questo controllo ogni richiesta prendeva 503: sembra un guasto e
    # invece e' una riga di `.env` che manca.
    assert "DELIR_API_TOKEN" in str(failure.value)


def test_a_development_machine_starts_and_says_it_is_open(monkeypatch):
    monkeypatch.setattr(settings, "delir_environment", "dev")
    monkeypatch.setattr(settings, "delir_auth_enabled", False)

    # Parte, ma non fa finta di essere protetta: il verdetto e' un valore, non
    # una riga di log che nessuno legge.
    assert assert_environment_is_defensible() == "open"


API_TOKEN = "a" * 48
ADMIN_TOKEN = "b" * 48


@pytest.fixture()
def guarded(monkeypatch):
    """Un ambiente vero configurato bene: ogni test ne rompe un pezzo solo."""
    monkeypatch.setattr(settings, "delir_environment", "prod")
    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", API_TOKEN)
    monkeypatch.setattr(settings, "delir_admin_token", ADMIN_TOKEN)
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "pilot,acme")
    monkeypatch.setattr(settings, "delir_default_tenant_id", "pilot")
    monkeypatch.setattr(settings, "delir_cors_origins", "https://app.example.com")


@pytest.mark.parametrize("environment", ["prod", "staging", "prod-sim"])
def test_a_declared_environment_with_a_complete_configuration_starts(
    guarded, monkeypatch, environment
):
    monkeypatch.setattr(settings, "delir_environment", environment)

    assert assert_environment_is_defensible() == "guarded"


@pytest.mark.parametrize(
    ("setting", "value", "named"),
    [
        # Prima era un warning: partiva, e le cancellazioni rispondevano 403
        # senza che nessuno capisse perche'.
        ("delir_admin_token", "", "DELIR_ADMIN_TOKEN mancante"),
        ("delir_admin_token", None, "DELIR_ADMIN_TOKEN mancante"),
        ("delir_admin_token", "corto", "DELIR_ADMIN_TOKEN piu' corto"),
        # Una chiave admin uguale al token API rende admin chiunque usi l'app.
        ("delir_admin_token", API_TOKEN, "DELIR_ADMIN_TOKEN uguale a DELIR_API_TOKEN"),
        ("delir_api_token", "change-me-api-token", "DELIR_API_TOKEN piu' corto"),
        # Senza allowlist il tenant lo sceglie il client con un header.
        ("delir_allowed_tenant_ids", "", "DELIR_ALLOWED_TENANT_IDS vuota"),
        ("delir_allowed_tenant_ids", " , ", "DELIR_ALLOWED_TENANT_IDS vuota"),
        ("delir_default_tenant_id", "altro", "DELIR_DEFAULT_TENANT_ID non compare"),
        ("delir_cors_origins", "*", "DELIR_CORS_ORIGINS"),
        ("delir_cors_origins", "https://app.example.com,*", "DELIR_CORS_ORIGINS"),
        ("delir_cors_origins", "", "DELIR_CORS_ORIGINS"),
    ],
)
def test_a_declared_environment_with_a_weak_door_refuses_to_start(
    guarded, monkeypatch, setting, value, named
):
    monkeypatch.setattr(settings, setting, value)

    with pytest.raises(RuntimeError) as failure:
        assert_environment_is_defensible()

    assert named in str(failure.value)


def test_every_problem_is_reported_at_once_and_no_value_is_printed(guarded, monkeypatch):
    """Chi configura un ambiente corregge il file una volta, non una riga per riavvio."""
    weak_api_token = "segreto-corto"
    monkeypatch.setattr(settings, "delir_api_token", weak_api_token)
    monkeypatch.setattr(settings, "delir_admin_token", "")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")
    monkeypatch.setattr(settings, "delir_cors_origins", "*")

    with pytest.raises(RuntimeError) as failure:
        assert_environment_is_defensible()

    message = str(failure.value)
    for named in (
        "DELIR_API_TOKEN",
        "DELIR_ADMIN_TOKEN",
        "DELIR_ALLOWED_TENANT_IDS",
        "DELIR_CORS_ORIGINS",
    ):
        assert named in message
    # Il messaggio finisce nei log del container: i valori non ci devono stare.
    assert weak_api_token not in message
    assert ADMIN_TOKEN not in message


def test_a_development_machine_with_authentication_needs_only_the_token(monkeypatch):
    """In dev l'autenticazione accesa serve a provare il flusso, non a difendersi."""
    monkeypatch.setattr(settings, "delir_environment", "dev")
    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "test-api-token")
    monkeypatch.setattr(settings, "delir_admin_token", "")
    monkeypatch.setattr(settings, "delir_allowed_tenant_ids", "")

    assert assert_environment_is_defensible() == "guarded"


@pytest.mark.parametrize("environment", ["prod", "staging", "produzione"])
def test_a_real_environment_does_not_publish_the_map_of_its_api(monkeypatch, environment):
    """`/docs` e `/openapi.json` elencano ogni rotta coi suoi parametri.

    In sviluppo servono; su internet sono la mappa per chi cerca da dove entrare.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app import api_docs_settings

    monkeypatch.setattr(settings, "delir_environment", environment)
    client = TestClient(FastAPI(**api_docs_settings()))

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


@pytest.mark.parametrize("environment", ["dev", "local", "test"])
def test_a_development_machine_keeps_the_api_docs(monkeypatch, environment):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app import api_docs_settings

    monkeypatch.setattr(settings, "delir_environment", environment)
    client = TestClient(FastAPI(**api_docs_settings()))

    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


@pytest.fixture()
def supabase_guarded(guarded, monkeypatch):
    monkeypatch.setattr(settings, "delir_auth_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "https://progetto.supabase.co")
    monkeypatch.setattr(settings, "supabase_publishable_key", "sb_publishable_chiave-del-browser")


def test_supabase_replaces_the_shared_token(supabase_guarded, monkeypatch):
    """Con identita' per persona il token condiviso non serve piu'."""
    monkeypatch.setattr(settings, "delir_api_token", "")

    assert assert_environment_is_defensible() == "guarded"


@pytest.mark.parametrize(
    ("url", "named"),
    [
        ("", "senza SUPABASE_URL"),
        ("progetto.supabase.co", "URL http(s) valido"),
        # Le chiavi pubbliche lette in chiaro da internet si possono sostituire.
        ("http://progetto.supabase.co", "https verso un host esterno"),
    ],
)
def test_supabase_without_a_trustworthy_url_refuses_to_start(
    supabase_guarded, monkeypatch, url, named
):
    monkeypatch.setattr(settings, "supabase_url", url)

    with pytest.raises(RuntimeError) as failure:
        assert_environment_is_defensible()

    assert named in str(failure.value)


@pytest.mark.parametrize("url", ["http://127.0.0.1:54321", "http://supabase-kong:8000"])
def test_a_local_supabase_over_http_is_allowed(supabase_guarded, monkeypatch, url):
    """PROD-SIM usa la CLI locale: in chiaro, ma senza uscire dalla macchina."""
    monkeypatch.setattr(settings, "delir_environment", "prod-sim")
    monkeypatch.setattr(settings, "supabase_url", url)

    assert assert_environment_is_defensible() == "guarded"


def test_supabase_still_needs_the_admin_key_until_roles_exist(supabase_guarded, monkeypatch):
    monkeypatch.setattr(settings, "delir_admin_token", "")

    with pytest.raises(RuntimeError, match="DELIR_ADMIN_TOKEN mancante"):
        assert_environment_is_defensible()


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_an_unknown_auth_provider_refuses_to_start(guarded, monkeypatch, environment):
    monkeypatch.setattr(settings, "delir_environment", environment)
    monkeypatch.setattr(settings, "delir_auth_provider", "supabse")

    with pytest.raises(RuntimeError, match="DELIR_AUTH_PROVIDER"):
        assert_environment_is_defensible()


def test_a_development_machine_with_supabase_needs_its_url(monkeypatch):
    monkeypatch.setattr(settings, "delir_environment", "dev")
    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_auth_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "")

    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        assert_environment_is_defensible()


def test_supabase_without_a_publishable_key_refuses_to_start(supabase_guarded, monkeypatch):
    monkeypatch.setattr(settings, "supabase_publishable_key", "")

    with pytest.raises(RuntimeError, match="SUPABASE_PUBLISHABLE_KEY"):
        assert_environment_is_defensible()


def _legacy_key(role: str) -> str:
    import jwt

    return jwt.encode({"role": role, "iss": "supabase"}, "segreto-qualunque-lungo-32-byte-ok", algorithm="HS256")


@pytest.mark.parametrize("key", ["sb_secret_N7UND0Ug", _legacy_key("service_role")])
def test_a_secret_key_in_the_browser_slot_refuses_to_start(supabase_guarded, monkeypatch, key):
    """La publishable key finisce in ogni browser: una secret key li' e' un incidente."""
    monkeypatch.setattr(settings, "supabase_publishable_key", key)

    with pytest.raises(RuntimeError) as failure:
        assert_environment_is_defensible()

    assert "chiave segreta" in str(failure.value)
    assert key not in str(failure.value)


def test_the_legacy_anon_key_is_accepted_as_publishable(supabase_guarded, monkeypatch):
    monkeypatch.setattr(settings, "supabase_publishable_key", _legacy_key("anon"))

    assert assert_environment_is_defensible() == "guarded"
