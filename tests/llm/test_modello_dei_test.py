"""I test live girano sul modello dei test, non su OpenAI.

Si verifica il meccanismo, senza chiamare nessuno: `use_test_llm` punta i client
sull'endpoint dichiarato, e senza un modello dei test un test live non ripiega
su OpenAI in silenzio.
"""

from __future__ import annotations

import pytest

import tests.live_llm as live_llm
from backend.agent import normalize_model_name
from backend.llm_config import chat_openai_kwargs
from backend.memory import embeddings
from backend.settings import settings

OLLAMA = "http://localhost:11434/v1"


@pytest.fixture()
def modello_dei_test(monkeypatch):
    monkeypatch.setattr(live_llm, "TEST_LLM_BASE_URL", OLLAMA)
    monkeypatch.setattr(live_llm, "TEST_LLM_API_KEY", "ollama")
    monkeypatch.setattr(live_llm, "TEST_LLM_MODEL", "qwen-test")
    monkeypatch.setattr(live_llm, "TEST_LLM_CONFIGURED", True)


def test_i_client_vanno_sull_endpoint_e_sul_modello_dei_test(monkeypatch, modello_dei_test):
    live_llm.use_test_llm(monkeypatch)

    kwargs = chat_openai_kwargs()
    assert kwargs["base_url"] == OLLAMA
    assert kwargs["api_key"] == "ollama"
    assert kwargs["model"] == "qwen-test"


def test_il_modello_della_conversazione_non_torna_a_quello_di_produzione(monkeypatch, modello_dei_test):
    live_llm.use_test_llm(monkeypatch)

    assert normalize_model_name(None) == "qwen-test"
    assert normalize_model_name("qwen-test") == "qwen-test"
    # Un nome che il modello dei test non conosce torna al modello dei test,
    # non a quello di produzione su un endpoint che non lo serve.
    assert normalize_model_name("un-modello-qualsiasi") == "qwen-test"


def test_sul_modello_dei_test_il_retrieval_resta_lessicale(monkeypatch, modello_dei_test):
    live_llm.use_test_llm(monkeypatch)

    assert embeddings.available() is False


def test_senza_modello_dei_test_non_si_ripiega_su_openai(monkeypatch):
    monkeypatch.setattr(live_llm, "TEST_LLM_CONFIGURED", False)
    monkeypatch.setattr(live_llm, "ALLOW_OPENAI", False)
    monkeypatch.setattr(settings, "openai_api_key", "sk-openai-vera")

    assert live_llm.provider_ready() is False


def test_openai_nei_test_e_una_scelta_dichiarata(monkeypatch):
    monkeypatch.setattr(live_llm, "TEST_LLM_CONFIGURED", False)
    monkeypatch.setattr(live_llm, "ALLOW_OPENAI", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-openai-vera")

    assert live_llm.provider_ready() is True
