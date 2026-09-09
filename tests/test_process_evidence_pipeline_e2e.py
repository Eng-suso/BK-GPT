"""Stesso processo, stesse fonti, stessa verita' - in chat, in review, sul canvas.

Nella stessa Process Chat DeliR vedeva zero interviste, poi Laura/Paolo/
Francesca, poi di nuovo zero; il planner del canvas, con le stesse tre fonti sul
tavolo, dichiarava di conoscere solo perimetro e obiettivo e ripartiva a chiedere
trigger, attori e prima attivita'. Non erano difetti separati: il source set era
una conseguenza della proiezione dei claim nel knowledge graph, che e' asincrona
e puo' degradare. Quando la proiezione non c'era, "nessun claim" diventava
"nessuna intervista" - e ogni ragionamento a valle partiva da li'.

Qui si attraversa il percorso vero: si crea un processo vuoto, si salvano le tre
interviste come le salva l'agente, poi si apre una Process Chat nuova, si degrada
la proiezione, si riapre, si prepara la review del canvas. L'invariante e' una
sola: lo stesso processo con le stesse fonti deve dare lo stesso source set a
ogni fase, e una bozza deve poter nascere prima della validazione finale.

Servono la DSN workspace e quelle canonical (`cd ops && docker compose up -d`).
"""

from __future__ import annotations

import json
import uuid

import pytest

from backend.settings import settings

if not all((settings.workspace_database_url, settings.canonical_database_url)):
    pytest.skip(
        "servono WORKSPACE_DATABASE_URL e le DSN canonical",
        allow_module_level=True,
    )

from backend import workspace_database as wd  # noqa: E402
from backend.graphs.process.nodes import load_process_context  # noqa: E402
from backend.graphs.routing_contracts import (  # noqa: E402
    CAPABILITY_REGISTRY,
    missing_prerequisites,
)
from backend.process_understanding import (  # noqa: E402
    ProcessActor,
    ProcessBoundaries,
    ProcessDecision,
    ProcessExceptionPath,
    ProcessStep,
    ProcessUnderstanding,
    ProcessUnknown,
)
from backend.security import reset_current_tenant_id, set_current_tenant_id  # noqa: E402

# Tre voci sullo stesso ciclo passivo. Insieme sostengono attori, attivita',
# handoff, il percorso urgente e i controlli. Nessuna di loro sa chi regolarizza
# l'ordine urgente a posteriori: quello resta una lacuna, non un blocco.
INTERVIEWS = (
    {
        "title": "Intervista Laura Conti - Ufficio Tecnico",
        "participants": ["Laura Conti"],
        "entities": ["Laura Conti", "Ufficio Tecnico", "Richiesta di acquisto"],
        "raw_content": (
            "Laura Conti, Ufficio Tecnico. Quando il magazzino segnala che manca "
            "un materiale apro una richiesta di acquisto e la mando ad Acquisti "
            "per mail. Se non ricevo risposta entro due giorni sollecito. Non so "
            "cosa succede dopo che Acquisti ha preso in carico la richiesta."
        ),
    },
    {
        "title": "Intervista Paolo Marchetti - Manutenzione",
        "participants": ["Paolo Marchetti"],
        "entities": ["Paolo Marchetti", "Manutenzione", "Ordine urgente"],
        "raw_content": (
            "Paolo Marchetti, Manutenzione. Quando la linea e' ferma non aspetto "
            "Acquisti: chiamo direttamente il fornitore e faccio consegnare. La "
            "parte amministrativa viene sistemata dopo, ma non so da chi ne' con "
            "quale documento."
        ),
    },
    {
        "title": "Intervista Francesca Neri - Acquisti",
        "participants": ["Francesca Neri"],
        "entities": ["Francesca Neri", "Ufficio Acquisti", "Ordine di acquisto"],
        "raw_content": (
            "Francesca Neri, Ufficio Acquisti. Ricevo la richiesta dall'Ufficio "
            "Tecnico, verifico che ci sia l'autorizzazione del responsabile, poi "
            "creo l'ordine e lo invio al fornitore. Sopra i cinquemila euro serve "
            "sempre la firma del direttore acquisti."
        ),
    },
)


@pytest.fixture(autouse=True)
def _deterministic_quality_report(monkeypatch):
    """Il quality report resta deterministico: qui si verifica il dato, non l'LLM."""
    monkeypatch.setattr(settings, "openai_api_key", None)


