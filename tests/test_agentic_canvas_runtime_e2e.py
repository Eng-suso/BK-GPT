"""Il runtime agentico del Canvas, dallo stato in cui il difetto viveva davvero.

Il test sul confine Process -> Canvas che esisteva gia' partiva da un processo
con il piano gia' preparato. E' lo stato giusto per verificare che la conoscenza
attraversi, ed e' lo stato sbagliato per accorgersi del difetto: nell'uso reale
il consulente salva tre interviste e chiede "genera il BPMN" senza che nessuno
abbia preparato un piano. Quello stato, misurato, era questo:

    fonti: 3   claim: 0   modello semantico: assente   modelable: no
    prerequisiti mancanti per process.canvas_handoff:
        ['bpmn_semantic_model', 'readiness_for_canvas']

Il gate rifiutava, il turno finiva in chiarimento, e al consulente arrivavano le
domande da questionario su trigger, attori e prima attivita' - dopo tre
interviste che quei punti li avevano descritti. "Nessuna intervista disponibile",
"nessun attore", il modello start -> end e le domande generiche non erano quattro
difetti: erano un difetto solo, e non era nel Canvas.

Qui si verificano le invarianti che quel difetto violava:

1. **handoff** - il Canvas riceve le tre voci con le loro parole, non tre nomi;
2. **ricostruzione vincolata all'evidenza** - il piano nasce dal corpus delle
   fonti, e cio' che le fonti non dicono non entra;
3. **bozza != validato** - un processo con lacune resta disegnabile;
4. **clarification ancorate** - la domanda porta con se' la lacuna che la genera;
5. **nessun successo non verificato** - un write che non si rilegge non e' un write.

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
from backend.agents import process_synthesis  # noqa: E402
from backend.agents.process_snapshot import (  # noqa: E402
    build_process_snapshot,
    draft_readiness_without_plan,
    render_snapshot_for_modeling,
)
from backend.agents.process_synthesis import ensure_process_plan  # noqa: E402
from backend.graphs.canvas_edit.graph import (  # noqa: E402
    canvas_completion_report,
    evaluate_canvas_completion,
    refresh_canvas_context_after_work,
)
from backend.graphs.canvas_edit.nodes import load_canvas_context  # noqa: E402
from backend.graphs.process.nodes import load_process_context  # noqa: E402
from backend.graphs.routing_contracts import (  # noqa: E402
    CAPABILITY_REGISTRY,
    missing_prerequisites,
)
from backend.process_understanding import (  # noqa: E402
    ProcessUnderstanding,
    ProcessUnderstandingResult,
)
from backend.workspace_services.bpmn_canvas_validation import (  # noqa: E402
    validate_canvas_against_process,
)
from backend.workspace_services.write_verification import (  # noqa: E402
    PersistenceVerificationError,
    verify_bpmn_model_persisted,
    verify_review_persisted,
)

# Le stesse tre voci degli altri test sull'evidenza: qui si verifica che
# arrivino fino al disegno.
from tests.test_process_canvas_handoff_e2e import (  # noqa: E402
    INTERVIEWS,
    OPEN_GAP,
    _save_interviews,
    _supported_understanding,
    empty_process,  # noqa: F401 - fixture
)

# Un canvas che non e' un modello del processo: e' il disegno che il runtime
# produceva e dichiarava "aggiornato e verificato senza problemi bloccanti".
START_END_ONLY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  id="Definitions_empty" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_empty" isExecutable="false">
    <bpmn:startEvent id="StartEvent_1" name="Inizio" >
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:endEvent id="EndEvent_1" name="Fine">
      <bpmn:incoming>Flow_1</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_empty">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="160" y="100" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1">
        <dc:Bounds x="320" y="100" width="36" height="36" />
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
"""


@pytest.fixture(autouse=True)
def _no_live_model(monkeypatch):
    """Qui si verifica il contratto fra agenti, non la qualita' dell'LLM."""
    monkeypatch.setattr(settings, "openai_api_key", None)


