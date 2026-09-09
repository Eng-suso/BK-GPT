"""Il confine Process Agent -> Canvas Agent, attraversato per davvero.

Il Process Agent possiede la conoscenza del processo; il Canvas Agent possiede
la trasformazione di quella conoscenza in BPMN. Fra i due passava il solo
`bpmn_model_id`: la Process Chat sapeva chi aveva detto cosa, e il canvas
ripartiva dal titolo. Non era un bug del canvas - era un pezzo di architettura
che non c'era.

Quattro invarianti, e ognuna corrisponde a un modo in cui il confine si rompe:

1. **handoff completeness** - Laura, Paolo e Francesca arrivano dall'altra parte
   con le loro voci, il loro sostegno e la lacuna che nessuno copre;
2. **semantic reconstruction** - da quello snapshot esce un BPMN che regge la
   validazione semantica contro il piano, senza inventare passaggi;
3. **version refresh** - una risposta del consulente cambia la versione della
   conoscenza, e il canvas se ne accorge;
4. **no parallel truth** - il canvas non puo' scrivere una verita' propria:
   ne' riscrivendo il piano da prosa, ne' tenendosi una decisione in tasca, ne'
   chiudendo un disegno costruito su una versione superata.

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
from backend.agents.process_snapshot import (  # noqa: E402
    build_process_snapshot,
    snapshot_identity,
)
from backend.graphs.canvas_edit.graph import (  # noqa: E402
    canvas_completion_report,
    knowledge_drift,
    refresh_canvas_context_after_work,
)
from backend.graphs.canvas_edit.nodes import load_canvas_context  # noqa: E402
from backend.process_understanding import (  # noqa: E402
    ProcessActor,
    ProcessBoundaries,
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessExceptionPath,
    ProcessFlowEdge,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
    ProcessUnknown,
    ProcessUnknownOption,
)
from backend.security import reset_current_tenant_id, set_current_tenant_id  # noqa: E402

# Le stesse tre voci del test sulla pipeline dell'evidenza: qui non si verifica
# che vengano raccolte, ma che attraversino il confine senza perdersi.
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

OPEN_GAP = "Chi regolarizza a posteriori l'ordine urgente di Manutenzione?"


@pytest.fixture(autouse=True)
def _deterministic_quality_report(monkeypatch):
    """Qui si verifica il contratto fra agenti, non la qualita' dell'LLM."""
    monkeypatch.setattr(settings, "openai_api_key", None)


@pytest.fixture()
def empty_process():
    token = set_current_tenant_id(f"t-handoff-{uuid.uuid4().hex[:8]}")
    suffix = uuid.uuid4().hex[:6]
    try:
        client = wd.create_client(name=f"Contoso Handoff {suffix}")
        project = wd.create_project(client_id=client["id"], name=f"Acquisti indiretti {suffix}")
        process = wd.create_process(
            project_id=project["id"],
            name="Gestione acquisto materiali indiretti e servizi",
        )
        yield {
            "project_id": project["id"],
            "process_id": process["id"],
            "bpmn_model_id": process["bpmn_model_id"],
            "process": process,
        }
    finally:
        _forget_episodes(project["id"])
        reset_current_tenant_id(token)


def _forget_episodes(project_id: str) -> None:
    from sqlalchemy import text

    from backend.memory.episodic import episodic_store

    with episodic_store.episodic_connection() as session:
        session.execute(text("DELETE FROM episodes WHERE project = :p"), {"p": project_id})


def _bind_process_chat(project_id: str, process_id: str):
    from backend.agents.scope_guard import bind_active_scope
    from backend.schemas.chat import ProcessChatScope

    return bind_active_scope(
        ProcessChatScope(type="process", project_id=project_id, process_id=process_id)
    )


def _save_interviews(scope: dict) -> None:
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
                id="firma_direttore",
                label="Raccogli la firma del direttore acquisti",
                actor_ids=["acquisti"],
            ),
            ProcessStep(
                id="crea_ordine",
                label="Crea e invia ordine al fornitore",
                actor_ids=["acquisti"],
            ),
            # Il passaggio di Paolo: e' lavoro di Manutenzione, e senza un
            # passaggio suo Manutenzione non avrebbe una corsia. Un attore che
            # nel disegno non compare e' un attore che sparisce dall'AS-IS.
            ProcessStep(
                id="chiama_fornitore",
                label="Chiama direttamente il fornitore e fa consegnare",
                actor_ids=["manutenzione"],
            ),
        ],
        sequence=["apri_richiesta", "verifica_autorizzazione", "crea_ordine"],
        main_success_path=["apri_richiesta", "verifica_autorizzazione", "crea_ordine"],
        # Una decisione senza il ramo che ne esce, e senza l'arco che la aggancia
        # al passaggio che la precede, non e' una decisione modellata: e'
        # un'etichetta. Il compilatore non genera nessun gateway e la validazione
        # semantica lo dice. Questo e' il livello a cui il piano deve arrivare
        # perche' il disegno sia quello di un consulente senior, non un elenco.
        decisions=[
            ProcessDecision(
                id="soglia_firma",
                label="Importo sopra i cinquemila euro?",
                outcomes=["Si, serve la firma del direttore", "No, procede Acquisti"],
                outcome_details=[
                    ProcessDecisionOutcome(
                        id="sopra_soglia_si",
                        label="Si, serve la firma del direttore",
                        condition="Importo > 5000 EUR",
                        target_path_id="sopra_soglia",
                    ),
                    ProcessDecisionOutcome(
                        id="sotto_soglia_no",
                        label="No, procede Acquisti",
                        condition="Importo <= 5000 EUR",
                        target_ref="crea_ordine",
                        is_default=True,
                    ),
                ],
            )
        ],
        alternative_paths=[
            ProcessPath(
                id="sopra_soglia",
                label="Sopra i cinquemila euro: firma del direttore",
                trigger_or_condition="Importo sopra i cinquemila euro",
                sequence=["firma_direttore"],
                rejoins_at="crea_ordine",
            )
        ],
        flow_edges=[
            ProcessFlowEdge(
                id="verifica_to_soglia",
                source_id="verifica_autorizzazione",
                target_id="soglia_firma",
                label="Autorizzazione verificata",
            ),
            ProcessFlowEdge(
                id="linea_ferma_to_chiamata",
                source_id="linea_ferma",
                target_id="chiama_fornitore",
                label="Linea ferma",
            ),
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
                question=OPEN_GAP,
                affects="percorso urgente",
                severity="blocking",
                grounded_in=(
                    "Paolo dice che la parte amministrativa viene sistemata dopo, "
                    "ma non da chi; Francesca non nomina il percorso urgente."
                ),
                options=[
                    ProcessUnknownOption(
                        label="Lo regolarizza Acquisti a posteriori",
                        implication="L'ordine urgente rientra nel flusso di Acquisti dopo la consegna.",
                    ),
                    ProcessUnknownOption(
                        label="Lo regolarizza Manutenzione stessa",
                        implication="Il percorso urgente resta interamente in Manutenzione.",
                    ),
                ],
            )
        ],
    )


def _prepare_plan(scope: dict, understanding: ProcessUnderstanding | None = None) -> dict:
    from backend.graphs.process.subgraphs.modeling.tools import (
        prepare_process_understanding_review,
    )

    with _bind_process_chat(scope["project_id"], scope["process_id"]):
        result = prepare_process_understanding_review.invoke(
            {
                "process_id": scope["process_id"],
                "process_description": "Bozza del ciclo passivo dalle tre interviste.",
                "process_understanding": understanding or _supported_understanding(),
            }
        )
    return json.loads(result.split("\n", 1)[1])["payload"]


def _tool_payload(output: str) -> dict:
    return json.loads(output.split("\n", 1)[1])


@pytest.fixture()
def mapped_process(empty_process):
    """Tre interviste raccolte e un piano preparato su quelle: lo stato del gate."""
    _save_interviews(empty_process)
    _prepare_plan(empty_process)
    return empty_process


# --- 1. handoff completeness ---------------------------------------------


def test_the_canvas_receives_the_three_voices_not_a_title(mapped_process):
    """Cio' che il Process Agent sa arriva dall'altra parte senza fondersi."""
    context = load_canvas_context({"bpmn_model_id": mapped_process["bpmn_model_id"]})
    snapshot = context["process_snapshot"]

    names = {source["name"] for source in snapshot["sources"]}
    assert names == {interview["title"] for interview in INTERVIEWS}

    voices = {
        voice
        for source in snapshot["sources"]
        for voice in source["participants"]
    }
    assert {"Laura Conti", "Paolo Marchetti", "Francesca Neri"} <= voices

    understanding = snapshot["process_understanding"]
    assert understanding is not None
    assert {actor["label"] for actor in understanding["actors"]} == {
        "Ufficio Tecnico",
        "Ufficio Acquisti",
        "Manutenzione",
    }
    assert understanding["decisions"], "la decisione sulla soglia deve attraversare"
    assert understanding["exceptions"], "il percorso urgente deve attraversare"


def test_the_open_gap_crosses_the_boundary_with_its_alternatives(mapped_process):
    """Una lacuna che arriva senza alternative e' una lacuna che il canvas colma da solo."""
    context = load_canvas_context({"bpmn_model_id": mapped_process["bpmn_model_id"]})
    snapshot = context["process_snapshot"]

    gap = next(
        item for item in snapshot["open_questions"] if "regolarizza" in item["question"]
    )
    assert gap["severity"] == "blocking"
    assert gap["answer"] is None
    assert len(gap["options"]) == 2


