"""P1 — il gateway: una chiamata dichiara il compito e il lavoro, e lascia una riga.

Quello che si verifica qui e' la risposta alla domanda da cui e' partito tutto:
«dove sono andati i soldi ieri». Perche' sia una query e non un'indagine servono
tre garanzie, e sono le tre cose testate sotto:

- nessuna chiamata senza operazione aperta (L2), **anche dentro un thread**, che
  e' il caso in cui si perde davvero perche' i `ContextVar` non si ereditano;
- una riga per ogni chiamata, anche quando fallisce (L4);
- i token contati anche sulle chiamate strutturate, che sono quasi tutte.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import BaseModel

from backend.llm import (
    LlmTask,
    OperationKind,
    OperationNotOpen,
    Outcome,
    all_profiles,
    current_operation,
    inherit_operation,
    operation,
    profile_for,
    record_avoided_call,
    run,
)
from backend.llm.prices import estimate_cost
from backend.llm.usage import TokenUsage, extract_tokens
from backend.security import get_current_tenant_id
from backend.settings import settings


class _Verdict(BaseModel):
    answer: str


class _FakeMessage:
    """Una risposta con i token dove langchain li mette davvero."""

    def __init__(self, *, input_tokens=120, output_tokens=40, reasoning=12, cached=30):
        self.content = "ok"
        self.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_token_details": {"cache_read": cached},
            "output_token_details": {"reasoning": reasoning},
        }


@pytest.fixture()
def ledger(monkeypatch):
    """Cattura gli eventi di consumo, invece di scriverli sul database.

    Il test verifica *cosa* viene registrato; che la scrittura arrivi a Postgres
    e' verificato a parte in `test_the_ledger_write_never_breaks_the_work`.
    """
    written: list[dict] = []

    def _record(**kwargs):
        written.append(kwargs)

    monkeypatch.setattr("backend.llm.gateway.record", _record)
    return written


@pytest.fixture()
def con_chiave(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-non-usata")


@pytest.fixture()
def fake_provider(monkeypatch, con_chiave):
    """Sostituisce il client, non la rete: nessuna chiamata parte davvero."""
    state: dict = {"response": _FakeMessage(), "raise": None, "kwargs": None}

    class _FakeClient:
        def __init__(self, **kwargs):
            state["kwargs"] = kwargs

        def bind(self, **_kwargs):
            return self

        def with_structured_output(self, schema, include_raw=False):
            state["include_raw"] = include_raw
            state["schema"] = schema
            return self

        def stream(self, *_args, **_kwargs):
            if state["raise"] is not None:
                raise state["raise"]
            yield state["response"]

    monkeypatch.setattr("backend.llm.gateway._client", lambda *_a, **_k: _FakeClient())
    return state


class TestNienteChiamateSenzaOperazione:
    """L2. Una chiamata senza operazione e' spesa non attribuibile."""

    def test_una_chiamata_fuori_da_un_operazione_e_rifiutata(self, fake_provider):
        with pytest.raises(OperationNotOpen):
            run(task=LlmTask.PLAN_EXTRACTION, messages=[])

    def test_anche_un_colpo_di_cache_appartiene_a_un_lavoro(self):
        with pytest.raises(OperationNotOpen):
            record_avoided_call(LlmTask.PLAN_EXTRACTION)

    def test_l_operazione_porta_il_tenant_senza_che_nessuno_lo_passi(self):
        with operation(OperationKind.PLAN_SYNTHESIS) as opened:
            assert opened.tenant_id == get_current_tenant_id()
            assert opened.id

    def test_un_operazione_annidata_ricorda_il_padre(self):
        with operation(OperationKind.CHAT_TURN) as turno:
            with operation(OperationKind.BPMN_DRAFT) as disegno:
                assert disegno.parent_id == turno.id
                assert disegno.id != turno.id

    def test_l_operazione_si_chiude_uscendo(self):
        with operation(OperationKind.CHAT_TURN):
            assert current_operation() is not None
        assert current_operation() is None