@pytest.fixture()
def recorded_extractions(monkeypatch) -> list[str]:
    """Sostituisce l'estrattore, e tiene il corpus che gli e' arrivato.

    Il corpus e' cio' che conta: se le parole di Laura, Paolo e Francesca non
    arrivano fin qui, nessun modello - vero o finto - puo' produrre un AS-IS che
    le rispetti, e il difetto sta a monte dell'LLM.
    """
    corpora: list[str] = []

    def _fake_extraction(title: str, source_text: str) -> ProcessUnderstandingResult:
        corpora.append(source_text)
        return ProcessUnderstandingResult(status="success", process=_supported_understanding())

    monkeypatch.setattr(process_synthesis, "build_process_understanding", _fake_extraction)
    return corpora


@pytest.fixture()
def interviewed_process(empty_process):
    """Tre interviste agli atti e nessun piano: lo stato reale del difetto."""
    _save_interviews(empty_process)
    return empty_process


def _tool_payload(output: str) -> dict:
    return json.loads(output.split("\n", 1)[1])


def _process_state(scope: dict) -> dict:
    return {
        **load_process_context({"process_id": scope["process_id"]}),
        "process_id": scope["process_id"],
        "project_id": scope["project_id"],
        "workflow_scope": "full_workflow",
    }


# --- TEST 1 — knowledge handoff -------------------------------------------


def test_the_canvas_receives_the_words_of_the_three_voices_not_three_names(
    interviewed_process, recorded_extractions
):
    """Lo snapshot portava il nome dell'intervista e non il suo testo.

    Con la proiezione dei claim indietro - che e' asincrona, e nella prova reale
    valeva zero claim su tre interviste - dall'altra parte del confine arrivavano
    tre nomi e nessuna sostanza. Chi modella non aveva materiale da cui modellare.
    """
    ensure_process_plan(interviewed_process["process_id"])
    snapshot = build_process_snapshot(interviewed_process["process_id"])

    assert len(snapshot.sources) == len(INTERVIEWS)
    brief = render_snapshot_for_modeling(snapshot)
    for interview in INTERVIEWS:
        voice = interview["participants"][0]
        assert voice in brief, f"la voce di {voice} non attraversa il confine"
    # Non i nomi delle interviste: le loro parole.
    assert "chiamo direttamente il fornitore" in brief.casefold()
    assert "sopra i cinquemila euro" in brief.casefold()


def test_the_same_evidence_set_is_on_both_sides_of_the_boundary(
    interviewed_process, recorded_extractions
):
    ensure_process_plan(interviewed_process["process_id"])

    process_side = load_process_context({"process_id": interviewed_process["process_id"]})
    canvas_side = load_canvas_context(
        {"bpmn_model_id": interviewed_process["bpmn_model_id"]}
    )

    assert (
        process_side["evidence_ledger"]["source_set_id"]
        == canvas_side["process_snapshot"]["evidence_source_set_id"]
    )
    assert canvas_side["process_understanding"] is not None


def test_the_evidence_corpus_reaches_the_extractor_with_the_voices_separated(
    interviewed_process, recorded_extractions
):
    """Il piano nasce dalle fonti, e le fonti restano voci distinte.

    Fondere i transcript in un blocco unico e' il modo piu' diretto per far
    diventare "regola generale" cio' che una sola persona ha descritto del
    proprio reparto.
    """
    ensure_process_plan(interviewed_process["process_id"])

    assert len(recorded_extractions) == 1
    corpus = recorded_extractions[0]
    for interview in INTERVIEWS:
        assert interview["participants"][0] in corpus
        assert interview["raw_content"][:40] in corpus
    assert corpus.count("[FONTE ") >= len(INTERVIEWS)


# --- TEST 2 — ricostruzione semantica vincolata all'evidenza ---------------


def test_three_interviews_and_no_plan_still_reach_the_canvas_as_a_plan(
    interviewed_process, recorded_extractions
):
    """L'invariante che non c'era: se il processo ha evidenza, il processo ha un piano.

    Prima la `ProcessUnderstanding` esisteva solo se un passo dell'agente la
    scriveva - il router doveva scegliere `modeling`, il subagente doveva
    chiamare il tool giusto e riempirne bene l'argomento. Tre condizioni affidate
    a un prompt per un'invariante che invece e' dura.
    """
    before = build_process_snapshot(interviewed_process["process_id"])
    assert not before.has_semantic_model
    assert before.evidence_count == len(INTERVIEWS)

    outcome = ensure_process_plan(interviewed_process["process_id"])

    assert outcome.action == "synthesized"
    assert outcome.has_plan
    assert outcome.snapshot.version > before.version