def test_the_canvas_knowledge_brief_names_who_said_what(mapped_process):
    """Il tool che il canvas chiama gli restituisce le voci, non una sintesi."""
    from backend.toolsets.process_knowledge import inspect_process_knowledge

    with _bind_process_chat(mapped_process["project_id"], mapped_process["process_id"]):
        payload = _tool_payload(
            inspect_process_knowledge.invoke({"process_id": mapped_process["process_id"]})
        )["payload"]

    brief = payload["knowledge_brief"]
    for interview in INTERVIEWS:
        assert interview["title"] in brief
    assert "Laura Conti" in brief and "Paolo Marchetti" in brief and "Francesca Neri" in brief
    assert OPEN_GAP in brief
    assert payload["snapshot_label"].startswith("V")


# --- 2. semantic reconstruction -------------------------------------------


def test_the_snapshot_compiles_to_a_bpmn_the_plan_actually_supports(mapped_process):
    """Il disegno che nasce dallo snapshot regge la validazione contro il piano."""
    from backend.bpmn import BPMNSemanticModel, semantic_model_to_bpmn_xml
    from backend.workspace_services.bpmn_canvas_validation import (
        validate_canvas_against_process,
    )

    snapshot = build_process_snapshot(mapped_process["process_id"])
    semantic_model = BPMNSemanticModel.model_validate(snapshot.bpmn_semantic_model)
    xml = semantic_model_to_bpmn_xml(semantic_model)

    report = validate_canvas_against_process(
        xml=xml,
        process_understanding=ProcessUnderstanding.model_validate(
            snapshot.process_understanding
        ),
        bpmn_semantic_model=semantic_model,
    )
    assert report["issues"] == [], report["issues"]

    # Le tre cose che distinguono una mappa da consulente da un elenco disegnato:
    # ogni attore ha una corsia, la decisione e' un gateway, il percorso urgente
    # non e' un disegno parallelo che parte dal nulla.
    assert len(semantic_model.lanes) >= 3
    assert any(node.type.endswith("Gateway") for node in semantic_model.flowNodes)
    assert any(node.type == "startEvent" for node in semantic_model.flowNodes)
    assert any(node.type == "endEvent" for node in semantic_model.flowNodes)