@pytest.fixture()
def empty_process():
    """Un processo appena creato: nessuna fonte, nessuna review, nessun BPMN."""
    token = set_current_tenant_id(f"t-pipeline-{uuid.uuid4().hex[:8]}")
    suffix = uuid.uuid4().hex[:6]
    try:
        client = wd.create_client(name=f"Contoso Pipeline {suffix}")
        project = wd.create_project(client_id=client["id"], name=f"Acquisti indiretti {suffix}")
        process = wd.create_process(
            project_id=project["id"],
            name="Gestione acquisto materiali indiretti e servizi",
        )
        yield {"project_id": project["id"], "process_id": process["id"], "process": process}
    finally:
        _forget_episodes(project["id"])
        reset_current_tenant_id(token)


def _forget_episodes(project_id: str) -> None:
    from sqlalchemy import text

    from backend.memory.episodic import episodic_store

    with episodic_store.episodic_connection() as session:
        session.execute(text("DELETE FROM episodes WHERE project = :p"), {"p": project_id})


def _canvas_prerequisites(state: dict) -> list[str]:
    return missing_prerequisites(CAPABILITY_REGISTRY["process.canvas_handoff"], state)


def _bind_process_chat(project_id: str, process_id: str):
    """Il vincolo di scope che il backend mette attorno a un turno di chat."""
    from backend.agents.scope_guard import bind_active_scope
    from backend.schemas.chat import ProcessChatScope

    return bind_active_scope(
        ProcessChatScope(type="process", project_id=project_id, process_id=process_id)
    )


def _save_interviews(scope: dict) -> None:
    """Le tre interviste, salvate una alla volta come le salva l'agente."""
    from backend.toolsets.process_memory import manage_process_evidence

    with _bind_process_chat(scope["project_id"], scope["process_id"]):
        for interview in INTERVIEWS:
            manage_process_evidence.invoke(
                {
                    "operation": "save_interview",
                    "project_id": scope["project_id"],
                    "process_id": scope["process_id"],
                    "title": interview["title"],
                    "raw_content": interview["raw_content"],
                    "summary": interview["title"],
                    "participants": interview["participants"],
                    "entities": interview["entities"],
                }
            )


def _new_chat_context(scope: dict) -> dict:
    """Una Process Chat nuova: stato vuoto, nessuna memoria del turno precedente."""
    with _bind_process_chat(scope["project_id"], scope["process_id"]):
        return load_process_context({"process_id": scope["process_id"]})


def _supported_understanding() -> ProcessUnderstanding:
    """Il piano che le tre interviste sostengono, con la lacuna che resta aperta."""
    return ProcessUnderstanding(
        title="Gestione acquisto materiali indiretti e servizi",
        actors=[
            ProcessActor(id="ufficio_tecnico", label="Ufficio Tecnico", kind="team"),
            ProcessActor(id="acquisti", label="Ufficio Acquisti", kind="team"),
            ProcessActor(id="manutenzione", label="Manutenzione", kind="team"),
        ],
        steps=[
            ProcessStep(
                id="apri_richiesta",
                label="Apri richiesta di acquisto",
                actor_ids=["ufficio_tecnico"],
            ),
            ProcessStep(
                id="verifica_autorizzazione",
                label="Verifica autorizzazione del responsabile",
                actor_ids=["acquisti"],
            ),
            ProcessStep(
                id="crea_ordine",
                label="Crea e invia ordine al fornitore",
                actor_ids=["acquisti"],
            ),
        ],
        sequence=["apri_richiesta", "verifica_autorizzazione", "crea_ordine"],
        main_success_path=["apri_richiesta", "verifica_autorizzazione", "crea_ordine"],
        decisions=[
            ProcessDecision(
                id="soglia_firma",
                label="Importo sopra i cinquemila euro?",
                outcomes=["Si, serve la firma del direttore", "No, procede Acquisti"],
            )
        ],
        exceptions=[
            ProcessExceptionPath(
                id="linea_ferma",
                label="Linea ferma: Manutenzione chiama il fornitore",
                trigger="La linea di produzione e' ferma",
                handling="Manutenzione contatta direttamente il fornitore",
                attached_to_step_id="apri_richiesta",
            )
        ],
        boundaries=ProcessBoundaries(
            trigger="Il magazzino segnala un materiale mancante",
            start_event="Richiesta di acquisto aperta",
            success_end="Ordine inviato al fornitore",
        ),
        unknowns=[
            ProcessUnknown(
                question="Chi regolarizza a posteriori l'ordine urgente di Manutenzione?",
                affects="percorso urgente",
                severity="blocking",
                grounded_in=(
                    "Paolo dice che la parte amministrativa viene sistemata dopo, "
                    "ma non da chi; Francesca non nomina il percorso urgente."
                ),
            )
        ],
    )


