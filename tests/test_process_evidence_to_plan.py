"""Il percorso Evidenza -> Comprensione -> Piano, verificato dove si rompeva.

Il test E2E di V2 si e' fermato su tre rotture che sembravano tre bug e sono
una sola frattura: cio' che le interviste avevano raccolto arrivava a un solo
nodo del grafo. Il consulente vedeva un planner che dichiarava di conoscere
"esclusivamente il titolo del processo" dopo tre interviste (PROCESS-V2-11), tre
domande bloccanti su sourcing, budget e conformita' che nessuna fonte aveva mai
nominato (PROCESS-V2-12/15), e due schermate che raccontavano stati diversi
dello stesso processo (PROCESS-V2-13).

Qui si verifica il comportamento, non l'implementazione: dato un registro
dell'evidenza, cosa vede chi deve decidere, quali domande passano e quali no,
e cosa succede a un piano che ignora le fonti. Nessuna chiamata a un modello,
nessun ordine fra i test, nessuno stato che sopravvive: eseguirli due volte da'
lo stesso esito.
"""

from __future__ import annotations

import pytest

from backend.agents.evidence_brief import (
    content_tokens,
    evidence_prompt_block,
    is_catch_all_question,
    ledger_vocabulary,
    question_is_grounded,
    turn_evidence_ledger,
)
from backend.agents.primary_scope import build_scope_system_prompt


# --- il materiale: tre voci sullo stesso processo -------------------------


def claim(
    statement: str,
    voice: str,
    *,
    source: str = "",
    scope_label: str = "",
    quote: str = "",
) -> dict:
    """Un'affermazione come la scrive l'estrattore delle evidenze."""
    return {
        "claim": statement,
        "attributed_to": voice,
        "source_name": source or f"Intervista {voice}",
        "scope_label": scope_label,
        "epistemic_status": "reported",
        "quote": quote,
        "quote_verified": bool(quote),
    }


THREE_INTERVIEWS: list[dict] = [
    claim(
        "Acquisti crea e invia l'ordine al fornitore",
        "Francesca Neri",
        scope_label="reparto Acquisti",
    ),
    claim(
        "Per importi piccoli l'approvazione puo' non essere formalizzata",
        "Paolo Ricci",
        scope_label="reparto Produzione",
    ),
    claim(
        "L'autorizzazione del responsabile e' sempre richiesta",
        "Francesca Neri",
        scope_label="reparto Acquisti",
    ),
    claim(
        "Quando serve con urgenza il reparto contatta direttamente il fornitore",
        "Marco Villa",
        scope_label="reparto Produzione",
    ),
]


def process_state(claims: list[dict] | None = None, **overrides) -> dict:
    """Lo stato di un turno di chat processo, come lo apre `load_process_context`."""
    return {
        "scope_type": "process",
        "scope_key": "process:p1:pr1",
        "chat_mode": "agent",
        "project_id": "p1",
        "process_id": "pr1",
        "process_name": "Ciclo passivo",
        "evidence_ledger": {
            "status": "ok",
            "claims": claims if claims is not None else THREE_INTERVIEWS,
            "count": len(claims if claims is not None else THREE_INTERVIEWS),
        },
        "process_claims": [],
        "contradictions": [],
        **overrides,
    }


# --- PROCESS-V2-11/13: l'evidenza arriva a chi deve decidere ---------------


def test_the_scope_prompt_carries_what_the_interviews_said():
    """Chi apre una passata vede le voci, non solo il nome del processo."""
    prompt = build_scope_system_prompt(process_state())

    assert "REGISTRO DELL'EVIDENZA" in prompt
    for voice in ("Francesca Neri", "Paolo Ricci", "Marco Villa"):
        assert voice in prompt
    assert "Acquisti crea e invia l'ordine al fornitore" in prompt


def test_the_scope_prompt_says_a_recorded_fact_is_not_a_gap():
    """Il registro non e' materiale opzionale: e' cio' che il processo sa."""
    prompt = build_scope_system_prompt(process_state())

    assert "Non dichiararlo mancante" in prompt
    assert "citare la lacuna o la contraddizione concreta" in prompt