def test_the_draft_is_drawable_while_the_gap_stays_open(mapped_process):
    """Una lacuna dichiarata non blocca la bozza: e' disegnandola che si vede."""
    snapshot = build_process_snapshot(mapped_process["process_id"])

    assert snapshot.modelable is True
    assert snapshot.blocking_questions, "la lacuna non puo' sparire per far passare il disegno"
    assert snapshot.validation_readiness["status"] == "needs_validation"


# --- 3. version refresh ----------------------------------------------------


def test_answering_a_question_produces_a_new_knowledge_version(mapped_process):
    """La risposta del consulente e' conoscenza nuova, e si vede dalla versione."""
    before = build_process_snapshot(mapped_process["process_id"])

    wd.answer_bpmn_review_question(
        bpmn_model_id=mapped_process["bpmn_model_id"],
        question=OPEN_GAP,
        answer="Lo regolarizza Acquisti a posteriori, con un ordine retroattivo.",
    )

    after = build_process_snapshot(mapped_process["process_id"])
    assert after.version > before.version
    assert after.snapshot_id != before.snapshot_id

    answered = next(item for item in after.open_questions if item.question == OPEN_GAP)
    assert answered.answer is not None
    assert not after.blocking_questions


def test_the_canvas_reads_the_new_version_not_the_one_it_started_on(mapped_process):
    """Il canvas riceve la decisione come conoscenza, non come messaggio di chat."""
    wd.answer_bpmn_review_question(
        bpmn_model_id=mapped_process["bpmn_model_id"],
        question=OPEN_GAP,
        answer="Lo regolarizza Acquisti a posteriori, con un ordine retroattivo.",
    )

    context = load_canvas_context({"bpmn_model_id": mapped_process["bpmn_model_id"]})
    snapshot = context["process_snapshot"]
    answered = next(
        item for item in snapshot["open_questions"] if item["question"] == OPEN_GAP
    )

    assert answered["answer"].startswith("Lo regolarizza Acquisti")
    assert context["process_snapshot_id"] == snapshot["snapshot_id"]


