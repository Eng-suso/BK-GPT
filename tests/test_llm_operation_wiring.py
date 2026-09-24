"""P1.5 tappa 1-2 — l'operazione arriva dove si spende.

Il gateway rifiuta una chiamata senza operazione aperta (L2). E' una garanzia
utile solo se i punti d'ingresso l'operazione la aprono davvero: altrimenti L2
non protegge la misura, rompe il prodotto.

Questi test guardano il percorso vero, non l'unita': dalla riga di coda fino
dentro i thread del pool di estrazione, che e' il punto dove la spesa si perdeva
perche' i `ContextVar` non si ereditano.
"""

from __future__ import annotations

import pytest

from backend.llm import OperationKind, current_operation


def _plan(title: str, actor: str, step: str):
    """Un piano minimo ma **valido**.

    Se non lo e', `_extract` cattura l'errore di validazione come guasto
    ritentabile e ogni fonte viene estratta due volte: il test conterebbe il
    doppio delle chiamate e sembrerebbe un difetto del codice.
    """
    from backend.process_understanding import (
        ProcessActor,
        ProcessStep,
        ProcessUnderstanding,
        ProcessUnderstandingResult,
    )

    return ProcessUnderstandingResult(
        status="success",
        process=ProcessUnderstanding(
            title=title,
            actors=[ProcessActor(id=actor, label=actor.title(), kind="team")],
            steps=[ProcessStep(id=step, label=step.replace("_", " "), actor_ids=[actor])],
        ),
    )


def test_the_extraction_pool_carries_the_operation_into_its_threads(monkeypatch):
    """Le chiamate piu' care che facciamo: una per intervista, in parallelo.

    Se l'operazione non entra nei thread, sono esattamente quelle che non si
    vedono nel registro — e sono la maggior parte della spesa.
    """
    from backend.agents import process_synthesis
    from backend.llm import operation

    viste: list[object] = []

    def _fake_extraction(title, source_text, *, with_quality_report=True):
        viste.append(current_operation())
        return _plan(title, "ufficio_tecnico", "apri_richiesta")

    monkeypatch.setattr(process_synthesis, "build_process_understanding", _fake_extraction)

    sources = [
        {"id": f"s{n}", "name": f"Intervista {n}", "content": f"Testo della voce {n}."}
        for n in range(4)
    ]

    with operation(OperationKind.PLAN_SYNTHESIS, process_id="proc-42") as aperta:
        process_synthesis.extract_plan_from_sources("Ciclo passivo", sources)

    assert len(viste) == len(sources), (
        "una chiamata per fonte: se sono il doppio, il doppio del test non "
        "restituisce un piano valido e il retry per fonte sta scattando"
    )
    assert all(op is not None for op in viste), (
        "un'estrazione senza operazione e' spesa non attribuibile, ed e' il "
        "difetto per cui il credito e' finito senza che si sapesse dove"
    )
    assert {op.id for op in viste} == {aperta.id}, (
        "il lavoro in un thread e' lo *stesso* lavoro: un'operazione nuova per "
        "thread renderebbe illeggibile il costo per risultato"
    )
    assert {op.process_id for op in viste} == {"proc-42"}


def test_the_extraction_pool_carries_the_tenant_too(monkeypatch):
    """Il tenant nei thread era gia' un problema noto in questo repo.

    `test_product_language` lo dice a parole: «l'agente gira in un thread proprio,
    che non eredita la contextvar del tenant». Qui quella perdita e' chiusa per il
    pool di estrazione, e verificata.
    """
    from backend.agents import process_synthesis
    from backend.llm import operation
    from backend.security import get_current_tenant_id

    tenant_visti: list[str] = []

    def _fake_extraction(title, source_text, *, with_quality_report=True):
        tenant_visti.append(get_current_tenant_id())
        return _plan(title, "ufficio_tecnico", "apri_richiesta")

    monkeypatch.setattr(process_synthesis, "build_process_understanding", _fake_extraction)

    sources = [
        {"id": "s1", "name": "Intervista 1", "content": "Prima voce."},
        {"id": "s2", "name": "Intervista 2", "content": "Seconda voce."},
    ]

    with operation(OperationKind.PLAN_SYNTHESIS, tenant_id="acme"):
        process_synthesis.extract_plan_from_sources("Ciclo passivo", sources)

    assert tenant_visti == ["acme", "acme"]


