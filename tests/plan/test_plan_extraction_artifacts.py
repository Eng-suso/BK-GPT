"""Una fonte gia' letta non si rilegge: il piano parziale e' un artefatto.

L'estrazione e' la chiamata piu' cara del prodotto - una per intervista, a testo
intero - e il suo risultato viveva dentro il merge e moriva li'. Ricostruire il
piano di un processo con quattro interviste costava quattro estrazioni anche
quando tre non erano cambiate, e nel lavoro vero le fonti si aggiungono una per
volta: e' il caso normale, non quello raro.

Qui si verifica il rimedio (P2, §4.2 del piano) e i tre modi in cui poteva
diventare peggio del problema:

1. riusare l'artefatto di un **altro cliente** (L8);
2. riusare il piano parziale che una riparazione stava correggendo;
3. far fallire una sintesi perche' il risparmio non era disponibile.

Niente modello: l'estrattore e' sostituito, perche' qui si verifica la contabilita
del lavoro evitato e non la bravura dell'LLM.
"""

from __future__ import annotations

import uuid

import pytest

from backend.agents.process_synthesis import (
    extract_plan_from_sources,
    extraction_artifact_key,
)
from backend.llm import LlmTask, OperationKind, operation
from backend.process_understanding import (
    ExtractionFailure,
    ProcessActor,
    ProcessStep,
    ProcessUnderstanding,
    ProcessUnderstandingResult,
)
from backend.settings import settings

if not settings.workspace_database_url:
    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)


def _source(name: str, content: str) -> dict:
    return {
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "type": "Intervista",
        "participants": [],
        "summary": "",
        "content": content,
        "has_content": True,
    }


LAURA = _source("Intervista Laura", "Laura Conti apre la richiesta di acquisto.")
PAOLO = _source("Intervista Paolo", "Paolo Marchetti chiama il fornitore.")
FRANCESCA = _source("Intervista Francesca", "Francesca Neri crea l'ordine.")


def _plan(actor: str, step: str) -> ProcessUnderstandingResult:
    return ProcessUnderstandingResult(
        status="success",
        process=ProcessUnderstanding(
            title="Ciclo passivo",
            actors=[ProcessActor(id=actor, label=actor.title(), kind="team")],
            steps=[ProcessStep(id=step, label=step.replace("_", " "), actor_ids=[actor])],
        ),
    )


@pytest.fixture()
def tenant():
    """Un tenant per test.

    Gli artefatti sopravvivono al test che li ha scritti - e' il loro mestiere -
    e due test che leggono la stessa intervista si riuserebbero il risultato a
    vicenda, verdi per la ragione sbagliata.
    """
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    name = f"t-{uuid.uuid4().hex[:8]}"
    token = set_current_tenant_id(name)
    try:
        yield name
    finally:
        reset_current_tenant_id(token)


@pytest.fixture()
def extractor(monkeypatch):
    """L'estrattore sostituito, che tiene il conto di quante volte ha letto."""
    seen: list[str] = []

    def _fake(title: str, source_text: str, *, with_quality_report: bool = True):
        seen.append(source_text)
        if "laura" in source_text.casefold():
            return _plan("ufficio_tecnico", "apri_richiesta")
        if "paolo" in source_text.casefold():
            return _plan("manutenzione", "chiama_fornitore")
        return _plan("acquisti", "crea_ordine")

    monkeypatch.setattr(
        "backend.agents.process_synthesis.build_process_understanding", _fake
    )
    return seen


@pytest.fixture()
def ledger(monkeypatch):
    """Cattura gli eventi di consumo invece di scriverli sul database."""
    written: list[dict] = []
    monkeypatch.setattr("backend.llm.gateway.record", lambda **kwargs: written.append(kwargs))
    return written


# --- il riuso --------------------------------------------------------------


def test_the_same_interview_is_not_read_twice(tenant, extractor):
    with operation(OperationKind.PLAN_SYNTHESIS):
        prima = extract_plan_from_sources("Ciclo passivo", [LAURA], reuse_artifacts=True)
        dopo = extract_plan_from_sources("Ciclo passivo", [LAURA], reuse_artifacts=True)

    assert prima.llm_calls == 1
    assert prima.reused == 0
    assert dopo.llm_calls == 0, "la seconda lettura non si paga"
    assert dopo.reused == 1
    assert len(extractor) == 1, "il modello ha letto l'intervista una volta sola"
    # Il piano riusato e' il piano di prima, non un piano vuoto.
    assert dopo.process is not None
    assert [actor.id for actor in dopo.process.actors] == ["ufficio_tecnico"]


def test_only_the_new_interview_is_read(tenant, extractor):
    """Il caso normale, ed e' l'intero punto di P2: la terza intervista costa
    una estrazione, non tre."""
    with operation(OperationKind.PLAN_SYNTHESIS):
        extract_plan_from_sources("Ciclo passivo", [LAURA, PAOLO], reuse_artifacts=True)
        dopo = extract_plan_from_sources(
            "Ciclo passivo", [LAURA, PAOLO, FRANCESCA], reuse_artifacts=True
        )

    assert dopo.sources_read == 3
    assert dopo.reused == 2
    assert dopo.llm_calls == 1
    assert len(extractor) == 3
    # E il piano che ne esce e' quello di tutte e tre le voci, non della sola
    # letta adesso: un artefatto riusato deve entrare nel merge come gli altri.
    assert dopo.process is not None
    assert sorted(actor.id for actor in dopo.process.actors) == [
        "acquisti",
        "manutenzione",
        "ufficio_tecnico",
    ]