def test_reading_twice_without_changes_gives_the_same_version(mapped_process):
    """L'identita' e' calcolata sullo stato, non sul momento della lettura."""
    first = build_process_snapshot(mapped_process["process_id"])
    second = build_process_snapshot(mapped_process["process_id"])

    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_id == snapshot_identity(
        process_id=mapped_process["process_id"],
        version=first.version,
        source_set_id=first.evidence_source_set_id,
    )


def test_a_degraded_claim_projection_does_not_fake_a_new_version(
    mapped_process, monkeypatch
):
    """La proiezione dei claim e' asincrona: il suo ritardo non e' conoscenza nuova."""
    from backend.toolsets import process_memory

    healthy = build_process_snapshot(mapped_process["process_id"])

    monkeypatch.setattr(
        process_memory,
        "process_claim_ledger",
        lambda *_a, **_k: {"status": "error", "claims": [], "count": 0},
    )
    degraded = build_process_snapshot(mapped_process["process_id"])

    assert degraded.snapshot_id == healthy.snapshot_id
    # Ma lo dichiara, invece di far finta che la provenance sia completa.
    assert degraded.claim_status == "error"


# --- 4. no parallel truth --------------------------------------------------


def test_process_and_canvas_read_the_same_version_of_the_same_process(mapped_process):
    """Due agenti, una verita': gli id devono coincidere, non assomigliarsi."""
    from backend.graphs.process.nodes import load_process_context

    with _bind_process_chat(mapped_process["project_id"], mapped_process["process_id"]):
        process_side = build_process_snapshot(mapped_process["process_id"])
        process_context = load_process_context({"process_id": mapped_process["process_id"]})

    canvas_context = load_canvas_context({"bpmn_model_id": mapped_process["bpmn_model_id"]})

    assert canvas_context["process_snapshot_id"] == process_side.snapshot_id
    assert (
        canvas_context["process_snapshot"]["evidence_source_set_id"]
        == process_context["evidence_ledger"]["source_set_id"]
    )
    assert (
        canvas_context["process_snapshot"]["process_understanding"]
        == process_side.process_understanding
    )


def test_the_canvas_cannot_rewrite_the_plan_from_its_own_prose(mapped_process):
    """La strada che rendeva il disegno una seconda fonte e' chiusa."""
    from backend.toolsets.bpmn import prepare_canvas_bpmn_review

    before = build_process_snapshot(mapped_process["process_id"])

    with pytest.raises(ValueError, match="evidenze registrate"):
        prepare_canvas_bpmn_review.invoke(
            {
                "bpmn_model_id": mapped_process["bpmn_model_id"],
                "process_description": (
                    "Il processo parte da una richiesta e finisce con un ordine. "
                    "Sono coinvolti il richiedente e l'ufficio acquisti."
                ),
            }
        )

    after = build_process_snapshot(mapped_process["process_id"])
    assert after.snapshot_id == before.snapshot_id
    assert after.process_understanding == before.process_understanding