class TestIPuntiDIngressoApronoLOperazione:
    """Se un ingresso si dimentica, L2 non protegge la misura: rompe il prodotto."""

    def test_la_coda_dei_piani_apre_un_operazione_di_sintesi(self, monkeypatch):
        from backend.workers import plan_worker

        vista: dict = {}

        def _fake_ensure(process_id):
            op = current_operation()
            vista["kind"] = op.kind if op else None
            vista["process_id"] = op.process_id if op else None
            vista["tenant_id"] = op.tenant_id if op else None
            raise RuntimeError("basta: quello che serve l'abbiamo letto")

        monkeypatch.setattr(
            "backend.agents.process_synthesis.ensure_process_plan", _fake_ensure
        )
        monkeypatch.setattr(plan_worker.wd, "fail_plan_materialization", lambda *a, **k: None)

        plan_worker._work_one(
            {"id": 1, "tenant_id": "acme", "process_id": "proc-7"}
        )

        assert vista["kind"] == OperationKind.PLAN_SYNTHESIS
        assert vista["process_id"] == "proc-7"
        assert vista["tenant_id"] == "acme"

    def test_la_coda_dei_confronti_apre_un_operazione_di_revisione(self, monkeypatch):
        from backend.workers import conformance_worker

        vista: dict = {}

        def _fake_audit(process_id):
            op = current_operation()
            vista["kind"] = op.kind if op else None
            vista["process_id"] = op.process_id if op else None
            vista["tenant_id"] = op.tenant_id if op else None
            return None

        monkeypatch.setattr(
            "backend.agents.conformance_audit.audit_process_conformance", _fake_audit
        )
        monkeypatch.setattr(
            conformance_worker.wd, "release_conformance_check", lambda *a, **k: None
        )

        conformance_worker._work_one(
            {"id": 1, "tenant_id": "acme", "process_id": "proc-9", "bpmn_model_id": "bpmn-9"}
        )

        assert vista["kind"] == OperationKind.CONFORMANCE_AUDIT
        assert vista["process_id"] == "proc-9"
        assert vista["tenant_id"] == "acme"

    def test_l_operazione_si_chiude_anche_quando_il_lavoro_fallisce(self, monkeypatch):
        """Un'operazione che resta aperta dopo un guasto attribuirebbe la spesa
        della riga successiva a quella di prima."""
        from backend.workers import plan_worker

        def _boom(process_id):
            raise RuntimeError("guasto")

        monkeypatch.setattr("backend.agents.process_synthesis.ensure_process_plan", _boom)
        monkeypatch.setattr(plan_worker.wd, "fail_plan_materialization", lambda *a, **k: None)

        plan_worker._work_one({"id": 1, "tenant_id": "acme", "process_id": "proc-7"})

        assert current_operation() is None