def test_the_plan_declares_the_sources_it_was_built_on(
    interviewed_process, recorded_extractions
):
    """"Il piano e' aggiornato rispetto alle interviste?" diventa una domanda con risposta."""
    outcome = ensure_process_plan(interviewed_process["process_id"])
    snapshot = outcome.snapshot

    assert snapshot.plan_evidence_source_set_id == snapshot.evidence_source_set_id
    assert snapshot.plan_is_current


def test_a_plan_already_built_on_the_current_sources_is_not_rebuilt(
    interviewed_process, recorded_extractions
):
    """Rifare il piano a ogni giro cancellerebbe le risposte gia' date dal consulente."""
    ensure_process_plan(interviewed_process["process_id"])
    first = build_process_snapshot(interviewed_process["process_id"])

    again = ensure_process_plan(interviewed_process["process_id"])

    assert again.action == "reused"
    assert len(recorded_extractions) == 1
    assert again.snapshot.snapshot_id == first.snapshot_id


def test_a_new_source_makes_the_plan_stale_and_it_is_rebuilt(
    interviewed_process, recorded_extractions
):
    """Una quarta intervista non deve lasciare in piedi un piano di tre fonti fa."""
    ensure_process_plan(interviewed_process["process_id"])
    from backend.toolsets.process_memory import manage_process_evidence

    from tests.test_process_canvas_handoff_e2e import _bind_process_chat

    with _bind_process_chat(
        interviewed_process["project_id"], interviewed_process["process_id"]
    ):
        manage_process_evidence.invoke(
            {
                "operation": "save_interview",
                "project_id": interviewed_process["project_id"],
                "process_id": interviewed_process["process_id"],
                "title": "Intervista Marco Bianchi - Amministrazione",
                "raw_content": (
                    "Marco Bianchi, Amministrazione. Ricevo la fattura dal fornitore e "
                    "verifico che corrisponda all'ordine prima di pagarla."
                ),
                "summary": "Intervista Marco Bianchi - Amministrazione",
                "participants": ["Marco Bianchi"],
                "entities": ["Marco Bianchi", "Amministrazione", "Fattura"],
            }
        )

    stale = build_process_snapshot(interviewed_process["process_id"])
    assert not stale.plan_is_current

    outcome = ensure_process_plan(interviewed_process["process_id"])
    assert outcome.action == "synthesized"
    assert len(recorded_extractions) == 2
    assert "Marco Bianchi" in recorded_extractions[1]


def test_a_process_without_evidence_is_not_a_process_to_draw(empty_process):
    """Senza fonti non si sintetizza niente, e non si finge un disegno."""
    outcome = ensure_process_plan(empty_process["process_id"])

    assert outcome.action == "no_evidence"
    assert not outcome.has_plan
    assert outcome.blockers


# --- TEST 3 — soglia bozza contro soglia validazione ----------------------


def test_evidence_without_a_plan_opens_the_draft_gate_not_the_validation_one(
    interviewed_process,
):
    """"Non validato" e "non modellabile" erano la stessa soglia, e vinceva la seconda."""
    state = _process_state(interviewed_process)

    assert state["draft_readiness"]["status"] == "synthesizable"
    assert state["validation_readiness"]["status"] == "needs_validation"

    spec = CAPABILITY_REGISTRY["process.canvas_handoff"]
    assert missing_prerequisites(spec, state) == []


def test_a_process_with_nothing_recorded_keeps_the_canvas_gate_closed(empty_process):
    """La soglia si apre sull'evidenza, non sul fatto che qualcuno abbia chiesto un disegno."""
    state = _process_state(empty_process)

    assert state["draft_readiness"]["status"] == "not_modelable"
    spec = CAPABILITY_REGISTRY["process.canvas_handoff"]
    assert "readiness_for_canvas" in missing_prerequisites(spec, state)