def test_an_empty_ledger_does_not_pretend_to_know_anything():
    """Senza fonti il prompt lo dice, invece di inventare un registro."""
    prompt = build_scope_system_prompt(process_state(claims=[]))

    assert "nessuna affermazione registrata" in prompt
    # Le regole su come usare il registro non hanno senso senza registro.
    assert "Non dichiararlo mancante" not in prompt


def test_the_ledger_stays_out_of_the_scopes_that_do_not_have_one():
    """Sul progetto e sul consulente il registro non e' definito."""
    assert evidence_prompt_block({**process_state(), "scope_type": "project"}) == []
    assert evidence_prompt_block({"scope_type": "consultant"}) == []


def test_two_voices_on_the_same_fact_count_as_two():
    """Il sostegno si ricalcola sull'unione di persistito e appena raccolto."""
    fresh = [claim("L'autorizzazione del responsabile e' sempre richiesta", "Paolo Ricci")]
    entries = turn_evidence_ledger(process_state(process_claims=fresh))

    corroborated = [
        entry
        for entry in entries
        if "autorizzazione" in entry.claim.statement.lower()
        and entry.corroborating_sources
    ]
    assert corroborated, "due voci sulla stessa affermazione devono corroborarsi"


def test_the_same_ledger_reaches_the_prompt_and_the_router():
    """PROCESS-V2-13: una sola resa, non due letture divergenti dello stesso stato."""
    from backend.graphs.process.graph import render_ledger_lines

    state = process_state()
    rendered = render_ledger_lines(turn_evidence_ledger(state))

    assert rendered in build_scope_system_prompt(state)


# --- PROCESS-V2-12/15: una domanda deve citare la lacuna che la genera -----


GENERIC_QUESTIONS = [
    "Quali sono gli attori del processo?",
    "Quali attivita' compongono il processo?",
    "Quali regole di conformita' si applicano?",
    "Quali soglie di approvazione servono per il sourcing?",
    "Come funziona il processo?",
    "E' prevista una verifica budget?",
]

GROUNDED_QUESTIONS = [
    "Paolo dice che per importi piccoli l'approvazione puo' non essere "
    "formalizzata, Francesca dice che l'autorizzazione e' sempre richiesta: "
    "quale descrive il processo effettivo?",
    "Francesca dice che Acquisti crea e invia l'ordine: cosa accade fra invio "
    "ordine e ricezione fattura?",
    "Quando il reparto contatta direttamente il fornitore per urgenza, chi "
    "autorizza a posteriori?",
]


@pytest.mark.parametrize("question", GENERIC_QUESTIONS)
def test_a_template_question_does_not_reach_the_consultant(question):
    vocabulary = ledger_vocabulary(turn_evidence_ledger(process_state()))
    assert not question_is_grounded(question, vocabulary)


@pytest.mark.parametrize("question", GROUNDED_QUESTIONS)
def test_a_question_that_names_the_gap_gets_through(question):
    vocabulary = ledger_vocabulary(turn_evidence_ledger(process_state()))
    assert question_is_grounded(question, vocabulary)


def test_a_broad_question_survives_when_it_declares_its_gap():
    """La forma larga non e' il difetto: esserlo senza motivo lo e'."""
    vocabulary = ledger_vocabulary(turn_evidence_ledger(process_state()))

    assert question_is_grounded(
        "Quali sono gli attori?",
        vocabulary,
        grounded_in="Francesca nomina Acquisti, ma nessuno dice chi autorizza",
    )
    assert not question_is_grounded(
        "Quali sono gli attori?",
        vocabulary,
        grounded_in="il team di sourcing strategico",
    )


def test_the_first_interview_can_still_ask_broad_questions():
    """Senza registro non c'e' niente rispetto a cui una domanda sia generica."""
    for question in GENERIC_QUESTIONS:
        assert question_is_grounded(question, set())


def test_the_category_shape_is_recognised_for_what_it_is():
    assert is_catch_all_question("Quali sono gli attori del processo?")
    assert not is_catch_all_question(
        "Chi autorizza l'ordine quando il reparto ha gia' contattato il fornitore?"
    )


def test_the_grounding_check_ignores_the_words_every_question_uses():
    """"processo", "attori", "regole" non provano che si parli di queste note."""
    assert content_tokens("Quali sono gli attori del processo?") == set()


# --- il registro decide anche il passo successivo, non solo il testo -------