class TestICompitiABassoRischioPassanoDalGateway:
    """t.3 — reranker ed entity resolution.

    Entrambi avevano un client costruito in casa e una cache da invalidare.
    Adesso chiedono al gateway, e quello che resta nel modulo e' la sola domanda
    che il chiamante deve poter fare: «e' possibile, adesso, riordinare / dare un
    giudizio?».
    """

    def test_il_reranker_esiste_solo_se_c_e_una_chiave(self, monkeypatch):
        from backend.memory import reranker
        from backend.settings import settings

        reranker.build_reranker.cache_clear()
        monkeypatch.setattr(settings, "openai_api_key", None)
        assert reranker.build_reranker() is None

        reranker.build_reranker.cache_clear()
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")
        assert reranker.build_reranker() is not None
        reranker.build_reranker.cache_clear()

    def test_il_reranker_chiede_al_gateway_col_compito_giusto(self, monkeypatch):
        """Che il gateway poi registri e' verificato in `test_llm_gateway.py`:
        qui conta che il compito dichiarato sia quello, perche' e' il compito a
        decidere modello, ragionamento e timeout."""
        from backend.llm import LlmTask, operation
        from backend.memory import reranker

        chiamate: list[dict] = []

        class _Verdetto:
            order = [2, 0, 1]

        def _fake_run(**kwargs):
            chiamate.append(kwargs)
            return _Verdetto()

        monkeypatch.setattr("backend.memory.reranker.llm_run", _fake_run)

        with operation(OperationKind.CHAT_TURN):
            ordine = reranker.LLMReranker().order("domanda", ["a", "b", "c"])

        assert ordine == [2, 0, 1]
        assert chiamate[0]["task"] is LlmTask.RETRIEVAL_RERANK
        assert chiamate[0]["output"] is reranker._RerankVerdict

    def test_un_modello_iniettato_resta_il_seam_dei_test(self, monkeypatch):
        """Il gateway non chiude la porta a un doppio deterministico."""
        from backend.memory import reranker

        class _Finto:
            def stream(self, *_a, **_k):
                class _V:
                    order = [1, 0]

                yield _V()

        def _non_chiamare(**_kwargs):
            raise AssertionError("con un modello iniettato il gateway non si tocca")

        monkeypatch.setattr("backend.memory.reranker.llm_run", _non_chiamare)

        assert reranker.LLMReranker(_Finto()).order("q", ["a", "b"]) == [1, 0]

    def test_il_resolver_dichiara_il_gateway_invece_di_costruire_un_client(self, monkeypatch):
        from backend.memory.knowledge_graph import entity_resolution as er
        from backend.settings import settings

        monkeypatch.setattr(settings, "openai_api_key", None)
        assert er.build_llm() is None, "senza chiave non si tenta il merge fuzzy"

        monkeypatch.setattr(settings, "openai_api_key", "sk-test")
        assert er.build_llm() is er.GATEWAY

    def test_il_resolver_non_ha_piu_un_singleton_da_invalidare(self):
        """Una cache globale in meno e' una fonte di stato fra test in meno."""
        from backend.memory.knowledge_graph import entity_resolution as er

        assert not hasattr(er, "_llm_singleton")


def test_the_ingestion_worker_opens_its_operation(monkeypatch):
    """Dentro l'ingestione girano gli embedding e il giudizio di entity resolution.

    Senza operazione aperta il gateway rifiuta, l'`except` largo del resolver lo
    inghiotte, e il grafo accumula duplicati in silenzio: il guasto peggiore,
    perche' non si vede.
    """
    from backend.memory.knowledge_graph import canonical
    from backend.workers import ingest_worker

    vista: dict = {}

    class _Row:
        id = 1
        payload = {
            "consultant_id": "c1",
            "client_id": "cli-1",
            "project_id": "proj-3",
            "process_id": "proc-3",
            "entities": [],
        }

    def _fake_write_evidence(**_payload):
        op = current_operation()
        vista["kind"] = op.kind if op else None
        vista["project_id"] = op.project_id if op else None
        vista["process_id"] = op.process_id if op else None
        return {}

    monkeypatch.setattr(ingest_worker, "_consultant", lambda: "c1")
    monkeypatch.setattr(ingest_worker, "_requeue_stuck", lambda *_a, **_k: None)
    monkeypatch.setattr(ingest_worker, "_claim", lambda *_a, **_k: [_Row()])
    monkeypatch.setattr(ingest_worker, "_mark_done", lambda *_a, **_k: True)
    monkeypatch.setattr(canonical, "write_evidence", _fake_write_evidence)
    monkeypatch.setattr(ingest_worker.settings, "canonical_database_url", "postgresql://x/y")

    assert ingest_worker.drain_once() == 1
    assert vista["kind"] == OperationKind.KG_INGESTION
    assert (vista["project_id"], vista["process_id"]) == ("proj-3", "proc-3")