def test_an_open_gap_does_not_cancel_what_is_already_known(
    interviewed_process, recorded_extractions
):
    """La lacuna resta dentro la bozza come domanda, non come divieto di disegnarla."""
    outcome = ensure_process_plan(interviewed_process["process_id"])
    snapshot = outcome.snapshot

    assert snapshot.draft_readiness["status"] == "modelable"
    assert snapshot.validation_readiness["status"] == "needs_validation"
    assert any(item.question == OPEN_GAP for item in snapshot.open_questions)
    # Il piano continua a contenere cio' che le fonti sostengono.
    understanding = ProcessUnderstanding.model_validate(snapshot.process_understanding)
    assert understanding.actors and understanding.steps


def test_the_readiness_of_a_process_without_a_plan_is_never_ambiguous():
    """`None` non era una risposta: chi leggeva lo trattava come "non modellabile"."""
    assert draft_readiness_without_plan(3)["status"] == "synthesizable"
    assert draft_readiness_without_plan(0)["status"] == "not_modelable"
    assert draft_readiness_without_plan(0)["blockers"]


# --- TEST 4 — clarification ancorate all'evidenza -------------------------


def test_the_question_carries_the_evidence_gap_that_generates_it(
    interviewed_process, recorded_extractions
):
    """"Chi approva?" e' una domanda da questionario finche' non dice da dove nasce."""
    ensure_process_plan(interviewed_process["process_id"])
    review = wd.get_bpmn_review(interviewed_process["bpmn_model_id"], include_approved=True)

    gap = next(
        item for item in review["open_questions"] if item["question"] == OPEN_GAP
    )
    assert "Paolo" in gap["grounded_in"]
    assert gap["options"], "una lacuna senza alternative costringe a scrivere a mano"
    assert gap["affects"]


def test_the_gap_reaches_the_canvas_with_its_grounding(
    interviewed_process, recorded_extractions
):
    ensure_process_plan(interviewed_process["process_id"])
    snapshot = build_process_snapshot(interviewed_process["process_id"])

    gap = next(item for item in snapshot.open_questions if item.question == OPEN_GAP)
    assert "Paolo" in gap.grounded_in
    assert "nasce da:" in render_snapshot_for_modeling(snapshot)


# --- TEST 6/7 — persistenza e prevenzione del falso successo --------------


def test_a_plan_that_the_database_does_not_have_is_not_a_plan(interviewed_process):
    """Read-after-write: la review si rilegge prima di dichiararla scritta."""
    with pytest.raises(PersistenceVerificationError):
        verify_review_persisted(
            interviewed_process["bpmn_model_id"], expect_plan_content=True
        )


def test_a_review_written_but_empty_fails_verification(
    interviewed_process, recorded_extractions, monkeypatch
):
    """Il writer non solleva eccezioni: e' rileggendo che si scopre che non c'e' niente."""
    ensure_process_plan(interviewed_process["process_id"])

    def _empty_review(*_args, **_kwargs):
        return {"version": 99, "process_understanding": {}}

    monkeypatch.setattr(wd, "get_bpmn_review", _empty_review)
    with pytest.raises(PersistenceVerificationError):
        verify_review_persisted(
            interviewed_process["bpmn_model_id"], expect_plan_content=True
        )


def test_a_canvas_that_was_not_saved_fails_verification(interviewed_process):
    with pytest.raises(PersistenceVerificationError):
        verify_bpmn_model_persisted(
            interviewed_process["bpmn_model_id"], START_END_ONLY_XML
        )


def test_a_start_end_canvas_is_not_a_model_of_a_process_we_know(
    interviewed_process, recorded_extractions
):
    """Il difetto del falso successo, isolato.

    La validazione semantica degradava a warning cio' che non poteva confrontare,
    quindi un start -> end tecnicamente valido usciva senza issue - e senza issue
    il runtime dichiarava "operazione completata, canvas aggiornato e verificato".
    """
    outcome = ensure_process_plan(interviewed_process["process_id"])

    validation = validate_canvas_against_process(
        xml=START_END_ONLY_XML,
        process_understanding=outcome.snapshot.process_understanding,
        bpmn_semantic_model=outcome.snapshot.bpmn_semantic_model,
    )

    assert validation["issues"], "un disegno vuoto davanti a un piano pieno non e' valido"
    assert any("attivita" in item for item in validation["issues"])