def test_a_reused_interview_leaves_a_cache_hit_in_the_ledger(tenant, extractor, ledger):
    """Un risparmio che non si misura non si difende: senza questa riga il
    lavoro evitato e' indistinguibile dall'inattivita'."""
    with operation(OperationKind.PLAN_SYNTHESIS):
        extract_plan_from_sources("Ciclo passivo", [LAURA], reuse_artifacts=True)
        ledger.clear()
        extract_plan_from_sources("Ciclo passivo", [LAURA], reuse_artifacts=True)

    evitate = [row for row in ledger if row.get("outcome") == "cache_hit"]
    assert len(evitate) == 1
    assert evitate[0]["task"] == LlmTask.PLAN_EXTRACTION.value
    assert evitate[0]["prompt_version"].startswith("plan_extraction@")


def test_the_reviewer_notes_make_it_a_different_extraction(tenant, extractor):
    """Una riparazione guidata dal revisore rilegge la fonte con i rilievi
    dentro: riusare il piano parziale che sta correggendo lo lascerebbe
    identico, e il loop di conformita' girerebbe a vuoto."""
    with operation(OperationKind.PLAN_SYNTHESIS):
        extract_plan_from_sources("Ciclo passivo", [LAURA], reuse_artifacts=True)
        riparato = extract_plan_from_sources(
            "Ciclo passivo",
            [LAURA],
            reviewer_notes={LAURA["id"]: ["la richiesta passa dal capo reparto"]},
            reuse_artifacts=True,
        )

    assert riparato.reused == 0
    assert riparato.llm_calls == 1
    assert len(extractor) == 2
    assert "capo reparto" in extractor[1]


def test_another_tenant_never_reuses_the_artifact(extractor):
    """L8: due clienti con lo stesso documento non condividono un risultato."""
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    primo = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    try:
        with operation(OperationKind.PLAN_SYNTHESIS):
            extract_plan_from_sources("Ciclo passivo", [LAURA], reuse_artifacts=True)
    finally:
        reset_current_tenant_id(primo)

    secondo = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    try:
        with operation(OperationKind.PLAN_SYNTHESIS):
            altro_cliente = extract_plan_from_sources("Ciclo passivo", [LAURA], reuse_artifacts=True)
    finally:
        reset_current_tenant_id(secondo)

    assert altro_cliente.reused == 0
    assert len(extractor) == 2


# --- cosa non si mette da parte -------------------------------------------


def test_a_failed_extraction_is_not_remembered(tenant, monkeypatch):
    """Un guasto non e' un risultato: metterlo da parte trasformerebbe un
    timeout in un'intervista persa per sempre."""
    esiti = iter(
        [
            ProcessUnderstandingResult(
                status="failed",
                failure=ExtractionFailure(
                    kind="timeout", message="scaduto", retryable=False, attempt=1
                ),
            ),
            _plan("ufficio_tecnico", "apri_richiesta"),
        ]
    )
    monkeypatch.setattr(
        "backend.agents.process_synthesis.build_process_understanding",
        lambda *args, **kwargs: next(esiti),
    )

    with operation(OperationKind.PLAN_SYNTHESIS):
        fallita = extract_plan_from_sources("Ciclo passivo", [LAURA], reuse_artifacts=True)
        ritentata = extract_plan_from_sources("Ciclo passivo", [LAURA], reuse_artifacts=True)

    assert fallita.failures
    assert ritentata.reused == 0
    assert ritentata.process is not None


def test_an_unreachable_artifact_store_does_not_break_the_extraction(
    tenant, extractor, monkeypatch
):
    """Una cache che non si raggiunge non e' un guasto dell'estrazione: si
    rilegge la fonte e si paga, com'era prima degli artefatti."""

    def _esplode(_keys):
        raise RuntimeError("database non raggiungibile")

    monkeypatch.setattr(
        "backend.workspace_database.plan_extractions_by_key", _esplode
    )

    with operation(OperationKind.PLAN_SYNTHESIS):
        result = extract_plan_from_sources("Ciclo passivo", [LAURA], reuse_artifacts=True)

    assert result.process is not None
    assert result.reused == 0
    assert result.llm_calls == 1


# --- la chiave -------------------------------------------------------------


def _key(notes: str = "testo", **overrides) -> str:
    argomenti = {
        "prompt_version": "plan_extraction@aaaa1111",
        "model": "gpt-x",
        "reasoning_effort": "medium",
    }
    argomenti.update(overrides)
    return extraction_artifact_key(notes, **argomenti)


def test_the_key_is_the_same_for_the_same_work(tenant):
    assert _key() == _key()


@pytest.mark.parametrize(
    "diverso",
    [
        pytest.param({"prompt_version": "plan_extraction@bbbb2222"}, id="prompt"),
        pytest.param({"model": "gpt-y"}, id="modello"),
        pytest.param({"reasoning_effort": "none"}, id="ragionamento"),
    ],
)
def test_the_key_moves_with_what_changes_the_result(tenant, diverso):
    """Prompt, modello e ragionamento cambiano il risultato a parita' di testo.
    Cambiarne uno non invalida niente: produce chiavi nuove, e gli artefatti di
    prima restano dove sono."""
    assert _key(**diverso) != _key()


def test_the_key_moves_with_the_text(tenant):
    assert _key("un altro testo") != _key("testo")
