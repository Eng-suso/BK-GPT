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
    from backend.graphs.process.subgraphs.modeling.tools import _plan_ignores_evidence
    from backend.process_understanding import ProcessUnderstanding

    empty_plan = ProcessUnderstanding(title="Ciclo passivo")

    assert _plan_ignores_evidence(empty_plan, claim_count=4) is not None
    assert _plan_ignores_evidence(None, claim_count=4) is not None


def test_a_plan_that_carries_the_actors_goes_through():
    from backend.graphs.process.subgraphs.modeling.tools import _plan_ignores_evidence
    from backend.process_understanding import ProcessActor, ProcessUnderstanding

    plan = ProcessUnderstanding(
        title="Ciclo passivo",
        actors=[ProcessActor(id="acquisti", label="Acquisti", kind="team")],
    )

    assert _plan_ignores_evidence(plan, claim_count=4) is None


def test_a_process_without_evidence_can_still_start_from_a_sketch():
    """Senza fonti registrate il gate non ha niente da difendere."""
    from backend.graphs.process.subgraphs.modeling.tools import _plan_ignores_evidence
    from backend.process_understanding import ProcessUnderstanding

    assert _plan_ignores_evidence(ProcessUnderstanding(title="Nuovo"), claim_count=0) is None


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