def test_an_ungrounded_clarification_is_refused_and_sent_to_collect_evidence():
    """Chiedere una categoria gia' coperta non e' un chiarimento: e' un ricominciare."""
    from backend.graphs.process.graph import ungrounded_clarification

    refusal = ungrounded_clarification(
        status="clarification_required",
        question="Quali sono gli attori del processo?",
        state=process_state(),
    )

    assert refusal is not None
    assert "evidence ledger already covers" in refusal


def test_a_grounded_clarification_reaches_the_consultant():
    from backend.graphs.process.graph import ungrounded_clarification

    assert (
        ungrounded_clarification(
            status="clarification_required",
            question=GROUNDED_QUESTIONS[0],
            state=process_state(),
        )
        is None
    )


def test_a_refusal_by_the_runtime_is_not_rewritten_as_a_missing_question():
    """Un prerequisito mancante o una capability fuori modalita' si dicono cosi' come sono."""
    from backend.graphs.process.graph import ungrounded_clarification

    for status in ("missing_prerequisite", "capability_not_in_mode", "invalid_structured_decision"):
        assert (
            ungrounded_clarification(
                status=status,
                question="Quali sono gli attori del processo?",
                state=process_state(),
            )
            is None
        )


def test_the_first_turn_can_still_ask_before_any_evidence_exists():
    from backend.graphs.process.graph import ungrounded_clarification

    assert (
        ungrounded_clarification(
            status="clarification_required",
            question="Quali sono gli attori del processo?",
            state=process_state(claims=[]),
        )
        is None
    )


def test_edit_mode_keeps_its_clarification_instead_of_collecting_evidence():
    """In Modifica raccogliere evidenza non e' un'opzione: la domanda resta."""
    from backend.graphs.process.graph import ungrounded_clarification

    assert (
        ungrounded_clarification(
            status="clarification_required",
            question="Quali sono gli attori del processo?",
            state=process_state(chat_mode="edit"),
        )
        is None
    )


# --- il piano non puo' ripartire dal titolo mentre le fonti esistono -------


def test_a_plan_with_no_actors_is_refused_when_the_evidence_exists():
    """PROCESS-V2-11 nella sua forma piu' dannosa: il vuoto che diventa stato ufficiale."""
    from backend.agents.process_snapshot import plan_ignores_evidence
    from backend.process_understanding import ProcessUnderstanding

    empty_plan = ProcessUnderstanding(title="Ciclo passivo")

    assert plan_ignores_evidence(empty_plan, 4) is not None
    assert plan_ignores_evidence(None, 4) is not None


def test_a_plan_that_carries_the_actors_goes_through():
    from backend.agents.process_snapshot import plan_ignores_evidence
    from backend.process_understanding import ProcessActor, ProcessUnderstanding

    plan = ProcessUnderstanding(
        title="Ciclo passivo",
        actors=[ProcessActor(id="acquisti", label="Acquisti", kind="team")],
    )

    assert plan_ignores_evidence(plan, 4) is None


def test_a_process_without_evidence_can_still_start_from_a_sketch():
    """Senza fonti registrate il gate non ha niente da difendere."""
    from backend.agents.process_snapshot import plan_ignores_evidence
    from backend.process_understanding import ProcessUnderstanding

    assert plan_ignores_evidence(ProcessUnderstanding(title="Nuovo"), 0) is None


# --- le domande scartate non spariscono in silenzio ------------------------


def test_the_dropped_questions_stay_visible_as_work_to_redo():
    from backend.process_understanding import ProcessUnderstanding, ProcessUnknown
    from backend.workspace_services.bpmn_review import (
        _ungrounded_question_warning,
        partition_grounded_unknowns,
    )

    notes = (
        "Francesca Neri: Acquisti crea e invia l'ordine al fornitore. "
        "Paolo Ricci: per importi piccoli l'approvazione puo' non essere formalizzata."
    )
    plan = ProcessUnderstanding(
        title="Ciclo passivo",
        unknowns=[
            ProcessUnknown(
                question="Quali soglie di approvazione servono per il sourcing?",
                affects="approvazione",
            ),
            ProcessUnknown(
                question=(
                    "Paolo dice che per importi piccoli l'approvazione puo' non "
                    "essere formalizzata: chi decide la soglia?"
                ),
                affects="approvazione",
            ),
        ],
    )

    kept, dropped = partition_grounded_unknowns(plan, notes)

    assert [item.question for item in kept] == [plan.unknowns[1].question]
    assert [item.question for item in dropped] == [plan.unknowns[0].question]
    assert "sourcing" in _ungrounded_question_warning(dropped)