def test_a_construction_that_changed_nothing_is_a_failure_not_a_completion(
    interviewed_process, recorded_extractions
):
    """"Ho preparato il lavoro sul canvas" non dice ne' fatto ne' fallito."""
    ensure_process_plan(interviewed_process["process_id"])
    saved = wd.get_bpmn_model(interviewed_process["bpmn_model_id"])

    state = {
        "process_id": interviewed_process["process_id"],
        "bpmn_model_id": interviewed_process["bpmn_model_id"],
        "canvas_route": "construction",
        "canvas_initial_saved_bpmn_xml": saved["xml"],
        "canvas_run_snapshot_id": build_process_snapshot(
            interviewed_process["process_id"]
        ).snapshot_id,
    }

    result = refresh_canvas_context_after_work(state)

    assert result["canvas_run_status"] == "failed"
    report = canvas_completion_report({**state, **result})
    message = report["messages"][0].content
    assert "completata" not in message.casefold() or "non ho completato" in message.casefold()
    assert "non risulta salvata nessuna modifica" in message


def test_a_preview_waiting_for_approval_is_not_a_failed_write(
    interviewed_process, recorded_extractions
):
    """Non aver scritto, li', e' il comportamento voluto.

    Il controllo sul canvas immutato deve distinguere "nessuno ha scritto" da
    "non si doveva ancora scrivere": chiamare fallimento un'anteprima in attesa
    di approvazione sarebbe lo stesso difetto rovesciato.
    """
    ensure_process_plan(interviewed_process["process_id"])
    saved = wd.get_bpmn_model(interviewed_process["bpmn_model_id"])

    result = refresh_canvas_context_after_work(
        {
            "process_id": interviewed_process["process_id"],
            "bpmn_model_id": interviewed_process["bpmn_model_id"],
            "canvas_route": "construction",
            "canvas_initial_saved_bpmn_xml": saved["xml"],
            "canvas_preview_xml": START_END_ONLY_XML,
            "canvas_run_snapshot_id": build_process_snapshot(
                interviewed_process["process_id"]
            ).snapshot_id,
        }
    )

    assert result.get("canvas_run_status") != "failed"


def test_completion_is_refused_when_there_is_nothing_to_verify_against(
    interviewed_process,
):
    """Nessuna issue senza piano significa "controllo non eseguito", non "modello corretto"."""
    wd.update_bpmn_model(
        interviewed_process["bpmn_model_id"],
        START_END_ONLY_XML,
        change_summary="canvas di prova",
        source="test",
    )

    result = evaluate_canvas_completion(
        {
            "process_id": interviewed_process["process_id"],
            "bpmn_model_id": interviewed_process["bpmn_model_id"],
            "canvas_route": "construction",
            "canvas_loop_attempt": 5,
            "canvas_loop_max_attempts": 1,
        }
    )

    assert result["canvas_loop_status"] != "completed"
    assert result["canvas_run_status"] == "failed"
    assert any("evidenza" in item for item in result["blocking_conditions"])


def test_a_local_edit_on_a_hand_drawn_canvas_is_not_blocked_by_a_missing_plan(
    empty_process,
):
    """Una modifica locale si verifica contro l'XML, non contro un piano che non c'e'.

    Pretendere un piano del processo qui sarebbe lo stesso difetto rovesciato: un
    fallimento dichiarato senza motivo su un lavoro che e' andato a buon fine.
    """
    wd.update_bpmn_model(
        empty_process["bpmn_model_id"],
        START_END_ONLY_XML,
        change_summary="canvas disegnato a mano",
        source="test",
    )

    result = evaluate_canvas_completion(
        {
            "process_id": empty_process["process_id"],
            "bpmn_model_id": empty_process["bpmn_model_id"],
            "canvas_route": "patch_edit",
            "canvas_loop_attempt": 0,
            "canvas_loop_max_attempts": 2,
        }
    )

    assert result["canvas_loop_status"] == "completed"
    assert result["canvas_run_status"] == "done"