def _prepared_review(scope: dict, understanding: ProcessUnderstanding | None) -> dict:
    from backend.graphs.process.subgraphs.modeling.tools import (
        prepare_process_understanding_review,
    )

    with _bind_process_chat(scope["project_id"], scope["process_id"]):
        result = prepare_process_understanding_review.invoke(
            {
                "process_id": scope["process_id"],
                "process_description": (
                    "Bozza preliminare del ciclo passivo dalle tre interviste."
                ),
                "process_understanding": understanding,
            }
        )
    return json.loads(result.split("\n", 1)[1])["payload"]


@pytest.fixture()
def process_with_three_interviews(empty_process):
    """Processo vuoto, poi Laura, poi Paolo, poi Francesca."""
    _save_interviews(empty_process)
    return empty_process


# --- P0: lo stesso source set a ogni richiesta ----------------------------


def test_three_consecutive_reads_see_the_same_three_sources(process_with_three_interviews):
    """Tre richieste di fila nella stessa chat non possono vedere set diversi."""
    snapshots = [
        _new_chat_context(process_with_three_interviews)["evidence_ledger"] for _ in range(3)
    ]

    assert [snapshot["source_count"] for snapshot in snapshots] == [3, 3, 3]
    assert len({snapshot["source_set_id"] for snapshot in snapshots}) == 1
    assert len({tuple(snapshot["source_ids"]) for snapshot in snapshots}) == 1
    names = {source["name"] for source in snapshots[0]["sources"]}
    assert names == {interview["title"] for interview in INTERVIEWS}


def test_the_source_set_survives_a_degraded_claim_projection(
    process_with_three_interviews, monkeypatch
):
    """Il knowledge graph e' una proiezione: se cade, le interviste restano."""
    from backend.toolsets import process_memory

    healthy = _new_chat_context(process_with_three_interviews)["evidence_ledger"]

    def _broken(*_args, **_kwargs):
        raise RuntimeError("claim projection non raggiungibile")

    monkeypatch.setattr(process_memory, "process_claim_ledger", _broken)
    degraded = _new_chat_context(process_with_three_interviews)["evidence_ledger"]

    assert degraded["source_count"] == 3
    assert degraded["source_set_id"] == healthy["source_set_id"]
    # Lo stato dice cosa e' successo davvero: la proiezione e' rotta, le fonti no.
    assert degraded["claim_status"] == "error"
    assert degraded["status"] == "ok"


def test_a_new_chat_after_a_restart_reads_the_same_set(process_with_three_interviews):
    """Nessun pezzo del set vive nella memoria di processo o nel checkpoint."""
    from backend.local_store import local_engine

    before = _new_chat_context(process_with_three_interviews)["evidence_ledger"]

    local_engine.cache_clear()
    local_engine().dispose()

    after = _new_chat_context(process_with_three_interviews)["evidence_ledger"]

    assert after["source_set_id"] == before["source_set_id"]
    assert after["source_ids"] == before["source_ids"]


def test_every_source_reaches_the_prompt_with_its_own_text(process_with_three_interviews):
    """Il testo arriva a chi risponde, attribuito, senza fondere le voci."""
    from backend.agents.evidence_brief import render_source_evidence

    snapshot = _new_chat_context(process_with_three_interviews)["evidence_ledger"]
    rendered = render_source_evidence(snapshot)

    for interview in INTERVIEWS:
        assert interview["title"] in rendered
        assert interview["raw_content"][:60] in rendered
    for source in snapshot["sources"]:
        assert f"[FONTE {source['id']}]" in rendered
        assert f"[/FONTE {source['id']}]" in rendered


# --- P0: le stesse fonti arrivano al planner del canvas -------------------


