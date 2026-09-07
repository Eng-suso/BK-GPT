"""La memoria del consulente si riempie per decisione sua, non per iniziativa dell'agente.

Due difetti dallo stesso test E2E:

CONSULTANT-V2-01 — DeliR aveva registrato un "metodo riutilizzabile candidato"
senza che il consulente lo avesse chiesto. Il tool scriveva alla prima chiamata,
quindi bastava che il modello ritenesse il pattern interessante.

CONSULTANT-V2-02 — l'agente elencava offerte, metodo di vendita, posizionamento,
stile comunicativo e preferenze BPMN come "informazioni mancanti", anche in un
incarico di processo dove non servono. La tassonomia della memoria veniva letta
come un modulo da compilare.
"""

from pathlib import Path

import pytest

from backend.agents.run_context import bind_active_thread
from backend.graphs.consulting.graph import CONSULTING_SUBGRAPH_CONTRACT
from backend.memory import pending_actions
from backend.toolsets.memory import manage_consultant_playbook


SKILLS_DIR = Path(__file__).resolve().parents[1] / "backend" / "graphs" / "consulting" / "skills"
MEMORY_GOVERNANCE = (SKILLS_DIR / "consultant_memory_governance.md").read_text(encoding="utf-8")


@pytest.fixture
def consulting_thread(monkeypatch):
    """Un thread isolato, con lo store delle azioni in attesa vuoto."""
    monkeypatch.setattr(pending_actions, "_MEMORY_STORE", {})
    with bind_active_thread("thread-playbook"):
        yield "thread-playbook"


def save_proposal(**kwargs) -> str:
    payload = {
        "operation": "save_candidate",
        "title": "Intervista in due passaggi",
        "body": "Prima il flusso dichiarato, poi le eccezioni reali.",
        "applies_when": "Discovery di un processo poco documentato",
    }
    payload.update(kwargs)
    return manage_consultant_playbook.invoke(payload)


def test_proposing_a_method_writes_nothing(consulting_thread, monkeypatch):
    from backend.memory import canonical_memory

    def refuse(*_args, **_kwargs):
        raise AssertionError("save_candidate ha scritto senza conferma")

    monkeypatch.setattr(canonical_memory, "write_procedural_candidate", refuse)

    result = save_proposal()

    assert "awaiting_confirmation" in result
    assert "Intervista in due passaggi" in result
    # Il testo che l'agente rilegge non deve permettergli di dire "registrato".
    assert "non registrato" in result


def test_the_proposal_survives_the_turn_and_is_written_only_on_confirmation(
    consulting_thread, monkeypatch
):
    from backend.memory import canonical_memory

    written: list[dict] = []

    def capture(consultant_id, **kwargs):
        written.append({"consultant_id": consultant_id, **kwargs})
        return "playbook-1"

    monkeypatch.setattr(canonical_memory, "write_procedural_candidate", capture)

    save_proposal()
    assert written == []

    # Il turno dopo: la conferma non riporta il metodo, lo ritrova dal thread.
    confirmed = manage_consultant_playbook.invoke({"operation": "confirm_save"})

    assert len(written) == 1
    assert written[0]["title"] == "Intervista in due passaggi"
    assert written[0]["applies_when"] == "Discovery di un processo poco documentato"
    assert written[0]["scope"] == "consultant"
    assert "playbook-1" in confirmed
    assert "candidate" in confirmed


def test_refusing_the_proposal_leaves_the_memory_alone(consulting_thread, monkeypatch):
    from backend.memory import canonical_memory

    monkeypatch.setattr(
        canonical_memory,
        "write_procedural_candidate",
        lambda *_a, **_k: pytest.fail("cancel_save ha comunque scritto"),
    )

    save_proposal()
    cancelled = manage_consultant_playbook.invoke({"operation": "cancel_save"})

    assert "cancelled" in cancelled
    assert manage_consultant_playbook.invoke({"operation": "confirm_save"}).count("not_found") == 1


def test_a_confirmation_is_not_executed_twice(consulting_thread, monkeypatch):
    from backend.memory import canonical_memory

    calls: list[str] = []
    monkeypatch.setattr(
        canonical_memory,
        "write_procedural_candidate",
        lambda *_a, **kwargs: (calls.append(kwargs["title"]), "playbook-1")[1],
    )

    save_proposal()
    manage_consultant_playbook.invoke({"operation": "confirm_save"})
    second = manage_consultant_playbook.invoke({"operation": "confirm_save"})

    assert len(calls) == 1
    assert "not_found" in second or "noop" in second


def test_confirming_nothing_says_so_instead_of_inventing_a_method(consulting_thread):
    result = manage_consultant_playbook.invoke({"operation": "confirm_save"})

    assert "not_found" in result
    assert "save_candidate" in result


def test_a_proposal_without_a_method_is_refused(consulting_thread):
    result = save_proposal(body="   ")

    assert "blocked" in result


def test_the_tool_prompt_forbids_registering_a_method_on_the_agents_initiative():
    description = manage_consultant_playbook.description

    assert "never your initiative" in description
    assert "confirm_save" in description
    assert "cancel_save" in description
    # Il prompt deve vietare esplicitamente l'annuncio anticipato.
    assert "Never say it is saved at this step." in description


def test_the_skill_states_who_decides_that_a_method_is_worth_keeping():
    assert "## Registering a Method" in MEMORY_GOVERNANCE
    assert "never because you noticed a pattern" in MEMORY_GOVERNANCE
    assert "confirm_save" in MEMORY_GOVERNANCE


def test_the_memory_taxonomy_is_not_presented_as_a_form_to_complete():
    assert "not a form to complete" in MEMORY_GOVERNANCE
    assert "an empty type is not a gap" in MEMORY_GOVERNANCE


@pytest.mark.parametrize(
    "rule",
    [
        "Do not answer \"what do you know about me\" by listing the categories",
        "only when it blocks the task at hand",
        "The absence of a stated preference is not a gap",
        "not open questions to raise unprompted",
    ],
)
def test_the_contract_the_agent_reads_carries_the_unknowns_rule(rule: str):
    # CONSULTANT-V2-02: la regola deve arrivare all'agente, non restare in un file
    # che nessun prompt include. Il contratto e' il testo che il modello legge.
    assert rule in CONSULTING_SUBGRAPH_CONTRACT
