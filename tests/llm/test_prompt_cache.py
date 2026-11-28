"""`prompt_cache_key` per compito, solo verso OpenAI.

OpenAI instrada sulla stessa cache le richieste con la stessa chiave: con piu'
persone che mandano lo stesso prefisso (istruzioni e tool di un compito) il
riuso sale. La posizione del contratto del sotto-grafo nel prompt non cambia
qui: spostarlo cambia cosa legge il modello e va deciso con gli eval della chat
(docs/usage-limits/STIMA.md).
"""

from __future__ import annotations

from backend.llm_config import prompt_cache_body
from backend.settings import settings


def test_the_cache_key_is_per_task_and_only_towards_openai(monkeypatch):
    monkeypatch.setattr(settings, "openai_base_url", None)
    monkeypatch.setattr(settings, "llm_prompt_cache_key", True)
    assert prompt_cache_body("chat_turn") == {"prompt_cache_key": "delir:chat_turn"}

    # Un fornitore compatibile potrebbe rifiutare un campo che non conosce.
    monkeypatch.setattr(settings, "openai_base_url", "http://altro-fornitore/v1")
    assert prompt_cache_body("chat_turn") is None

    monkeypatch.setattr(settings, "openai_base_url", None)
    monkeypatch.setattr(settings, "llm_prompt_cache_key", False)
    assert prompt_cache_body("chat_turn") is None


def test_the_chat_client_sends_the_cache_key(monkeypatch):
    from backend.llm import LlmTask
    from backend.llm.chat_client import chat_client

    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_base_url", None)
    monkeypatch.setattr(settings, "llm_prompt_cache_key", True)

    client = chat_client(LlmTask.CHAT_TURN, model_name="gpt-5.6-luna", streaming=True, tag="t")

    assert client.extra_body == {"prompt_cache_key": "delir:chat_turn"}
