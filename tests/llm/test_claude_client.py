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
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.llm import LlmTask, OperationKind, operation, profile_for, run
from backend.llm.claude_client import CACHE_BREAKPOINT, DeliRChatAnthropic, claude_client, with_cached_system
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

    @pytest.mark.parametrize("task", ["chat_turn", "embedding", "transcription", "memory_extraction"])
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


class TestIlClientClaude:
    def test_senza_chiave_non_parte(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_task_models_json", RERANK_ON_HAIKU)
        monkeypatch.setattr(settings, "anthropic_api_key", None)
        with pytest.raises(MissingProviderKey, match="ANTHROPIC_API_KEY"):
            claude_client(profile_for(LlmTask.RETRIEVAL_RERANK), input_characters=None, max_retries=0)

    def test_un_compito_senza_ragionamento_lo_spegne(self, rerank_on_haiku):
        client = claude_client(profile_for(LlmTask.RETRIEVAL_RERANK), input_characters=None, max_retries=0)
        assert isinstance(client, DeliRChatAnthropic)
        assert client.thinking == {"type": "disabled"}
        assert client.effort == "low"

    def test_un_compito_di_giudizio_spende_di_piu_ma_non_ragiona(self, monkeypatch):
        """Con il ragionamento acceso il tool dell'output strutturato non e' piu'
        forzato, e il ragionamento consuma `max_tokens`: il livello resta come
        `effort`."""
        monkeypatch.setattr(settings, "llm_task_models_json", '{"plan_extraction": "claude-haiku-5-5"}')
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-non-usata")
        client = claude_client(profile_for(LlmTask.PLAN_EXTRACTION), input_characters=10_000, max_retries=0)
        assert client.thinking == {"type": "disabled"}
        assert client.effort == "medium"

    def test_l_host_e_quello_dichiarato_anche_con_una_variabile_d_ambiente(self, monkeypatch, rerank_on_haiku):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example.com")
        client = claude_client(profile_for(LlmTask.RETRIEVAL_RERANK), input_characters=None, max_retries=0)
        assert client.anthropic_api_url == ANTHROPIC_API_URL


class TestLaParteFissaInCache:
    def test_i_messaggi_di_sistema_iniziali_si_uniscono_con_il_segnalibro(self):
        prepared = with_cached_system([
            SystemMessage(content="Sei un revisore."),
            SystemMessage(content="Rispondi in JSON."),
            HumanMessage(content="Il caso."),
        ])
        assert [type(m) for m in prepared] == [SystemMessage, HumanMessage]
        blocks = prepared[0].content
        assert [b["text"] for b in blocks] == ["Sei un revisore.", "Rispondi in JSON."]
        assert blocks[-1]["cache_control"] == CACHE_BREAKPOINT
        assert "cache_control" not in blocks[0]

    def test_un_sistema_dopo_la_conversazione_resta_al_suo_posto(self):
        prepared = with_cached_system([
            SystemMessage(content="Base."),
            HumanMessage(content="Documento."),
            AIMessage(content="Bozza."),
            SystemMessage(content="Correggi il campo X."),
        ])
        assert [type(m) for m in prepared] == [SystemMessage, HumanMessage, AIMessage, HumanMessage]
        assert prepared[-1].content == "Correggi il campo X."

    def test_senza_sistema_la_richiesta_passa_com_e(self):
        messages = [HumanMessage(content="ciao")]
        assert with_cached_system(messages) == messages

    def test_la_richiesta_ha_il_segnalibro_in_fondo_al_sistema(self, rerank_on_haiku):
        """La richiesta vera, costruita senza mandarla: un secondo messaggio di
        sistema in coda (lo schema del JSON libero) non la fa rifiutare."""
        client = claude_client(profile_for(LlmTask.RETRIEVAL_RERANK), input_characters=None, max_retries=0)
        payload = client._get_request_payload([
            SystemMessage(content="Ordina i frammenti."),
            HumanMessage(content="Domanda e frammenti."),
            SystemMessage(content="Schema."),
        ])
        assert payload["system"] == [
            {"type": "text", "text": "Ordina i frammenti.", "cache_control": CACHE_BREAKPOINT}
        ]
        assert [m["role"] for m in payload["messages"]] == ["user"]
        assert "temperature" not in payload or payload["temperature"] is None


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

        def _fake_claude_client(profile, **_kw):
            built.append(profile.model)
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
