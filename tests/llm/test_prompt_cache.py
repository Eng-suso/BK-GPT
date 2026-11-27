"""Il prompt dell'agente e' ordinato perche' il fornitore ne riusi l'inizio.

OpenAI riusa dalla cache solo il prefisso identico del prompt e lo fattura a
una frazione del prezzo. Il contratto del sotto-grafo (istruzioni dell'agente e
tool, migliaia di token) stava dopo la conversazione: ogni turno, e ogni passo
dopo una tool call, lo ripagava per intero. Misurato sull'app vera, il prefisso
riusabile tra due turni dello stesso thread era il 55-70% del prompt; con
l'ordine giusto e' il 98% (docs/load-test/README.md).
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.graphs.common import with_contract_before_history
from backend.llm_config import prompt_cache_body
from backend.settings import settings

BRAIN = SystemMessage(content="istruzioni fisse del prodotto")
CONTEXT = SystemMessage(content="contesto del thread")


def _turn(*history):
    return with_contract_before_history([BRAIN, CONTEXT, *history], "contratto del sotto-grafo")


def test_the_fixed_part_comes_first_and_the_conversation_last():
    messages = _turn(HumanMessage(content="dove si ferma?"))

    assert [m.content for m in messages] == [
        "istruzioni fisse del prodotto",
        "contratto del sotto-grafo",
        "contesto del thread",
        "dove si ferma?",
    ]


def test_the_next_turn_only_appends_so_the_previous_prompt_is_its_prefix():
    first = _turn(HumanMessage(content="dove si ferma?"))
    second = _turn(
        HumanMessage(content="dove si ferma?"),
        AIMessage(content="alla seconda firma"),
        HumanMessage(content="e quanto dura?"),
    )

    assert second[: len(first)] == first


def test_without_leading_instructions_the_contract_opens_the_prompt():
    messages = with_contract_before_history([HumanMessage(content="ciao")], "contratto")

    assert isinstance(messages[0], SystemMessage) and messages[0].content == "contratto"


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