# --- P0: il source set e' operativo, non una conseguenza del KG ------------


def _workspace_sources() -> list[dict]:
    return [
        {
            "id": "src-laura",
            "project_id": "p1",
            "process_id": "pr1",
            "name": "Intervista Laura Conti",
            "type": "Intervista",
            "meta": "Laura descrive la richiesta e il passaggio ad Acquisti.",
        },
        {
            "id": "src-paolo",
            "project_id": "p1",
            "process_id": "pr1",
            "name": "Intervista Paolo Marchetti",
            "type": "Intervista",
            "meta": "Paolo descrive il percorso urgente.",
        },
        {
            "id": "src-francesca",
            "project_id": "p1",
            "process_id": "pr1",
            "name": "Intervista Francesca Neri",
            "type": "Intervista",
            "meta": "Francesca descrive ordine e controlli.",
        },
    ]


def test_the_source_set_does_not_flap_when_the_claim_projection_does(monkeypatch):
    """Tre richieste e un restart vedono le stesse fonti anche se il KG degrada."""
    from backend.graphs.process import nodes
    from backend.toolsets import process_memory
    from backend.workspace_services import source_document

    monkeypatch.setattr(nodes.workspace_database, "list_project_sources", lambda _project_id: _workspace_sources())
    monkeypatch.setattr(
        source_document,
        "source_document",
        lambda source_id: {
            **next(item for item in _workspace_sources() if item["id"] == source_id),
            "summary": "Fonte salvata",
            "participants": [],
            "content": f"testo autoritativo di {source_id}",
            "has_content": True,
        },
    )
    ledgers = iter(
        [
            {"status": "ok", "claims": THREE_INTERVIEWS, "count": 4},
            {"status": "error", "claims": [], "count": 0, "reason": "projection restarting"},
            {"status": "ok", "claims": THREE_INTERVIEWS, "count": 4},
            {"status": "empty", "claims": [], "count": 0},
        ]
    )
    monkeypatch.setattr(process_memory, "process_claim_ledger", lambda *_args, **_kwargs: next(ledgers))

    snapshots = [nodes.load_evidence_ledger("p1", "pr1") for _ in range(4)]
    expected_ids = ["src-francesca", "src-laura", "src-paolo"]

    assert [snapshot["source_ids"] for snapshot in snapshots] == [expected_ids] * 4
    assert len({snapshot["source_set_id"] for snapshot in snapshots}) == 1
    assert [snapshot["source_count"] for snapshot in snapshots] == [3, 3, 3, 3]
    assert snapshots[1]["claim_status"] == "error"
    assert snapshots[1]["status"] == "ok"


def test_the_scope_prompt_keeps_sources_visible_when_claims_are_still_projecting():
    state = process_state(claims=[])
    state["evidence_ledger"] = {
        "status": "ok",
        "claim_status": "error",
        "claims": [],
        "count": 0,
        "source_count": 3,
        "source_set_id": "stable-set",
        "sources": [
            {**source, "content": f"testo autoritativo di {source['id']}"}
            for source in _workspace_sources()
        ],
    }

    prompt = build_scope_system_prompt(state)

    for voice in ("Laura Conti", "Paolo Marchetti", "Francesca Neri"):
        assert voice in prompt
    assert "3 fonti" in prompt
    assert "claim projection" in prompt


def test_a_plan_cannot_ignore_saved_sources_just_because_claims_are_not_ready():
    from backend.agents.process_snapshot import plan_ignores_evidence
    from backend.process_understanding import ProcessUnderstanding

    assert plan_ignores_evidence(ProcessUnderstanding(title="Ciclo passivo"), 3)


# --- P1: bozza modellabile e validazione sono due soglie -------------------