class TestIThreadNonEreditanoDaSoli:
    """Il caso in cui la spesa si perde per davvero.

    Il pool di estrazione e' il posto dove facciamo le chiamate piu' care: una
    per intervista, in parallelo. Se l'operazione non entra nei thread, quelle
    chiamate sono esattamente quelle che non si vedono.
    """

    def test_senza_inherit_un_thread_perde_l_operazione(self):
        with operation(OperationKind.PLAN_SYNTHESIS):
            with ThreadPoolExecutor(max_workers=1) as pool:
                visto = pool.submit(current_operation).result()

        assert visto is None, (
            "se questo passa, i ContextVar hanno cambiato semantica e "
            "`inherit_operation` non serve piu'"
        )

    def test_con_inherit_l_operazione_entra_nei_thread(self):
        with operation(OperationKind.PLAN_SYNTHESIS, process_id="p-1") as aperta:
            leggi = inherit_operation(current_operation)
            with ThreadPoolExecutor(max_workers=3) as pool:
                viste = list(pool.map(lambda _: leggi(), range(6)))

        assert [op.id for op in viste] == [aperta.id] * 6, (
            "il lavoro in un thread e' lo *stesso* lavoro: un'operazione nuova "
            "per thread renderebbe illeggibile il costo per risultato"
        )
        assert {op.process_id for op in viste} == {"p-1"}

    def test_con_inherit_anche_il_tenant_entra_nei_thread(self):
        with operation(OperationKind.PLAN_SYNTHESIS):
            leggi = inherit_operation(get_current_tenant_id)
            with ThreadPoolExecutor(max_workers=2) as pool:
                viste = set(pool.map(lambda _: leggi(), range(4)))

        assert viste == {get_current_tenant_id()}


class TestOgniChiamataLasciaUnaRiga:
    """L4. Compresi i guasti: un timeout si paga."""

    def test_una_chiamata_riuscita_registra_i_token(self, fake_provider, ledger):
        with operation(OperationKind.PLAN_SYNTHESIS, process_id="p-9"):
            run(task=LlmTask.PLAN_EXTRACTION, messages=[], input_characters=4_000)

        assert len(ledger) == 1
        evento = ledger[0]
        assert evento["outcome"] == Outcome.OK
        assert evento["task"] == LlmTask.PLAN_EXTRACTION.value
        assert evento["tokens"].input == 120
        assert evento["tokens"].output == 40
        assert evento["tokens"].reasoning == 12
        assert evento["tokens"].cached_input == 30
        assert evento["operation"].process_id == "p-9"

    def test_un_timeout_ha_un_esito_suo(self, fake_provider, ledger):
        fake_provider["raise"] = TimeoutError("scaduto")

        with operation(OperationKind.PLAN_SYNTHESIS):
            with pytest.raises(TimeoutError):
                run(task=LlmTask.PLAN_EXTRACTION, messages=[])

        assert ledger[0]["outcome"] == Outcome.TIMEOUT, (
            "il timeout e' l'unico guasto pagato per intero: dentro `error` "
            "diventerebbe invisibile la voce da sorvegliare"
        )

    def test_un_guasto_qualunque_resta_registrato(self, fake_provider, ledger):
        fake_provider["raise"] = RuntimeError("provider giu'")

        with operation(OperationKind.PLAN_SYNTHESIS):
            with pytest.raises(RuntimeError):
                run(task=LlmTask.PLAN_EXTRACTION, messages=[])

        assert ledger[0]["outcome"] == Outcome.ERROR
        assert ledger[0]["error_kind"] == "RuntimeError"

    def test_una_chiamata_che_non_parte_per_mancanza_di_chiave_si_registra(
        self, monkeypatch, ledger
    ):
        """Senza questa riga, un'installazione senza chiave sembra efficiente."""
        from backend.llm_config import MissingProviderKey

        monkeypatch.setattr(settings, "openai_api_key", None)

        with operation(OperationKind.PLAN_SYNTHESIS):
            with pytest.raises(MissingProviderKey):
                run(task=LlmTask.PLAN_EXTRACTION, messages=[])

        assert ledger[0]["outcome"] == Outcome.REFUSED

    def test_una_chiamata_evitata_e_un_risultato_da_registrare(self, ledger):
        with operation(OperationKind.PLAN_SYNTHESIS):
            record_avoided_call(LlmTask.PLAN_EXTRACTION)

        assert ledger[0]["outcome"] == Outcome.CACHE_HIT, (
            "un risparmio che non si misura non si difende"
        )


