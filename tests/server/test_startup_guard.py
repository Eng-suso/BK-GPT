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


def test_a_declared_environment_with_authentication_starts(monkeypatch):
    monkeypatch.setattr(settings, "delir_environment", "prod")
    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "un-token-vero")

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