def test_partial_evidence_can_be_modelable_without_being_validated():
    from backend.process_understanding import (
        ProcessActor,
        ProcessBoundaries,
        ProcessStep,
        ProcessUnderstanding,
        ProcessUnknown,
        draft_readiness_from_understanding,
        validation_readiness_from_understanding,
    )

    understanding = ProcessUnderstanding(
        title="Ciclo passivo",
        actors=[ProcessActor(id="acquisti", label="Acquisti", kind="team")],
        steps=[
            ProcessStep(
                id="crea_ordine",
                label="Crea e invia ordine",
                actor_ids=["acquisti"],
                source_evidence=["src-francesca"],
            )
        ],
        sequence=["crea_ordine"],
        main_success_path=["crea_ordine"],
        boundaries=ProcessBoundaries(trigger="Fabbisogno rilevato", success_end="Ordine inviato"),
        unknowns=[
            ProcessUnknown(
                question="Chi autorizza a posteriori l'ordine urgente?",
                affects="gestione urgenze",
                severity="blocking",
                grounded_in="Paolo descrive l'ordine urgente ma non chi lo regolarizza.",
            )
        ],
    )

    draft = draft_readiness_from_understanding(understanding)
    validation = validation_readiness_from_understanding(understanding)

    assert draft["status"] == "modelable"
    assert draft["blockers"] == []
    assert draft["gaps"] == ["Chi autorizza a posteriori l'ordine urgente?"]
    assert validation["status"] == "needs_validation"


# --- P1: non si richiede cio' che il modello ha gia' estratto --------------


def _plan_that_already_knows(*questions: str):
    """Un piano che ha trigger, attori, attivita', decisioni e fine processo."""
    from backend.process_understanding import (
        ProcessActor,
        ProcessBoundaries,
        ProcessDecision,
        ProcessStep,
        ProcessUnderstanding,
        ProcessUnknown,
    )

    return ProcessUnderstanding(
        title="Ciclo passivo",
        actors=[ProcessActor(id="acquisti", label="Acquisti", kind="team")],
        steps=[ProcessStep(id="crea", label="Crea ordine", actor_ids=["acquisti"])],
        sequence=["crea"],
        main_success_path=["crea"],
        decisions=[
            ProcessDecision(id="urgente", label="Richiesta urgente?", outcomes=["si", "no"])
        ],
        boundaries=ProcessBoundaries(
            trigger="Fabbisogno rilevato",
            start_event="Richiesta ricevuta",
            success_end="Ordine inviato",
        ),
        unknowns=[
            ProcessUnknown(
                question=question,
                affects="ciclo passivo",
                grounded_in="Laura e Francesca descrivono gia' questo punto.",
            )
            for question in questions
        ],
    )


@pytest.mark.parametrize(
    "question",
    [
        "Qual e' il trigger del processo?",
        "Qual e' la prima attivita'?",
        "Quali sono gli attori del processo?",
        "Quali decisioni ci sono?",
        "Come finisce il processo?",
    ],
)
def test_clarification_drops_a_fact_already_present_in_the_understanding(question):
    from backend.workspace_services.bpmn_review import partition_answered_unknowns

    kept, answered = partition_answered_unknowns(_plan_that_already_knows(question))

    assert kept == []
    assert [item.question for item in answered] == [question]


@pytest.mark.parametrize(
    "question",
    [
        "Chi regolarizza a posteriori l'ordine urgente che Paolo manda al fornitore?",
        "Quale controllo si applica quando l'ordine urgente supera il budget del reparto?",
        "Quando la richiesta arriva a voce, chi la trascrive prima dell'ordine?",
    ],
)
def test_a_gap_on_a_concrete_case_survives_even_if_the_category_is_populated(question):
    """Il filtro toglie le domande di categoria, non le lacune vere.

    Un piano che ha degli attori non rende superflua "chi regolarizza l'ordine
    urgente": scartarla perche' nomina un ruolo silenzierebbe la lacuna che il
    consulente deve ancora chiudere.
    """
    from backend.workspace_services.bpmn_review import partition_answered_unknowns

    kept, answered = partition_answered_unknowns(_plan_that_already_knows(question))

    assert answered == []
    assert [item.question for item in kept] == [question]


def test_an_answered_question_is_reported_as_answered_not_as_ungrounded():
    """Due difetti diversi, due spiegazioni diverse per chi legge il piano."""
    from backend.workspace_services.bpmn_review import (
        _answered_question_warning,
        _ungrounded_question_warning,
    )

    plan = _plan_that_already_knows("Quali sono gli attori del processo?")

    assert "contiene gia'" in _answered_question_warning(plan.unknowns)
    assert "contiene gia'" not in _ungrounded_question_warning(plan.unknowns)