class TestLeChiamateStrutturateSonoQuasiTutte:
    """Il difetto che avrebbe azzerato la misura senza che nessuno se ne accorgesse."""

    def test_una_risposta_strutturata_conta_i_token_dal_grezzo(self, fake_provider, ledger):
        fake_provider["response"] = {
            "raw": _FakeMessage(input_tokens=900, output_tokens=75),
            "parsed": _Verdict(answer="si"),
            "parsing_error": None,
        }

        with operation(OperationKind.CONFORMANCE_AUDIT):
            verdetto = run(
                task=LlmTask.CONFORMANCE_AUDIT, messages=[], output=_Verdict
            )

        assert isinstance(verdetto, _Verdict), "a chi chiama torna il parsato"
        assert fake_provider["include_raw"] is True, (
            "senza include_raw il grezzo non arriva e ogni chiamata strutturata "
            "risulterebbe da zero token"
        )
        assert ledger[0]["tokens"].input == 900
        assert ledger[0]["tokens"].output == 75

    def test_uno_schema_non_rispettato_e_un_errore_pagato(self, fake_provider, ledger):
        fake_provider["response"] = {
            "raw": _FakeMessage(input_tokens=500, output_tokens=20),
            "parsed": None,
            "parsing_error": ValueError("schema"),
        }

        with operation(OperationKind.CONFORMANCE_AUDIT):
            with pytest.raises(ValueError):
                run(task=LlmTask.CONFORMANCE_AUDIT, messages=[], output=_Verdict)

        evento = ledger[0]
        assert evento["outcome"] == Outcome.ERROR
        assert evento["error_kind"] == "invalid_structured_output"
        assert evento["tokens"].input == 500, "il fornitore ha risposto, e va pagato"


class TestIlRegistroDeiCompiti:
    def test_ogni_compito_ha_un_profilo(self):
        """Un default silenzioso rimetterebbe in piedi il `medium` per tutto."""
        for task in LlmTask:
            assert profile_for(task).task is task

    def test_i_compiti_con_una_coda_dietro_non_ritentano(self):
        for task in (
            LlmTask.PLAN_EXTRACTION,
            LlmTask.PLAN_UNIFICATION,
            LlmTask.CONFORMANCE_AUDIT,
        ):
            assert profile_for(task).retry is False

    def test_i_path_interattivi_ritentano(self):
        for task in (LlmTask.CHAT_TURN, LlmTask.CONTEXT_ROUTING, LlmTask.TRANSCRIPTION):
            assert profile_for(task).retry is True

    def test_dove_l_output_e_uno_schema_strict_non_si_paga_ragionamento(self):
        """Lo schema fa il lavoro: il `medium` per sette compiti era un default."""
        for task in (LlmTask.ENTITY_RESOLUTION, LlmTask.RETRIEVAL_RERANK):
            assert profile_for(task).reasoning_effort == "none"

    def test_il_timeout_scala_solo_dove_l_input_e_lungo(self):
        assert profile_for(LlmTask.PLAN_EXTRACTION).scales_with_input is True
        assert profile_for(LlmTask.RETRIEVAL_RERANK).scales_with_input is False

    def test_i_profili_sono_esposti_tutti(self):
        assert set(all_profiles()) == set(LlmTask)