class TestGliEmbeddingPassanoDalGateway:
    """t.4 — `memory/embeddings.py`.

    Il modulo mantiene il suo contratto («mai solleva, degrada a `None`») con
    una sola eccezione dichiarata: il rifiuto per operazione mancante. Degradare
    anche quello spegnerebbe il retrieval vettoriale in silenzio, e il sintomo
    arriverebbe al consulente come «le risposte sono peggiorate».
    """

    def test_l_embedding_chiede_al_gateway_con_la_dimensione_del_contratto(self, monkeypatch):
        from backend.memory import embeddings

        visto: dict = {}

        def _fake_embed(*, texts, dimensions):
            visto["texts"] = texts
            visto["dimensions"] = dimensions
            return [[0.5] * 3 for _ in texts]

        monkeypatch.setattr(embeddings.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr("backend.memory.embeddings.embed", _fake_embed)

        assert embeddings.embed_texts(["uno", "due"]) == [[0.5] * 3, [0.5] * 3]
        assert visto["dimensions"] == embeddings.EMBED_DIM

    def test_un_guasto_del_fornitore_degrada_a_none(self, monkeypatch):
        from backend.memory import embeddings

        def _esplode(**_kwargs):
            raise RuntimeError("fornitore giu'")

        monkeypatch.setattr(embeddings.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr("backend.memory.embeddings.embed", _esplode)

        assert embeddings.embed_texts(["uno"]) is None

    def test_ma_un_punto_d_ingresso_dimenticato_non_degrada(self, monkeypatch):
        from backend.llm import OperationNotOpen
        from backend.memory import embeddings

        def _rifiuta(**_kwargs):
            raise OperationNotOpen("nessuna operazione")

        monkeypatch.setattr(embeddings.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr("backend.memory.embeddings.embed", _rifiuta)

        with pytest.raises(OperationNotOpen):
            embeddings.embed_texts(["uno"])

    def test_senza_chiave_non_si_arriva_nemmeno_al_gateway(self, monkeypatch):
        from backend.memory import embeddings

        def _non_chiamare(**_kwargs):
            raise AssertionError("senza chiave non si chiede niente al gateway")

        monkeypatch.setattr(embeddings.settings, "openai_api_key", "")
        monkeypatch.setattr("backend.memory.embeddings.embed", _non_chiamare)

        assert embeddings.embed_texts(["uno"]) is None

    def test_il_modulo_non_costruisce_piu_un_client(self):
        from backend.memory import embeddings

        assert not hasattr(embeddings, "_client")


def test_the_entity_sweep_script_opens_its_operation(monkeypatch):
    """Lo sweep periodico embedda e chiede giudizi: e' un punto d'ingresso.

    Gira da riga di comando, fuori da ogni richiesta e da ogni worker, ed e' il
    posto piu' facile da dimenticare proprio perche' non e' prodotto.
    """
    import argparse

    from backend.security import get_current_tenant_id
    from scripts import kg_resolve_entities as script

    vista: dict = {}

    def _fake_backfill(consultant, client, apply):
        op = current_operation()
        vista["kind"] = op.kind if op else None
        vista["tenant_id"] = op.tenant_id if op else None
        return 0

    monkeypatch.setattr(script, "_clients", lambda *_a, **_k: ["cli-1"])
    monkeypatch.setattr(script, "backfill_client", _fake_backfill)

    args = argparse.Namespace(
        consultant="consulente-1", client=None, apply=False,
        no_backfill=False, no_sweep=True, limit=10,
    )
    script.run(args)

    assert vista["kind"] == OperationKind.KG_INGESTION
    # Il tenant e' quello workspace, non l'id del consulente canonical: sono due
    # spazi di id, e mescolarli nella stessa colonna e' l'errore gia' corretto
    # una volta su `project_id`.
    assert vista["tenant_id"] == get_current_tenant_id()

class TestIlRifiutoL2NonSiDegradaMai:
    """La regola che tiene in piedi tutte le tappe: `OperationNotOpen` risale.

    I compiti best-effort hanno un `except` largo di proposito - un rerank
    saltato non deve far cadere una risposta - ma quel largo inghiottiva anche
    il rifiuto del gateway. Il risultato sarebbe il peggiore possibile: il
    prodotto continua a funzionare *peggio*, e non lo dice nessuno. Qui si
    verifica un modulo per volta, perche' ognuno ha il suo `except`.
    """

    def test_il_reranker_lo_lascia_passare(self, monkeypatch):
        from backend.llm import OperationNotOpen
        from backend.memory import reranker

        def _rifiuta(**_kwargs):
            raise OperationNotOpen("nessuna operazione")

        monkeypatch.setattr("backend.memory.reranker.llm_run", _rifiuta)
        with pytest.raises(OperationNotOpen):
            reranker.LLMReranker().order("domanda", ["a", "b"])

    def test_il_resolver_lo_lascia_passare(self, monkeypatch):
        from backend.llm import OperationNotOpen
        from backend.memory.knowledge_graph import entity_resolution as er

        def _rifiuta(**_kwargs):
            raise OperationNotOpen("nessuna operazione")

        monkeypatch.setattr("backend.memory.knowledge_graph.entity_resolution.llm_run", _rifiuta)
        with pytest.raises(OperationNotOpen):
            er.adjudicate(
                name="Ufficio crediti",
                entity_type="other",
                context="",
                candidates=[
                    er.Candidate(
                        entity_id="e1",
                        canonical_name="Ufficio credito",
                        entity_type="other",
                        trgm=0.8,
                    )
                ],
                llm=er.GATEWAY,
            )

    def test_l_estrazione_dei_playbook_lo_lascia_passare(self, monkeypatch):
        from backend.llm import OperationNotOpen
        from backend.memory.procedural import extraction

        def _rifiuta(**_kwargs):
            raise OperationNotOpen("nessuna operazione")

        monkeypatch.setattr(extraction.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr("backend.memory.procedural.extraction.llm_run", _rifiuta)
        with pytest.raises(OperationNotOpen):
            extraction.extract_playbook_from_episodes(
                [{"title": "a", "summary": "x"}, {"title": "b", "summary": "y"}]
            )


class TestIPlaybookPassanoDalGateway:
    """t.3bis — `memory/procedural/extraction.py`, la coda di t.3.

    Era nell'elenco della tappa e non era stato migrato: costruiva ancora due
    `ChatOpenAI` suoi, quindi il suo apprendimento era spesa senza nome.
    """

    def test_l_estrazione_chiede_al_gateway_col_compito_giusto(self, monkeypatch):
        from backend.llm import LlmTask
        from backend.memory.procedural import extraction

        chiamate: list[dict] = []

        def _fake_run(**kwargs):
            chiamate.append(kwargs)
            return extraction.ExtractedPlaybook(title="Metodo", body="Passi", confidence=0.5)

        monkeypatch.setattr(extraction.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr("backend.memory.procedural.extraction.llm_run", _fake_run)

        risultato = extraction.extract_playbook_from_episodes(
            [{"title": "a", "summary": "x"}, {"title": "b", "summary": "y"}]
        )

        assert risultato is not None and risultato.title == "Metodo"
        assert chiamate[0]["task"] is LlmTask.PLAYBOOK_EXTRACTION
        assert chiamate[0]["output"] is extraction.ExtractedPlaybook

    def test_la_generalizzazione_dichiara_il_compito_suo(self, monkeypatch):
        from backend.llm import LlmTask
        from backend.memory.procedural import extraction

        chiamate: list[dict] = []

        def _fake_run(**kwargs):
            chiamate.append(kwargs)
            return extraction.GeneralizedPlaybook(title="Generico", body="Passi")

        monkeypatch.setattr(extraction.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr("backend.memory.procedural.extraction.llm_run", _fake_run)

        extraction.generalize_playbook_body({"title": "t", "body": "b"}, ["Acme"])

        assert chiamate[0]["task"] is LlmTask.PLAYBOOK_GENERALIZATION

    def test_un_modello_iniettato_resta_il_seam_dei_test(self, monkeypatch):
        from backend.memory.procedural import extraction

        class _Finto:
            def stream(self, *_a, **_k):
                yield extraction.ExtractedPlaybook(title="Iniettato", body="Passi")

        def _non_chiamare(**_kwargs):
            raise AssertionError("con un modello iniettato il gateway non si tocca")

        monkeypatch.setattr("backend.memory.procedural.extraction.llm_run", _non_chiamare)

        risultato = extraction.extract_playbook_from_episodes(
            [{"title": "a", "summary": "x"}, {"title": "b", "summary": "y"}],
            llm=_Finto(),
        )
        assert risultato is not None and risultato.title == "Iniettato"

    def test_senza_chiave_non_si_tenta(self, monkeypatch):
        from backend.memory.procedural import extraction

        monkeypatch.setattr(extraction.settings, "openai_api_key", "")
        assert extraction.extract_playbook_from_episodes(
            [{"title": "a", "summary": "x"}, {"title": "b", "summary": "y"}]
        ) is None

    def test_il_modulo_non_costruisce_piu_client(self):
        from backend.memory.procedural import extraction

        assert not hasattr(extraction, "_extract_llm")
        assert not hasattr(extraction, "_generalize_llm")


class TestIlPercorsoCaldoPassaDalGateway:
    """t.5 — estrazione, giudizio di qualita', revisore, unificazione.

    Sono le quattro chiamate piu' care che facciamo, e fino a qui erano le
    uniche rimaste a costruirsi il client da sole. Quello che si verifica non e'
    che "funzionano": e' che **dichiarano il compito giusto** e passano la
    lunghezza dell'input, perche' e' da li' che il gateway ricava il timeout e
    il registro ricava la riga.
    """

    def test_l_estrazione_dichiara_il_compito_e_la_lunghezza_vera(self, monkeypatch):
        from backend.llm import LlmTask
        from backend import process_understanding as pu

        chiamate: list[dict] = []

        def _fake_run(**kwargs):
            chiamate.append(kwargs)
            return pu.ProcessUnderstanding(
                title="T", objective="O", scope="S",
            )

        note = "una nota di intervista" * 40
        monkeypatch.setattr(pu.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr("backend.process_understanding.llm_run", _fake_run)

        esito = pu.build_process_understanding("Processo", note, with_quality_report=False)

        assert esito.status == "success"
        assert chiamate[0]["task"] is LlmTask.PLAN_EXTRACTION
        assert chiamate[0]["output"] is pu.ProcessUnderstanding
        # La lunghezza vera, non una fascia arrotondata: il timeout lo calcola
        # il gateway e la cache per scaglioni non serve piu' a nessuno.
        assert chiamate[0]["input_characters"] == len(note)

    def test_il_giudizio_di_qualita_dichiara_il_compito_suo(self, monkeypatch):
        from backend.llm import LlmTask
        from backend import process_understanding as pu

        chiamate: list[dict] = []

        def _fake_run(**kwargs):
            chiamate.append(kwargs)
            return pu.ProcessUnderstandingQualityReport(
                overall_score=7, dimensions=[], blocking_gaps=[], recommendations=[],
            )

        monkeypatch.setattr(pu.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr("backend.process_understanding.llm_run", _fake_run)

        pu.evaluate_process_understanding_quality(
            pu.ProcessUnderstanding(title="T", objective="O", scope="S"),
            source_text="note",
        )

        assert chiamate[0]["task"] is LlmTask.PLAN_QUALITY

    def test_il_giudizio_di_qualita_non_degrada_su_un_ingresso_dimenticato(self, monkeypatch):
        """Il fallback conservativo e' per i guasti del giudice, non per L2.

        Degradare qui darebbe un giudizio prudente **sempre**, e il piano
        sembrerebbe di qualita' mediocre invece che non valutato: un guasto che
        si legge come un'opinione.
        """
        from backend.llm import OperationNotOpen
        from backend import process_understanding as pu

        def _rifiuta(**_kwargs):
            raise OperationNotOpen("nessuna operazione")

        monkeypatch.setattr(pu.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr("backend.process_understanding.llm_run", _rifiuta)

        with pytest.raises(OperationNotOpen):
            pu.evaluate_process_understanding_quality(
                pu.ProcessUnderstanding(title="T", objective="O", scope="S"),
                source_text="note",
            )

    def test_il_revisore_di_conformita_dichiara_il_compito(self, monkeypatch):
        from backend.llm import LlmTask
        from backend.agents import conformance_audit as ca

        chiamate: list[dict] = []

        def _fake_run(**kwargs):
            chiamate.append(kwargs)
            return ca.SourceAuditVerdict()

        monkeypatch.setattr("backend.settings.settings.openai_api_key", "sk-test")
        monkeypatch.setattr("backend.llm.run", _fake_run)

        revisore = ca.llm_source_auditor()
        assert revisore is not None
        revisore(
            ca.SourceAuditRequest(
                process_name="P", source_id="s1", source_name="Intervista",
                source_text="testo", plan_elements=[],
            )
        )

        assert chiamate[0]["task"] is LlmTask.CONFORMANCE_AUDIT
        assert chiamate[0]["input_characters"] > 0

    def test_l_unificatore_dichiara_il_compito(self, monkeypatch):
        from backend.llm import LlmTask
        from backend.agents import plan_consolidation as pc

        chiamate: list[dict] = []

        def _fake_run(**kwargs):
            chiamate.append(kwargs)
            return pc.PlanUnificationVerdict()

        monkeypatch.setattr("backend.settings.settings.openai_api_key", "sk-test")
        monkeypatch.setattr("backend.llm.run", _fake_run)

        unificatore = pc.llm_plan_unifier()
        assert unificatore is not None
        unificatore(
            pc.UnificationRequest(
                process_name="P", elements=[], start_candidates=[], source_paths={},
            )
        )

        assert chiamate[0]["task"] is LlmTask.PLAN_UNIFICATION

    def test_il_percorso_caldo_non_costruisce_piu_client(self):
        """La verifica che tiene: i builder non esistono, quindi non tornano."""
        from backend import process_understanding as pu

        assert not hasattr(pu, "_understanding_llm")
        assert not hasattr(pu, "_quality_evaluator_llm")
        assert not hasattr(pu, "_timeout_bucket")


def test_il_segnaposto_del_gateway_e_uno_solo():
    """Pulizia: due segnaposti identici sono due cose che possono divergere."""
    from backend.llm import GATEWAY
    from backend.memory.knowledge_graph import entity_resolution as er
    from backend.memory.procedural import extraction

    assert er.GATEWAY is GATEWAY
    assert extraction.GATEWAY is GATEWAY


class TestLaChatCostruisceDalProfilo:
    """t.6 — `agent.py` non decide piu' i parametri del modello.

    La chat e' l'unico compito che il gateway costruisce ma non esegue: il
    modello lo fa girare LangGraph e il risultato esce a pezzi. Restava pero'
    che i suoi parametri fossero scritti a mano in `agent.py` - le stesse
    decisioni del registro dei compiti, in un secondo posto.
    """

    def test_il_turno_prende_ragionamento_e_retry_dal_profilo(self, monkeypatch):
        from backend.llm import LlmTask, chat_client, profile_for
        from backend.settings import settings

        monkeypatch.setattr(settings, "openai_api_key", "sk-test")

        client = chat_client(
            LlmTask.CHAT_TURN, model_name="gpt-x", streaming=True, tag="agent-runtime"
        )

        assert client.reasoning_effort == profile_for(LlmTask.CHAT_TURN).reasoning_effort
        # `retry=True` nel profilo: dietro la chat non c'e' nessuna coda.
        assert client.max_retries == settings.agent_max_retries
        # Senza `stream_usage` i pezzi arrivano senza token e il turno
        # risulterebbe da zero: la stessa trappola delle chiamate strutturate.
        assert client.stream_usage is True

    def test_l_instradamento_prende_il_suo_tetto_sull_uscita(self, monkeypatch):
        from backend.llm import LlmTask, chat_client, profile_for
        from backend.settings import settings

        monkeypatch.setattr(settings, "openai_api_key", "sk-test")

        client = chat_client(
            LlmTask.CONTEXT_ROUTING, model_name="gpt-x", streaming=False, tag="context-router"
        )

        assert client.max_tokens == profile_for(LlmTask.CONTEXT_ROUTING).max_output_tokens == 512

    def test_senza_chiave_il_client_della_chat_non_si_costruisce(self, monkeypatch):
        from backend.llm import LlmTask, chat_client
        from backend.llm_config import MissingProviderKey
        from backend.settings import settings

        monkeypatch.setattr(settings, "openai_api_key", "")

        with pytest.raises(MissingProviderKey):
            chat_client(LlmTask.CHAT_TURN, model_name="gpt-x", streaming=True, tag="t")


class TestIlTurnoDiChatSiDivideInDueCompiti:
    """La spesa di un turno non e' una voce sola.

    Dentro un turno gira anche l'instradamento, che ha un profilo diverso
    (512 token, nessun ragionamento). Sommarli darebbe un totale giusto e due
    medie sbagliate, e la prima decisione che si prende col registro in mano e'
    proprio quanto far ragionare ciascun compito.
    """

    def test_il_nodo_dell_instradamento_ha_il_compito_suo(self):
        from backend.agent import CONTEXT_ROUTER_NODE
        from backend.llm import LlmTask
        from backend.services.agent_runtime import task_for_node

        assert task_for_node(CONTEXT_ROUTER_NODE) is LlmTask.CONTEXT_ROUTING

    def test_ogni_altro_nodo_e_il_turno(self):
        from backend.llm import LlmTask
        from backend.services.agent_runtime import task_for_node

        for nodo in ("consulting_subgraph", "summarize", "", "process_subgraph"):
            assert task_for_node(nodo) is LlmTask.CHAT_TURN

    def test_il_nodo_esiste_davvero_nel_grafo(self, monkeypatch):
        """Se il nodo si rinomina, la spesa dell'instradamento ricade nel turno.

        Non si verifica leggendo il codice ma costruendo il grafo vero e
        guardandoci dentro: e' l'unica prova che il nome su cui si appoggia il
        registro sia un nodo che esiste.
        """
        from backend.agent import CONTEXT_ROUTER_NODE, build_agent
        from backend.settings import settings

        monkeypatch.setattr(settings, "openai_api_key", "sk-test")

        grafo = build_agent("gpt-5.6-luna")

        assert CONTEXT_ROUTER_NODE in set(grafo.get_graph().nodes)


def test_a_model_call_without_an_entry_point_is_refused_not_silently_unattributed():
    """La garanzia dietro tutto: meglio un errore che una spesa senza nome."""
    from backend.llm import LlmTask, OperationNotOpen, run

    with pytest.raises(OperationNotOpen):
        run(task=LlmTask.PLAN_EXTRACTION, messages=[])
