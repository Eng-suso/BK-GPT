"""Claude nel gateway: la cache si conta e si paga come la fattura.

Anthropic, a differenza di OpenAI, fa pagare la scrittura in cache (1,25 volte
l'ingresso con la durata di 5 minuti). Un registro che contasse quei token al
prezzo d'ingresso direbbe meno di quanto si spende davvero.
"""

from __future__ import annotations

from decimal import Decimal

import anthropic
import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel

from backend.llm import LlmTask, OperationKind, operation, profile_for, run
from backend.llm.chat_client import chat_client
from backend.llm.claude_client import CACHE_BREAKPOINT, DeliRChatAnthropic, merge_leading_system
from backend.llm.egress import ANTHROPIC_API_URL, Destination, route
from backend.llm.gateway import reset_structured_output_memory
from backend.llm.prices import estimate_cost
from backend.llm_config import MissingProviderKey, chat_openai_kwargs
from backend.llm.usage import tokens_from_usage_metadata
from backend.settings import settings

HAIKU_PRICES = (
    '{"claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cached_input": 0.01, "cache_write": 0.125}}'
)


@pytest.fixture
def haiku_prices(monkeypatch):
    monkeypatch.setattr(settings, "llm_prices_json", HAIKU_PRICES)


class TestScritturaInCache:
    def test_le_scritture_si_pagano_a_parte(self, haiku_prices):
        # 1M in ingresso: 600K letti dalla cache, 300K scritti, 100K nuovi.
        cost = estimate_cost(
            "claude-haiku-5-5",
            input_tokens=1_000_000,
            output_tokens=0,
            cached_input_tokens=600_000,
            cache_write_input_tokens=300_000,
        )
        assert cost == Decimal("0.6") * Decimal("0.01") + Decimal("0.3") * Decimal("0.125") + Decimal("0.1") * Decimal("0.10")

    def test_senza_prezzo_della_scrittura_vale_l_ingresso(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_prices_json", '{"gpt-6-luna": {"input": 0.10, "output": 0.50}}')
        cost = estimate_cost("gpt-6-luna", input_tokens=1_000_000, output_tokens=0, cache_write_input_tokens=400_000)
        assert cost == Decimal("0.10")

    def test_le_scritture_non_superano_l_ingresso(self, haiku_prices):
        cost = estimate_cost(
            "claude-haiku-5-5", input_tokens=100, output_tokens=0, cached_input_tokens=80, cache_write_input_tokens=500
        )
        assert cost == (Decimal(80) * Decimal("0.01") + Decimal(20) * Decimal("0.125")) / Decimal(1_000_000)


class TestTokenDiClaude:
    def test_scritture_in_cache_creation(self):
        tokens = tokens_from_usage_metadata({
            "input_tokens": 1_000, "output_tokens": 50,
            "input_token_details": {"cache_read": 600, "cache_creation": 300},
        })
        assert (tokens.input, tokens.cached_input, tokens.cache_write_input) == (1_000, 600, 300)

    def test_scritture_divise_per_durata_si_contano_una_volta(self):
        # Con le voci per TTL langchain-anthropic azzera `cache_creation`.
        tokens = tokens_from_usage_metadata({
            "input_tokens": 1_000, "output_tokens": 50,
            "input_token_details": {"cache_read": 0, "cache_creation": 0, "ephemeral_5m_input_tokens": 400},
        })
        assert tokens.cache_write_input == 400

    def test_openai_non_ha_scritture(self):
        tokens = tokens_from_usage_metadata({
            "input_tokens": 1_000, "output_tokens": 50, "input_token_details": {"cache_read": 500},
        })
        assert tokens.cache_write_input == 0


# --- Il compito su Claude: modello, destinazione, client -----------------------

RERANK_ON_HAIKU = '{"retrieval_rerank": "claude-haiku-5-5", "entity_resolution": "claude-haiku-5-5"}'


@pytest.fixture
def rerank_on_haiku(monkeypatch):
    monkeypatch.setattr(settings, "llm_task_models_json", RERANK_ON_HAIKU)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-non-usata")


class TestModelloPerCompito:
    def test_il_compito_scelto_passa_a_claude(self, rerank_on_haiku):
        assert profile_for(LlmTask.RETRIEVAL_RERANK).model == "claude-haiku-5-5"
        assert profile_for(LlmTask.PLAN_EXTRACTION).model == settings.openai_model

    @pytest.mark.parametrize("task", ["context_routing", "embedding", "transcription", "memory_extraction"])
    def test_i_compiti_fissi_non_si_spostano(self, monkeypatch, task):
        monkeypatch.setattr(settings, "llm_task_models_json", f'{{"{task}": "claude-haiku-5-5"}}')
        assert profile_for(LlmTask(task)).model != "claude-haiku-5-5"

    def test_una_voce_sbagliata_non_ferma_le_altre(self, monkeypatch):
        monkeypatch.setattr(
            settings, "llm_task_models_json", '{"compito_che_non_esiste": "x", "retrieval_rerank": "claude-haiku-5-5"}'
        )
        assert profile_for(LlmTask.RETRIEVAL_RERANK).model == "claude-haiku-5-5"

    def test_la_destinazione_segue_il_modello(self, rerank_on_haiku):
        claude = route(Destination.LLM_CLAUDE)
        assert claude.active and claude.url == ANTHROPIC_API_URL
        assert set(claude.tasks) == {LlmTask.RETRIEVAL_RERANK, LlmTask.ENTITY_RESOLUTION}
        assert LlmTask.RETRIEVAL_RERANK not in route(Destination.LLM_CHAT).tasks

    def test_senza_compiti_su_claude_la_destinazione_e_spenta(self, monkeypatch):
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-non-usata")
        monkeypatch.setattr(settings, "llm_task_models_json", "")
        assert not route(Destination.LLM_CLAUDE).active


def _gateway_client(task: LlmTask):
    from backend.llm.gateway import _client

    return _client(profile_for(task), None)


class TestIlClientClaude:
    def test_senza_chiave_non_parte(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_task_models_json", RERANK_ON_HAIKU)
        monkeypatch.setattr(settings, "anthropic_api_key", None)
        with pytest.raises(MissingProviderKey, match="ANTHROPIC_API_KEY"):
            _gateway_client(LlmTask.RETRIEVAL_RERANK)

    def test_un_compito_senza_ragionamento_lo_spegne(self, rerank_on_haiku):
        client = _gateway_client(LlmTask.RETRIEVAL_RERANK)
        assert isinstance(client, DeliRChatAnthropic)
        assert client.thinking == {"type": "disabled"}
        assert client.reasoning_effort == "low"
        assert not client.cache_conversation

    def test_un_compito_di_giudizio_spende_di_piu_ma_non_ragiona(self, monkeypatch):
        """Con il ragionamento acceso il tool dell'output strutturato non e' piu'
        forzato, e il ragionamento consuma `max_tokens`: il livello resta come
        `effort`."""
        monkeypatch.setattr(settings, "llm_task_models_json", '{"plan_extraction": "claude-haiku-5-5"}')
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-non-usata")
        client = _gateway_client(LlmTask.PLAN_EXTRACTION)
        assert client.thinking == {"type": "disabled"}
        assert client.reasoning_effort == "medium"

    def test_l_host_e_quello_dichiarato_anche_con_una_variabile_d_ambiente(self, monkeypatch, rerank_on_haiku):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example.com")
        assert _gateway_client(LlmTask.RETRIEVAL_RERANK).anthropic_api_url == ANTHROPIC_API_URL


class TestLaParteFissaInCache:
    def test_i_messaggi_di_sistema_iniziali_si_uniscono(self):
        prepared = merge_leading_system([
            SystemMessage(content="Sei un revisore."),
            SystemMessage(content="Rispondi in JSON."),
            HumanMessage(content="Il caso."),
        ])
        assert [type(m) for m in prepared] == [SystemMessage, HumanMessage]
        assert [b["text"] for b in prepared[0].content] == ["Sei un revisore.", "Rispondi in JSON."]

    def test_un_sistema_dopo_la_conversazione_resta_al_suo_posto(self):
        messages = [SystemMessage(content="Base."), HumanMessage(content="Documento."), SystemMessage(content="Contratto.")]
        assert merge_leading_system(messages) == messages

    def test_il_gateway_segna_solo_il_sistema(self, rerank_on_haiku):
        """Una chiamata singola: il segnalibro in fondo alla richiesta farebbe
        pagare la scrittura su un contenuto che nessuno rilegge."""
        payload = _gateway_client(LlmTask.RETRIEVAL_RERANK)._get_request_payload([
            SystemMessage(content="Ordina i frammenti."),
            SystemMessage(content="Rispondi in JSON."),
            HumanMessage(content="Domanda e frammenti."),
        ])
        assert payload["system"][-1] == {"type": "text", "text": "Rispondi in JSON.", "cache_control": CACHE_BREAKPOINT}
        assert "cache_control" not in payload["system"][0]
        assert "cache_control" not in str(payload["messages"])
        assert "temperature" not in payload or payload["temperature"] is None


class TestLaChatSuClaude:
    """La chat: il passo dopo rilegge dalla cache tutto il passo prima."""

    @pytest.fixture
    def chat_on_haiku(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_task_models_json", '{"chat_turn": "claude-haiku-5-5"}')
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-non-usata")

    def test_la_chat_e_chi_la_segue_girano_su_claude(self, chat_on_haiku):
        from backend.agent import normalize_model_name

        assert normalize_model_name("gpt-5.6-luna") == "claude-haiku-5-5"
        assert profile_for(LlmTask.CONTEXT_ROUTING).model == "claude-haiku-5-5"
        assert profile_for(LlmTask.THREAD_SUMMARY).model == "claude-haiku-5-5"
        assert LlmTask.CHAT_TURN in route(Destination.LLM_CLAUDE).tasks

    def test_il_client_della_chat_e_claude_e_misurato(self, chat_on_haiku):
        from backend.llm_streaming import TURN_METERED_TAG

        client = chat_client(LlmTask.CHAT_TURN, model_name="claude-haiku-5-5", streaming=True, tag="t", reasoning_effort="high")
        assert isinstance(client, DeliRChatAnthropic)
        assert client.cache_conversation and client.streaming and client.stream_usage
        assert TURN_METERED_TAG in client.tags
        assert client.reasoning_effort == "high"

    def test_segnalibri_sul_sistema_e_sulla_fine_della_conversazione(self, chat_on_haiku):
        """La forma del prompt della chat: sistema in testa, storia, tool, e il
        contratto dello specialista in coda."""
        client = chat_client(LlmTask.CHAT_TURN, model_name="claude-haiku-5-5", streaming=True, tag="t")
        payload = client._get_request_payload([
            SystemMessage(content="Memoria procedurale."),
            SystemMessage(content="Scope del processo."),
            HumanMessage(content="Aggiorna il piano."),
            AIMessage(content="", tool_calls=[{"name": "read_process_plan", "args": {}, "id": "c1"}]),
            ToolMessage(content="Il piano.", tool_call_id="c1"),
            SystemMessage(content="Contratto dello specialista."),
        ])
        assert payload["system"][-1]["cache_control"] == CACHE_BREAKPOINT
        roles = [m["role"] for m in payload["messages"]]
        assert roles[-1] == "system"  # il contratto, al suo posto
        last_turn = payload["messages"][-2]
        assert last_turn["role"] == "user"
        assert last_turn["content"][-1]["cache_control"] == CACHE_BREAKPOINT
        marks = str(payload["messages"]).count("cache_control")
        assert marks == 1


class TestIlGatewaySuClaude:
    def test_la_riga_conta_le_scritture_e_il_modello(self, monkeypatch, rerank_on_haiku):
        written: list[dict] = []
        monkeypatch.setattr("backend.llm.gateway.record", lambda **kw: written.append(kw))
        built: list[str] = []

        class _FakeClaude:
            def stream(self, *_a, **_k):
                yield AIMessage(content="ok", usage_metadata={
                    "input_tokens": 2_000, "output_tokens": 30, "total_tokens": 2_030,
                    "input_token_details": {"cache_read": 0, "cache_creation": 1_200},
                })

        def _fake_claude_client(**kwargs):
            built.append(kwargs["model"])
            return _FakeClaude()

        monkeypatch.setattr("backend.llm.claude_client.claude_client", _fake_claude_client)

        with operation(OperationKind.PLAN_SYNTHESIS):
            run(task=LlmTask.RETRIEVAL_RERANK, messages=[HumanMessage(content="x")])

        assert built == ["claude-haiku-5-5"]
        assert written[-1]["model"] == "claude-haiku-5-5"
        assert written[-1]["tokens"].cache_write_input == 1_200


    def test_il_json_libero_su_claude_non_chiede_json_object(self, monkeypatch, rerank_on_haiku):
        """Lo schema nativo rifiutato porta al JSON libero: su Claude senza
        `response_format`, che langchain-anthropic non sa mandare."""
        class _Answer(BaseModel):
            answer: str

        monkeypatch.setattr("backend.llm.gateway.record", lambda **kw: None)
        reset_structured_output_memory()
        bound: list[dict] = []

        class _FakeClaude:
            def with_structured_output(self, *_a, **_k):
                return self

            def bind(self, **kwargs):
                bound.append(kwargs)
                return self

            def stream(self, messages, *_a, **_k):
                if not any("JSON Schema" in str(getattr(m, "content", "")) for m in messages):
                    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
                    raise anthropic.BadRequestError(
                        "schema", response=httpx.Response(400, request=request), body=None
                    )
                yield AIMessage(content='{"answer": "ok"}')

        monkeypatch.setattr("backend.llm.claude_client.claude_client", lambda *_a, **_k: _FakeClaude())

        with operation(OperationKind.PLAN_SYNTHESIS):
            parsed = run(task=LlmTask.RETRIEVAL_RERANK, messages=[HumanMessage(content="x")], output=_Answer)

        assert parsed.answer == "ok"
        assert bound == []
        reset_structured_output_memory()


def test_il_client_openai_decide_i_parametri_sul_modello_del_compito(monkeypatch):
    """Un compito su un modello OpenAI senza ragionamento non riceve i parametri
    di ragionamento del modello di conversazione."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-non-usata")
    monkeypatch.setattr(settings, "openai_model", "gpt-5.6-luna")
    kwargs = chat_openai_kwargs(model="gpt-4.1-mini")
    assert kwargs["model"] == "gpt-4.1-mini"
    assert "reasoning_effort" not in kwargs
