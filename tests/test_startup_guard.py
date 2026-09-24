"""Cosa deve succedere prima che l'app accetti la prima richiesta.

B2. `delir_auth_enabled` e' spento di default, e con l'autenticazione spenta il
prodotto risponde a chiunque, da qualunque origine, con permessi di
amministratore. In sviluppo e' il comportamento voluto. Il difetto era che un
ambiente vero partiva esattamente allo stesso modo, senza dire niente.
"""


import pytest

from backend.app import assert_environment_is_defensible
from backend.settings import settings


def test_a_declared_environment_refuses_to_start_without_authentication(monkeypatch):
    monkeypatch.setattr(settings, "delir_environment", "prod")
    monkeypatch.setattr(settings, "delir_auth_enabled", False)

    with pytest.raises(RuntimeError) as failure:
        assert_environment_is_defensible()

    # Il messaggio dice la conseguenza e come uscirne, non solo il nome del flag.
    assert "amministratore" in str(failure.value)
    assert "DELIR_ENVIRONMENT=dev" in str(failure.value)


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
    assert assert_environment_is_defensible() == "aperto"


def test_a_declared_environment_with_authentication_starts(monkeypatch):
    monkeypatch.setattr(settings, "delir_environment", "prod")
    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_api_token", "un-token-vero")

    assert assert_environment_is_defensible() == "protetto"
