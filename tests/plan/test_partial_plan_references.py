"""P0.6: un riferimento rotto si ferma sul piano parziale, prima del merge.

Un'attivita' assegnata a un attore che il piano non definisce, un collegamento
verso un nodo che non c'e'. Dopo il merge il difetto e' di tutti e di nessuno:
non dice piu' da quale intervista arriva, e il consulente lo trova nella
diagnostica del piano intero senza sapere cosa rileggere. Sul piano parziale si
sa, e si chiede alla stessa fonte di correggersi.

Quattro proprieta':

1. un piano parziale pulito non costa niente in piu';
2. la correzione si chiede sul punto, con i riferimenti rotti per nome;
3. la correzione si **verifica** con lo stesso controllo, e si tiene solo se
   corregge; cio' che resta rotto si dichiara;
4. la correzione pagata finisce nell'artefatto: la prossima volta non si ripaga.

Niente modello: l'estrattore e' sostituito.
"""

from __future__ import annotations

import uuid

import pytest

from backend.agents.process_synthesis import extract_plan_from_sources
from backend.llm import OperationKind, OperationNotOpen, operation
from backend.process_understanding import (
    ProcessActor,
    ProcessStep,
    ProcessUnderstanding,
    ProcessUnderstandingResult,
    plan_reference_errors,
)
from backend.settings import settings

if not settings.workspace_database_url:
    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)

PAOLO = {
    "id": "src-paolo",
    "name": "Intervista Paolo",
    "type": "Intervista",
    "content": "Paolo, Manutenzione: quando la linea e' ferma chiamo il fornitore.",
}


def _plan(*, actor_defined: bool) -> ProcessUnderstandingResult:
    """Un'attivita' di Manutenzione; l'attore c'e' o no."""
    return ProcessUnderstandingResult(
        status="success",
        process=ProcessUnderstanding(
            title="Acquisti urgenti",
            actors=(
                [ProcessActor(id="manutenzione", label="Manutenzione", kind="team")]
                if actor_defined
                else []
            ),
            steps=[
                ProcessStep(
                    id="chiama_fornitore",
                    label="Chiama il fornitore",
                    actor_ids=["manutenzione"],
                )
            ],
        ),
    )


@pytest.fixture()
def extractor(monkeypatch):
    """L'estrattore sostituito: la prima lettura dimentica l'attore.

    `fixes` decide cosa fa la correzione. Ogni testo ricevuto resta in `seen`.
    """
    state: dict = {"seen": [], "fixes": True}

    def _fake(title: str, source_text: str, *, with_quality_report: bool = True):
        state["seen"].append(source_text)
        correcting = "CORREZIONE RICHIESTA" in source_text
        return _plan(actor_defined=correcting and state["fixes"])

    monkeypatch.setattr("backend.agents.process_synthesis.build_process_understanding", _fake)
    return state


@pytest.fixture()
def tenant():
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    try:
        yield
    finally:
        reset_current_tenant_id(token)


# --- il controllo ----------------------------------------------------------


def test_a_voice_that_tells_no_activity_is_not_a_broken_plan():
    """I riferimenti rotti sono l'unica cosa che si controlla sul parziale: una
    fonte che non racconta attivita' non copre quel pezzo, non e' rotta."""
    vuoto = ProcessUnderstanding(title="Acquisti urgenti")

    assert plan_reference_errors(vuoto) == []


def test_an_activity_of_an_undefined_actor_is_a_broken_reference():
    errors = plan_reference_errors(_plan(actor_defined=False).process)

    assert errors == ["Attivita collegate ad attori non definiti: manutenzione"]


# --- la correzione ---------------------------------------------------------


def test_a_clean_partial_plan_costs_nothing_more(monkeypatch):
    seen: list[str] = []

    def _clean(title, source_text, *, with_quality_report=True):
        seen.append(source_text)
        return _plan(actor_defined=True)

    monkeypatch.setattr("backend.agents.process_synthesis.build_process_understanding", _clean)

    result = extract_plan_from_sources("Acquisti urgenti", [PAOLO])

    assert len(seen) == 1
    assert result.llm_calls == 1
    assert result.reference_repairs == 0
    assert result.unresolved_references == {}


def test_a_broken_reference_is_corrected_on_that_point(extractor):
    result = extract_plan_from_sources("Acquisti urgenti", [PAOLO])

    assert len(extractor["seen"]) == 2
    correction = extractor["seen"][1]
    # La correzione nomina il punto, e rilegge la stessa fonte intera.
    assert "manutenzione" in correction
    assert PAOLO["content"] in correction
    assert result.reference_repairs == 1
    assert result.llm_calls == 2, "la correzione e' una chiamata, e si conta"
    assert result.unresolved_references == {}
    assert result.process is not None
    assert plan_reference_errors(result.process) == [], "il merge riceve il piano corretto"


def test_a_correction_that_does_not_correct_is_not_kept(extractor):
    """A parita' di riferimenti rotti il piano di prima resta: una correzione
    che non corregge ha solo cambiato il piano senza motivo. Cio' che resta
    rotto non sparisce: si dichiara, con la fonte da cui viene."""
    extractor["fixes"] = False

    result = extract_plan_from_sources("Acquisti urgenti", [PAOLO])

    assert len(extractor["seen"]) == 2, "una correzione sola: il budget e' del runtime"
    assert result.unresolved_references == {
        "Intervista Paolo": ["Attivita collegate ad attori non definiti: manutenzione"]
    }


def test_the_paid_correction_is_the_artifact(extractor, tenant):
    """Si deposita il piano corretto sotto la chiave della lettura originale: la
    prossima ricostruzione non ripaga ne' l'estrazione ne' la correzione."""
    with operation(OperationKind.PLAN_SYNTHESIS):
        extract_plan_from_sources("Acquisti urgenti", [PAOLO], reuse_artifacts=True)
        dopo = extract_plan_from_sources("Acquisti urgenti", [PAOLO], reuse_artifacts=True)

    assert len(extractor["seen"]) == 2
    assert dopo.llm_calls == 0
    assert dopo.reused == 1
    assert dopo.process is not None
    assert plan_reference_errors(dopo.process) == []


def test_a_forgotten_entry_point_is_not_a_lost_source(monkeypatch):
    """L2: senza operazione l'estrazione non diventa "fonte persa, ritentata".
    E' lo stesso difetto che teneva spento il revisore di conformita'."""

    def _gateway_like(title, source_text, *, with_quality_report=True):
        raise OperationNotOpen("estrazione fuori da un'operazione")

    monkeypatch.setattr(
        "backend.agents.process_synthesis.build_process_understanding", _gateway_like
    )

    with pytest.raises(OperationNotOpen):
        extract_plan_from_sources("Acquisti urgenti", [PAOLO])
