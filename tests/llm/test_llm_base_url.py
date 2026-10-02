"""Un endpoint compatibile OpenAI al posto di api.openai.com, solo se chiesto.

I test che parlano con un modello girano su un provider gratuito o economico
(Gemini, Ollama), la produzione su OpenAI. Il punto d'aggancio e'
`settings.openai_base_url`: vuoto in produzione, e allora i client non devono
nemmeno nominarlo; impostato nei test, e allora deve arrivare a ogni client di
chat - quello dei compiti e quello della conversazione.
"""

from __future__ import annotations

import pytest

from backend.llm import LlmTask
from backend.llm.chat_client import chat_client
from backend.llm_config import chat_openai_kwargs
from backend.settings import settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"


@pytest.fixture(autouse=True)
def _chiave_finta(monkeypatch):
    """Costruire un client non chiama nessuno: basta una chiave qualsiasi."""
    monkeypatch.setattr(settings, "openai_api_key", "chiave-non-usata")


def test_senza_endpoint_i_client_parlano_con_openai(monkeypatch):
    monkeypatch.setattr(settings, "openai_base_url", None)

    assert "base_url" not in chat_openai_kwargs()
    assert chat_client(LlmTask.CHAT_TURN, model_name="gpt-5.6-luna", streaming=False, tag="t").openai_api_base is None


def test_un_endpoint_impostato_arriva_a_ogni_client_di_chat(monkeypatch):
    monkeypatch.setattr(settings, "openai_base_url", GEMINI)

    assert chat_openai_kwargs()["base_url"] == GEMINI
    client = chat_client(LlmTask.CHAT_TURN, model_name="gemini-flash", streaming=False, tag="t")
    assert client.openai_api_base == GEMINI