class TestIlClientRiceveLaPolicyDelProfilo:
    """Contro il costruttore vero, non contro un doppio permissivo.

    La prima versione di `_client` passava `max_retries` con `bind`, che aggiunge
    kwargs **alla chiamata API**: il fornitore l'avrebbe rifiutato come parametro
    sconosciuto. Il doppio usato negli altri test ignorava `bind`, quindi non
    poteva vederlo. Qui si guarda cosa arriva al costruttore.
    """

    @pytest.fixture()
    def costruito(self, monkeypatch, con_chiave):
        visti: dict = {}

        class _FakeChatOpenAI:
            def __init__(self, **kwargs):
                visti.update(kwargs)

        import langchain_openai

        monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
        return visti

    def test_i_retry_arrivano_al_costruttore(self, costruito):
        from backend.llm.gateway import _client

        _client(profile_for(LlmTask.PLAN_EXTRACTION), 1_000)

        assert costruito["max_retries"] == settings.model_max_retries

    def test_un_compito_interattivo_riceve_i_suoi_retry(self, costruito):
        from backend.llm.gateway import _client

        _client(profile_for(LlmTask.CHAT_TURN), None)

        assert costruito["max_retries"] == settings.agent_max_retries

    def test_il_ragionamento_del_profilo_arriva_al_client(self, costruito):
        from backend.llm.gateway import _client

        _client(profile_for(LlmTask.ENTITY_RESOLUTION), None)

        assert costruito.get("reasoning_effort") in {"none", None}

    def test_un_compito_che_scala_riceve_un_timeout_piu_lungo(self, costruito):
        from backend.llm.gateway import _client

        _client(profile_for(LlmTask.PLAN_EXTRACTION), 20_000)
        lungo = costruito["timeout"]

        _client(profile_for(LlmTask.RETRIEVAL_RERANK), 20_000)
        corto = costruito["timeout"]

        assert lungo > corto, (
            "il rerank legge poco: un timeout lungo allunga solo il tempo per "
            "accorgersi del guasto"
        )


