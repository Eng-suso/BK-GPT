"""Le chiamate di Mem0 lasciano la loro riga nel registro dei consumi.

Mem0 costruisce i suoi client OpenAI dentro la libreria: prima di
`backend.llm.mem0_meter` ogni `memory.add()` e `memory.search()` era spesa che
il registro non vedeva.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.llm import LlmTask, OperationKind, operation
from backend.llm import mem0_meter
from backend.services import degradation_counters
from backend.settings import settings


def _chat_response():
    return SimpleNamespace(
        model="gpt-4o-mini-2024",
        usage=SimpleNamespace(
            prompt_tokens=900,
            completion_tokens=60,
            prompt_tokens_details=SimpleNamespace(cached_tokens=200),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
    )


def _embedding_response():
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=42))


class _Resource:
    def __init__(self, response=None, exc=None):
        self.response, self.exc, self.calls = response, exc, 0

    def create(self, **_kwargs):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.response


def _memory(chat=None, embeddings=None):
    """La forma di `mem0.Memory` che conta: `llm.client` e `embedding_model.client`."""
    chat = chat or _Resource(_chat_response())
    embeddings = embeddings or _Resource(_embedding_response())
    return SimpleNamespace(
        llm=SimpleNamespace(client=SimpleNamespace(chat=SimpleNamespace(completions=chat))),
        embedding_model=SimpleNamespace(client=SimpleNamespace(embeddings=embeddings)),
    )


@pytest.fixture()
def ledger(monkeypatch):
    written: list[dict] = []
    monkeypatch.setattr(mem0_meter, "record", lambda **kwargs: written.append(kwargs))
    return written


def test_l_estrazione_dei_fatti_si_registra_con_i_suoi_token(ledger):
    memory = mem0_meter.meter(_memory())

    with operation(OperationKind.CHAT_TURN) as op:
        memory.llm.client.chat.completions.create(model="gpt-4o-mini", messages=[])

    (row,) = ledger
    assert row["task"] == LlmTask.MEMORY_EXTRACTION.value
    assert row["operation"].id == op.id
    assert row["model"] == "gpt-4o-mini-2024"
    assert (row["tokens"].input, row["tokens"].output, row["tokens"].cached_input) == (900, 60, 200)
    assert row["outcome"] == "ok"


def test_l_embedding_della_memoria_si_registra(ledger):
    memory = mem0_meter.meter(_memory())

    with operation(OperationKind.CHAT_TURN):
        memory.embedding_model.client.embeddings.create(model="text-embedding-3-small", input="x")

    (row,) = ledger
    assert row["task"] == LlmTask.MEMORY_EMBEDDING.value
    assert row["tokens"].input == 42
    assert row["model"] == "text-embedding-3-small"


def test_un_guasto_lascia_comunque_la_sua_riga(ledger):
    memory = mem0_meter.meter(_memory(chat=_Resource(exc=TimeoutError("lento"))))

    with operation(OperationKind.CHAT_TURN), pytest.raises(TimeoutError):
        memory.llm.client.chat.completions.create(model="gpt-4o-mini", messages=[])

    (row,) = ledger
    assert row["outcome"] == "timeout"
    assert row["error_kind"] == "TimeoutError"


def test_senza_operazione_la_riga_non_sparisce_e_lo_si_dice(ledger):
    degradation_counters.reset()
    memory = mem0_meter.meter(_memory())

    memory.embedding_model.client.embeddings.create(model="text-embedding-3-small", input="x")

    (row,) = ledger
    assert row["operation"].kind == OperationKind.MEMORY_PROJECTION
    assert degradation_counters.snapshot()["llm_usage:mem0_call_without_operation"] == 1


def test_avvolgere_due_volte_non_conta_due_volte(ledger):
    memory = mem0_meter.meter(mem0_meter.meter(_memory()))

    with operation(OperationKind.CHAT_TURN):
        memory.embedding_model.client.embeddings.create(model="m", input="x")

    assert len(ledger) == 1


def test_una_forma_sconosciuta_non_rompe_la_memoria():
    degradation_counters.reset()
    strange = SimpleNamespace()

    assert mem0_meter.meter(strange) is strange
    assert degradation_counters.snapshot()["llm_usage:mem0_unmetered"] == 2


def test_il_modello_di_ripiego_e_quello_configurato_per_mem0():
    from backend.llm import profile_for

    assert profile_for(LlmTask.MEMORY_EXTRACTION).model == settings.mem0_llm_model
    assert profile_for(LlmTask.MEMORY_EMBEDDING).model == settings.mem0_embedder_model


def test_la_memoria_vera_viene_avvolta(monkeypatch):
    """Contro la libreria installata: se Mem0 rinomina gli attributi, lo si vede qui."""
    pytest.importorskip("mem0")
    from mem0.embeddings.openai import OpenAIEmbedding
    from mem0.llms.openai import OpenAILLM

    # Nessuna chiamata parte: serve solo che l'SDK costruisca i client.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-non-usata")

    memory = SimpleNamespace(
        llm=OpenAILLM({"model": "gpt-4o-mini", "api_key": "sk-test"}),
        embedding_model=OpenAIEmbedding(),
    )
    degradation_counters.reset()

    mem0_meter.meter(memory)

    assert getattr(memory.llm.client.chat.completions.create, "_delir_metered", False)
    assert getattr(memory.embedding_model.client.embeddings.create, "_delir_metered", False)
    assert "llm_usage:mem0_unmetered" not in degradation_counters.snapshot()