def test_the_canvas_planner_receives_the_same_evidence_set(process_with_three_interviews):
    """La review nasce dalle tre interviste, non dal solo perimetro."""
    expected = _new_chat_context(process_with_three_interviews)["evidence_ledger"]

    payload = _prepared_review(process_with_three_interviews, _supported_understanding())

    assert payload["evidence_source_set_id"] == expected["source_set_id"]
    assert payload["evidence_source_ids"] == expected["source_ids"]

    review = wd.get_bpmn_review(
        process_with_three_interviews["process"]["bpmn_model_id"], include_approved=True
    )
    for interview in INTERVIEWS:
        assert interview["title"] in review["source_text"]
        assert interview["raw_content"][:60] in review["source_text"]


def test_an_empty_plan_is_refused_while_the_interviews_are_on_record(
    process_with_three_interviews,
):
    """PROCESS-V2-11: un piano senza attori non diventa lo stato del processo."""
    with pytest.raises(ValueError, match="3 evidenze registrate"):
        _prepared_review(
            process_with_three_interviews,
            ProcessUnderstanding(title="Gestione acquisto materiali indiretti e servizi"),
        )


def test_an_empty_plan_is_refused_even_before_the_claims_are_projected(
    process_with_three_interviews, monkeypatch
):
    """Il gate difende le fonti, non la proiezione: la finestra asincrona non lo apre."""
    from backend.toolsets import process_memory

    monkeypatch.setattr(
        process_memory,
        "process_claim_ledger",
        lambda *_args, **_kwargs: {"status": "empty", "claims": [], "count": 0},
    )

    with pytest.raises(ValueError, match="3 evidenze registrate"):
        _prepared_review(
            process_with_three_interviews,
            ProcessUnderstanding(title="Gestione acquisto materiali indiretti e servizi"),
        )


# --- P1: bozza modellabile prima della validazione ------------------------


def test_the_draft_is_modelable_while_the_open_gap_stays_open(process_with_three_interviews):
    """Un dato parziale ma sufficiente e' una bozza, non un blocco."""
    payload = _prepared_review(process_with_three_interviews, _supported_understanding())

    assert payload["draft_readiness"]["status"] == "modelable"
    assert payload["draft_readiness"]["blockers"] == []
    assert payload["draft_readiness"]["gaps"], "la lacuna non puo' sparire"
    assert payload["validation_readiness"]["status"] == "needs_validation"


def test_the_same_readiness_comes_back_after_a_new_chat(process_with_three_interviews):
    """La soglia non vive nello stato del turno: si ricava dal piano salvato."""
    prepared = _prepared_review(process_with_three_interviews, _supported_understanding())

    context = _new_chat_context(process_with_three_interviews)

    assert context["draft_readiness"] == prepared["draft_readiness"]
    assert context["validation_readiness"] == prepared["validation_readiness"]


def test_a_preliminary_canvas_is_not_blocked_by_the_open_gap(process_with_three_interviews):
    """Draft-readiness e validation-readiness sono due soglie, e il canvas usa la prima."""
    _prepared_review(process_with_three_interviews, _supported_understanding())

    context = _new_chat_context(process_with_three_interviews)
    state = {
        **context,
        "workflow_scope": "full_workflow",
        "process_route": "delegate_canvas",
        "contradictions": [],
        "process_gaps": [],
    }

    assert "readiness_for_canvas" not in _canvas_prerequisites(state)
    # E il modello resta dichiaratamente non validato finche' la lacuna e' aperta.
    assert context["validation_readiness"]["status"] == "needs_validation"


# --- P1: non si richiede cio' che le fonti hanno gia' detto ---------------


def test_the_plan_does_not_ask_again_for_what_the_sources_already_said(
    process_with_three_interviews,
):
    """Trigger, attori, prima attivita' e fine processo non tornano come domande."""
    understanding = _supported_understanding()
    understanding.unknowns = [
        ProcessUnknown(
            question="Qual e' il trigger del processo?",
            affects="avvio",
            severity="blocking",
        ),
        ProcessUnknown(
            question="Quali sono gli attori del processo?",
            affects="attori",
            severity="blocking",
        ),
        *understanding.unknowns,
    ]

    payload = _prepared_review(process_with_three_interviews, understanding)
    questions = [item["question"] for item in payload["process_understanding"]["unknowns"]]

    assert "Qual e' il trigger del processo?" not in questions
    assert "Quali sono gli attori del processo?" not in questions
    # La lacuna vera resta, ed e' quella che nessuna fonte copre.
    assert any("regolarizza" in question for question in questions)
    assert any("contiene gia'" in item for item in payload["missing_information"])