def test_the_completion_message_says_which_plan_version_it_verified():
    """"Aggiornato" senza dire rispetto a cosa non e' un'affermazione verificabile."""
    report = canvas_completion_report(
        {
            "canvas_loop_status": "completed",
            "validation_report": {"process_snapshot_label": "V7"},
        }
    )

    assert "V7" in report["messages"][0].content


def test_a_process_without_interviews_is_told_so_instead_of_being_drawn(empty_process):
    """Il Canvas non parte su un piano vuoto: lo farebbe partire per produrre start -> end."""
    from backend.graphs.process.graph import _canvas_handoff_without_plan

    result = _canvas_handoff_without_plan(ensure_process_plan(empty_process["process_id"]))
    message = result["messages"][0].content

    assert "interviste" in message or "fonti" in message
    assert result["delegation_events"][0]["status"] == "blocked"


def test_a_failed_synthesis_is_told_as_a_failure_not_as_a_missing_interview(
    interviewed_process, monkeypatch
):
    """Due situazioni diverse, due frasi diverse: un guasto non e' una discovery da fare."""
    from backend.graphs.process.graph import _canvas_handoff_without_plan

    def _broken_extraction(*_args, **_kwargs):
        from backend.process_understanding import ExtractionFailure

        return ProcessUnderstandingResult(
            status="failed",
            failure=ExtractionFailure(
                kind="invalid_structured_output",
                message="Il modello non ha prodotto un piano valido.",
                retryable=False,
                attempt=1,
            ),
        )

    monkeypatch.setattr(process_synthesis, "build_process_understanding", _broken_extraction)
    outcome = ensure_process_plan(interviewed_process["process_id"])

    assert outcome.action == "synthesis_failed"
    message = _canvas_handoff_without_plan(outcome)["messages"][0].content
    assert "non ho disegnato niente" in message
    assert "Il modello non ha prodotto un piano valido." in message


# --- TEST 10 — il giro completo -------------------------------------------


def test_the_whole_loop_keeps_one_truth_from_the_interviews_to_the_canvas(
    interviewed_process, recorded_extractions
):
    """process -> interviste -> piano -> canvas -> risposta -> nuova versione -> canvas.

    Un solo processo, una sola verita', e ogni passaggio che dichiara su quale
    versione sta lavorando.
    """
    # Il piano nasce dalle interviste.
    outcome = ensure_process_plan(interviewed_process["process_id"])
    assert outcome.action == "synthesized"
    first = outcome.snapshot

    # I due lati leggono la stessa versione.
    canvas_side = load_canvas_context(
        {"bpmn_model_id": interviewed_process["bpmn_model_id"]}
    )
    assert canvas_side["process_snapshot_id"] == first.snapshot_id

    # Il consulente chiude la lacuna: la risposta e' conoscenza del processo.
    wd.answer_bpmn_review_question(
        bpmn_model_id=interviewed_process["bpmn_model_id"],
        question=OPEN_GAP,
        answer="Lo regolarizza Acquisti a posteriori",
    )

    # La conoscenza e' cambiata, e la versione lo dice.
    second = build_process_snapshot(interviewed_process["process_id"])
    assert second.snapshot_id != first.snapshot_id
    assert second.version > first.version
    answered = next(item for item in second.open_questions if item.question == OPEN_GAP)
    assert answered.answer == "Lo regolarizza Acquisti a posteriori"

    # Il piano non viene ricostruito sopra la risposta: le fonti sono le stesse.
    again = ensure_process_plan(interviewed_process["process_id"])
    assert again.action == "reused"
    assert len(recorded_extractions) == 1
    assert again.snapshot.snapshot_id == second.snapshot_id

    # E il Canvas legge la versione nuova, non quella su cui aveva iniziato.
    refreshed = load_canvas_context(
        {"bpmn_model_id": interviewed_process["bpmn_model_id"]}
    )
    assert refreshed["process_snapshot_id"] == second.snapshot_id