def test_a_canvas_question_lands_on_the_process_plan_not_on_the_canvas(mapped_process):
    """La domanda del modeler diventa conoscenza del processo, e alza la versione."""
    from backend.toolsets.process_knowledge import raise_modeling_question

    before = build_process_snapshot(mapped_process["process_id"])

    with _bind_process_chat(mapped_process["project_id"], mapped_process["process_id"]):
        result = _tool_payload(
            raise_modeling_question.invoke(
                {
                    "process_id": mapped_process["process_id"],
                    "question": (
                        "L'ordine urgente di Manutenzione al fornitore va disegnato "
                        "come percorso alternativo o come evento che interrompe la "
                        "richiesta di acquisto?"
                    ),
                    "affects": "percorso urgente, tipo di evento",
                    "grounded_in": (
                        "Paolo Marchetti dice che quando la linea e' ferma chiama "
                        "direttamente il fornitore senza aspettare Acquisti."
                    ),
                    "options": [
                        {
                            "label": "Percorso alternativo da inizio processo",
                            "implication": "Manutenzione ha un suo ramo parallelo.",
                        },
                        {
                            "label": "Evento che interrompe la richiesta",
                            "implication": "L'urgenza interrompe il flusso normale gia' avviato.",
                        },
                    ],
                    "severity": "blocking",
                }
            )
        )

    assert result["status"] == "waiting_for_user"

    after = build_process_snapshot(mapped_process["process_id"])
    assert after.version > before.version
    assert after.snapshot_id != before.snapshot_id
    assert any("ordine urgente" in item.question for item in after.open_questions)


def test_a_question_the_sources_never_touched_is_refused(mapped_process):
    """Il canvas non puo' introdurre un tema che le fonti non hanno mai nominato."""
    from backend.toolsets.process_knowledge import raise_modeling_question

    with _bind_process_chat(mapped_process["project_id"], mapped_process["process_id"]):
        result = _tool_payload(
            raise_modeling_question.invoke(
                {
                    "process_id": mapped_process["process_id"],
                    "question": "Quali sono le soglie di approvazione del budget annuale?",
                    "affects": "governance",
                    "grounded_in": "prassi di settore",
                    "severity": "blocking",
                }
            )
        )

    assert result["status"] == "dropped_not_grounded"
    after = build_process_snapshot(mapped_process["process_id"])
    assert not any("budget annuale" in item.question for item in after.open_questions)


def test_a_run_built_on_a_superseded_version_stops_instead_of_closing(mapped_process):
    """Un disegno corretto su conoscenza superata resta un disegno da rifare."""
    started_on = build_process_snapshot(mapped_process["process_id"]).snapshot_id

    wd.answer_bpmn_review_question(
        bpmn_model_id=mapped_process["bpmn_model_id"],
        question=OPEN_GAP,
        answer="Lo regolarizza Acquisti a posteriori.",
    )

    state = {
        "process_id": mapped_process["process_id"],
        "bpmn_model_id": mapped_process["bpmn_model_id"],
        "canvas_run_snapshot_id": started_on,
    }
    drift = knowledge_drift(state)
    assert drift is not None
    assert drift["started_on"] == started_on
    assert drift["current_snapshot_id"] != started_on

    outcome = refresh_canvas_context_after_work(state)
    assert outcome["canvas_run_status"] == "waiting_for_user"
    assert outcome["canvas_loop_status"] == "blocked"

    report = canvas_completion_report({**state, **outcome})
    assert "decisione" in report["messages"][0].content.lower()
    assert report["canvas_task_log"][0]["status"] == "waiting_for_user"


def test_a_run_on_the_current_version_is_not_interrupted(mapped_process):
    """La deriva si dichiara quando c'e': un run allineato deve poter chiudere."""
    snapshot = build_process_snapshot(mapped_process["process_id"])
    state = {
        "process_id": mapped_process["process_id"],
        "bpmn_model_id": mapped_process["bpmn_model_id"],
        "canvas_run_snapshot_id": snapshot.snapshot_id,
    }

    assert knowledge_drift(state) is None
    assert refresh_canvas_context_after_work(state).get("canvas_run_status") is None