class TestIlCostoNonSiInventa:
    def test_senza_listino_il_costo_e_ignoto_non_zero(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_prices_json", "")

        assert estimate_cost("gpt-x", input_tokens=1_000, output_tokens=500) is None, (
            "zero direbbe 'gratis'; None dice 'non lo sappiamo', ed e' vero"
        )

    def test_con_il_listino_il_costo_si_calcola_per_milione(self, monkeypatch):
        monkeypatch.setattr(
            settings,
            "llm_prices_json",
            '{"gpt-x": {"input": 1.0, "output": 10.0}}',
        )

        costo = estimate_cost("gpt-x", input_tokens=1_000_000, output_tokens=100_000)

        assert costo is not None
        assert float(costo) == pytest.approx(2.0)

    def test_i_token_in_cache_costano_meno_quando_il_listino_lo_dice(self, monkeypatch):
        monkeypatch.setattr(
            settings,
            "llm_prices_json",
            '{"gpt-x": {"input": 10.0, "output": 10.0, "cached_input": 1.0}}',
        )

        pieno = estimate_cost("gpt-x", input_tokens=1_000_000, output_tokens=0)
        in_cache = estimate_cost(
            "gpt-x", input_tokens=1_000_000, output_tokens=0, cached_input_tokens=1_000_000
        )

        assert in_cache is not None and pieno is not None
        assert in_cache < pieno

    def test_senza_prezzo_di_cache_i_token_in_cache_si_contano_pieni(self, monkeypatch):
        """Sovrastimare e' l'errore giusto: un budget non si sfonda per ottimismo."""
        monkeypatch.setattr(
            settings, "llm_prices_json", '{"gpt-x": {"input": 10.0, "output": 10.0}}'
        )

        costo = estimate_cost(
            "gpt-x", input_tokens=1_000_000, output_tokens=0, cached_input_tokens=1_000_000
        )

        assert costo is not None and float(costo) == pytest.approx(10.0)

    def test_un_listino_illeggibile_non_ferma_il_prodotto(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_prices_json", "{non json")

        assert estimate_cost("gpt-x", input_tokens=10, output_tokens=10) is None

    def test_il_ragionamento_non_si_conta_due_volte(self, monkeypatch):
        """Il fornitore li fattura come uscita: sono dentro `output`, non accanto."""
        monkeypatch.setattr(
            settings, "llm_prices_json", '{"gpt-x": {"input": 0.0, "output": 10.0}}'
        )

        costo = estimate_cost("gpt-x", input_tokens=0, output_tokens=1_000_000)

        assert costo is not None and float(costo) == pytest.approx(10.0)


class TestLeggereIToken:
    def test_una_risposta_senza_metadata_da_zero_non_un_errore(self):
        assert extract_tokens(object()) == TokenUsage()

    def test_i_dettagli_annidati_si_leggono(self):
        tokens = extract_tokens(_FakeMessage(input_tokens=10, output_tokens=5, reasoning=2, cached=3))

        assert (tokens.input, tokens.output, tokens.reasoning, tokens.cached_input) == (10, 5, 2, 3)

    def test_valori_assurdi_non_entrano_nel_registro(self):
        class _Sporca:
            usage_metadata = {"input_tokens": -5, "output_tokens": "molti"}

        assert extract_tokens(_Sporca()) == TokenUsage()


def test_the_ledger_write_never_breaks_the_work(monkeypatch):
    """Un sistema di misura che rompe cio' che misura viene spento, e allora non
    misura piu' niente."""
    from backend.llm import usage

    def _explode(*_args, **_kwargs):
        raise RuntimeError("database occupato")

    monkeypatch.setattr("backend.workspace_storage.workspace_connection", _explode)

    with operation(OperationKind.PLAN_SYNTHESIS) as opened:
        usage.record(
            operation=opened,
            task=LlmTask.PLAN_EXTRACTION.value,
            model="gpt-x",
            outcome=Outcome.OK,
            tokens=TokenUsage(input=10, output=2),
        )


def test_the_ledger_row_reaches_postgres():
    """La riga arriva davvero, con le dimensioni con cui si legge la spesa."""
    from sqlalchemy import select

    from backend.llm import usage
    from backend.workspace_storage import WorkspaceLlmUsage, workspace_connection

    with operation(OperationKind.PLAN_SYNTHESIS, project_id="proj-1", process_id="proc-1") as opened:
        usage.record(
            operation=opened,
            task=LlmTask.PLAN_EXTRACTION.value,
            model="gpt-test-ledger",
            outcome=Outcome.OK,
            tokens=TokenUsage(input=321, output=21, reasoning=7, cached_input=100),
            duration_ms=1234,
            prompt_version="plan_extraction@3",
            reasoning_effort="medium",
        )

    with workspace_connection() as session:
        row = session.scalars(
            select(WorkspaceLlmUsage).where(WorkspaceLlmUsage.operation_id == opened.id)
        ).one()

        assert row.tenant_id == opened.tenant_id
        assert row.operation_kind == OperationKind.PLAN_SYNTHESIS
        assert (row.project_id, row.process_id) == ("proj-1", "proc-1")
        assert row.task == LlmTask.PLAN_EXTRACTION.value
        assert (row.input_tokens, row.output_tokens) == (321, 21)
        assert (row.reasoning_tokens, row.cached_input_tokens) == (7, 100)
        assert row.prompt_version == "plan_extraction@3"
        assert row.duration_ms == 1234
        assert row.created_at


# --------------------------------------------------------------------------- #
# t.4 — l'embedding
# --------------------------------------------------------------------------- #


class _FakeEmbeddingResponse:
    """La risposta dell'SDK OpenAI: i token stanno altrove rispetto a langchain."""

    def __init__(self, *, vectors, prompt_tokens=77):
        self.data = [type("_Item", (), {"embedding": v})() for v in vectors]
        self.usage = type("_Usage", (), {"prompt_tokens": prompt_tokens, "total_tokens": prompt_tokens})()


@pytest.fixture()
def fake_embedder(monkeypatch, con_chiave):
    state: dict = {"response": None, "raise": None, "kwargs": None}

    class _FakeEmbeddings:
        def create(self, **kwargs):
            state["kwargs"] = kwargs
            if state["raise"] is not None:
                raise state["raise"]
            n = len(kwargs.get("input") or [])
            return state["response"] or _FakeEmbeddingResponse(vectors=[[0.1] * 3 for _ in range(n)])

    class _FakeClient:
        embeddings = _FakeEmbeddings()

    monkeypatch.setattr("backend.llm.gateway._embedding_client", lambda: _FakeClient())
    return state


class TestLEmbeddingPassaDalGateway:
    """t.4. Nell'ingestione KG il volume sta qui: un registro che salta gli
    embedding racconta una spesa che non e' quella vera."""

    def test_un_embedding_fuori_da_un_operazione_e_rifiutato(self, fake_embedder):
        from backend.llm import embed

        with pytest.raises(OperationNotOpen):
            embed(texts=["a"], dimensions=1536)

    def test_i_token_si_leggono_da_usage_prompt_tokens(self, fake_embedder, ledger):
        from backend.llm import embed

        with operation(OperationKind.KG_INGESTION):
            vettori = embed(texts=["a", "b"], dimensions=1536)

        assert len(vettori) == 2
        evento = ledger[0]
        assert evento["task"] == LlmTask.EMBEDDING.value
        assert evento["outcome"] == Outcome.OK
        # `extract_tokens`, il lettore della chat, qui avrebbe dato zero.
        assert evento["tokens"] == TokenUsage(input=77)

    def test_il_modello_e_quello_del_contratto_non_quello_della_chat(self, fake_embedder, ledger):
        from backend.llm import embed

        with operation(OperationKind.KG_INGESTION):
            embed(texts=["a"], dimensions=1536)

        assert fake_embedder["kwargs"]["model"] == "text-embedding-3-small"
        assert fake_embedder["kwargs"]["dimensions"] == 1536
        assert ledger[0]["model"] == "text-embedding-3-small"
        assert ledger[0]["model"] != settings.openai_model

    def test_il_profilo_dell_embedding_non_puo_divergere_dal_contratto(self):
        """Il modello sta scritto in due posti: qui si verifica che dicano lo stesso.

        `tasks.py` non importa `memory.embeddings` di proposito - il registro dei
        compiti non deve dipendere dalla memoria - quindi il disallineamento lo
        deve intercettare un test, non la lettura di chi passa.
        """
        from backend.memory import embeddings

        assert profile_for(LlmTask.EMBEDDING).model == embeddings.EMBED_MODEL

    def test_un_guasto_lascia_comunque_la_sua_riga(self, fake_embedder, ledger):
        from backend.llm import embed

        fake_embedder["raise"] = TimeoutError("troppo lento")
        with operation(OperationKind.KG_INGESTION):
            with pytest.raises(TimeoutError):
                embed(texts=["a"], dimensions=1536)

        assert ledger[0]["outcome"] == Outcome.TIMEOUT
        assert ledger[0]["error_kind"] == "TimeoutError"

    def test_senza_chiave_si_registra_il_rifiuto(self, monkeypatch, ledger):
        from backend.llm import embed
        from backend.llm_config import MissingProviderKey

        monkeypatch.setattr(settings, "openai_api_key", "")
        from backend.llm import gateway

        gateway._embedding_client.cache_clear()
        with operation(OperationKind.KG_INGESTION):
            with pytest.raises(MissingProviderKey):
                embed(texts=["a"], dimensions=1536)

        assert ledger[0]["outcome"] == Outcome.REFUSED
        assert ledger[0]["error_kind"] == "MissingProviderKey"
