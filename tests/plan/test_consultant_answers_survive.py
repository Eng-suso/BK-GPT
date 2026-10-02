"""L9: una risposta del consulente sopravvive a ogni ricostruzione del piano.

Le risposte non sono artefatti da rigenerare: sono la fonte con la precedenza
piu' alta, quella di chi conosce il processo. Il piano pero' si ricostruisce
dalle interviste - e con P2 si ricostruisce piu' spesso e per pezzi - e la
domanda a cui il consulente aveva risposto viene dall'estrazione, non da lui.

La risposta restava salvata, ma si riagganciava alla domanda solo se il piano
nuovo la riponeva **con lo stesso testo**. Bastava che la ricostruzione non la
chiedesse piu', o che un filtro la scartasse come ridondante, e la risposta
spariva da tutto cio' che si legge: il pannello, lo snapshot che l'agente usa
per ragionare, il gate di approvazione. Il consulente aveva detto una cosa, e il
prodotto si comportava come se non l'avesse mai detta.
"""

from __future__ import annotations

import uuid

import pytest

from backend.settings import settings

if not settings.workspace_database_url:
    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)

QUESTION = "Chi autorizza gli ordini urgenti di Paolo oltre i mille euro?"
ANSWER = "Il direttore di stabilimento, sempre."


def _plan(*unknowns: dict) -> dict:
    return {
        "title": "Acquisti urgenti",
        "actors": [
            {"id": "manutenzione", "label": "Manutenzione", "kind": "team"},
            {"id": "acquisti", "label": "Acquisti", "kind": "team"},
        ],
        "steps": [
            {"id": "chiama_fornitore", "label": "Chiama il fornitore", "actor_ids": ["manutenzione"]},
            {"id": "regolarizza", "label": "Regolarizza l'ordine", "actor_ids": ["acquisti"]},
        ],
        "unknowns": list(unknowns),
    }


def _unknown(question: str = QUESTION, severity: str = "blocking") -> dict:
    return {
        "question": question,
        "affects": "autorizzazione",
        "severity": severity,
        "grounded_in": "Paolo dice che chiama il fornitore, Acquisti regolarizza l'ordine dopo",
    }


# Il testo contro cui il filtro di ancoraggio giudica le domande: la domanda
# qui sopra nomina cose che le note dicono, quindi alla prima preparazione passa.
NOTES = (
    "Paolo, Manutenzione: quando la linea e' ferma chiamo il fornitore. "
    "Acquisti regolarizza l'ordine dopo. Gli ordini urgenti oltre mille euro "
    "qualcuno li autorizza, non so chi."
)


@pytest.fixture()
def process():
    from backend import workspace_database as wd
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    suffix = uuid.uuid4().hex[:8]
    client = wd.create_client(name=f"Contoso {suffix}")
    project = wd.create_project(client_id=client["id"], name=f"Manutenzione {suffix}")
    created = wd.create_process(project_id=project["id"], name="Acquisti urgenti")
    try:
        yield wd.get_process(created["id"])
    finally:
        reset_current_tenant_id(token)


def _prepare(process: dict, plan: dict) -> dict:
    from backend import workspace_database as wd

    return wd.prepare_bpmn_review(
        bpmn_model_id=process["bpmn_model_id"],
        process_description=NOTES,
        process_understanding=plan,
    )


def _answered(review: dict) -> dict[str, str]:
    return {
        item["question"]: item["answer"]
        for item in review["open_questions"]
        if item.get("answer")
    }


def _answer(process: dict) -> None:
    from backend import workspace_database as wd

    wd.answer_bpmn_review_question(process["bpmn_model_id"], QUESTION, ANSWER)


def test_the_answer_is_there_after_the_consultant_gives_it(process):
    """Il punto di partenza, senza ricostruzione: la risposta e' agganciata."""
    _prepare(process, _plan(_unknown()))
    _answer(process)

    from backend import workspace_database as wd

    review = wd.get_bpmn_review(process["bpmn_model_id"], include_approved=True)
    assert _answered(review) == {QUESTION: ANSWER}


def test_a_rebuild_that_asks_the_same_question_keeps_the_answer(process):
    _prepare(process, _plan(_unknown()))
    _answer(process)

    review = _prepare(process, _plan(_unknown()))

    assert _answered(review) == {QUESTION: ANSWER}


def test_a_rebuild_that_no_longer_asks_the_question_keeps_the_answer(process):
    """Il caso che si rompeva: l'estrazione nuova non ripone la domanda, e con
    lei spariva la risposta."""
    _prepare(process, _plan(_unknown()))
    _answer(process)

    review = _prepare(process, _plan())

    assert _answered(review) == {QUESTION: ANSWER}


def test_an_answered_question_is_not_dropped_as_redundant(process):
    """I filtri delle domande esistono per non chiedere al consulente cio' che
    il piano sa gia'. Una domanda a cui ha gia' risposto non gli viene chiesta:
    e' la traccia di una sua decisione, e scartarla la cancellerebbe."""
    from backend import workspace_database as wd

    categoria = "Quali sono gli attori del processo?"
    _prepare(process, _plan(_unknown(categoria, severity="non_blocking")))
    wd.answer_bpmn_review_question(process["bpmn_model_id"], categoria, "Manutenzione e Acquisti.")

    review = _prepare(process, _plan(_unknown(categoria, severity="non_blocking")))

    assert _answered(review).get(categoria) == "Manutenzione e Acquisti."


def test_an_answered_blocking_question_does_not_block_again(process):
    from backend import workspace_database as wd

    _prepare(process, _plan(_unknown()))
    _answer(process)
    _prepare(process, _plan())

    with wd.workspace_connection() as session:
        row = wd.tenant_row(session, wd.WorkspaceBpmnReview, process["bpmn_model_id"])
        still_open = [item["question"] for item in wd.unanswered_questions(row)]

    assert QUESTION not in still_open


def test_a_revision_of_the_plan_keeps_the_answer_too(process):
    """L'altro punto da cui un piano si riscrive: l'emendamento. Stessa regola."""
    from backend import workspace_database as wd

    _prepare(process, _plan(_unknown()))
    _answer(process)

    review = wd.revise_bpmn_review(process["bpmn_model_id"], _plan(), change_summary="emendamento")

    assert _answered(review) == {QUESTION: ANSWER}


def test_the_agent_still_reads_the_answer_after_the_rebuild(process):
    """Lo snapshot e' cio' con cui l'agente ragiona: una risposta che non c'e'
    li' e' una risposta che l'agente contraddira'."""
    from backend.agents.process_snapshot import build_process_snapshot

    _prepare(process, _plan(_unknown()))
    _answer(process)
    _prepare(process, _plan())

    snapshot = build_process_snapshot(process["id"])

    assert {item.question: item.answer for item in snapshot.open_questions if item.answer} == {
        QUESTION: ANSWER
    }
