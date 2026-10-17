"""C3, seconda parte: il ripiego con l'LLM per l'abbinamento affermazione -> attivita'."""

import pytest

from backend.settings import settings
from backend.simulation import claim_matching
from backend.simulation.claim_matching import Activity, ClaimMatching, match_with_llm, parse, proposals_from_llm, render
from backend.simulation.claims import SourceClaim
from tests.simulation.test_simulation_claims import BPMN, _source_with_claims

CLAIMS = [
    SourceClaim(id=11, statement="Il controllo dei documenti contabili richiede due giorni.", quote="due giorni", quote_verified=True, source_id="s1"),
    SourceClaim(id=12, statement="Il processo parte dalla mail del fornitore.", quote="", quote_verified=False, source_id="s1"),
]
ACTIVITIES = [Activity("T_check", "Verifica fattura"), Activity("T_pay", "Paga")]


@pytest.fixture(autouse=True)
def _empty_cache():
    claim_matching._cache.clear()
    yield
    claim_matching._cache.clear()


@pytest.fixture()
def fake_llm(monkeypatch):
    """Un gateway finto: ogni chiamata finisce nella lista e torna la risposta data."""
    import backend.llm as llm

    calls: list[dict] = []
    answer: dict = {"result": ClaimMatching(matches=[])}

    def run(**kwargs):
        from backend.llm import current_operation

        calls.append({**kwargs, "operation": current_operation()})
        if isinstance(answer["result"], Exception):
            raise answer["result"]
        return answer["result"]

    monkeypatch.setattr(llm, "run", run)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "delir_fake_llm", False)
    return calls, answer


def test_the_model_sees_numbered_activities_and_claims():
    text = render(ACTIVITIES, CLAIMS)

    assert "[A0] Verifica fattura" in text
    assert "[C11] Il controllo dei documenti contabili" in text


def test_only_ids_that_were_shown_are_kept():
    result = ClaimMatching.model_validate({"matches": [
        {"activity": "A0", "claims": ["C11", "C99", "C11", "x"]},
        {"activity": "A7", "claims": ["C12"]},
        {"activity": "A1", "claims": []},
    ]})

    assert parse(result, ACTIVITIES, CLAIMS) == {"T_check": [11]}


def test_a_match_becomes_a_proposal_marked_as_from_the_model():
    [proposal] = proposals_from_llm([11], CLAIMS, {"s1": "procedura.pdf"})

    assert (proposal.match, proposal.source_name, proposal.score) == ("llm", "procedura.pdf", 0.0)
    assert proposal.duration_hint is not None and proposal.duration_hint.seconds == 172_800


def test_the_call_opens_its_operation_and_is_cached(fake_llm):
    calls, answer = fake_llm
    answer["result"] = ClaimMatching.model_validate({"matches": [{"activity": "A0", "claims": ["C11"]}]})

    first = match_with_llm("proc-1", ACTIVITIES, CLAIMS)
    second = match_with_llm("proc-1", ACTIVITIES, CLAIMS)

    assert first == second == {"T_check": [11]}
    assert len(calls) == 1
    assert calls[0]["operation"].kind == "claim_matching"
    assert calls[0]["operation"].process_id == "proc-1"


def test_a_failure_of_the_model_leaves_only_the_lexical_proposals(fake_llm):
    calls, answer = fake_llm
    answer["result"] = RuntimeError("429")

    assert match_with_llm("proc-1", ACTIVITIES, CLAIMS) == {}
    assert len(calls) == 1


def test_without_a_key_the_model_is_never_called(fake_llm, monkeypatch):
    calls, _ = fake_llm
    monkeypatch.setattr(settings, "openai_api_key", "")

    assert match_with_llm("proc-1", ACTIVITIES, CLAIMS) == {}
    assert calls == []


def test_the_panel_gets_the_model_proposals_only_where_names_found_nothing(api_client, new_bpmn_model, fake_llm):
    calls, answer = fake_llm
    bpmn_model_id = new_bpmn_model()
    approve_id, invoice_id = _source_with_claims(bpmn_model_id, [
        "Approva ogni ordine il responsabile.",
        "I bonifici partono il venerdi' dalla tesoreria.",
    ])
    # Senza proposte lessicali restano Ricevi (A0) e Paga (A1).
    answer["result"] = ClaimMatching.model_validate({"matches": [{"activity": "A1", "claims": [f"C{invoice_id}"]}]})

    body = api_client.post(f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-claims", json={"current_bpmn_xml": BPMN}).json()

    by_id = {a["element_id"]: a["proposals"] for a in body["activities"]}
    assert [p["claim_id"] for p in by_id["T_approve"]] == [approve_id]
    assert by_id["T_approve"][0]["match"] == "lexical"
    assert [(p["claim_id"], p["match"]) for p in by_id["T_pay"]] == [(invoice_id, "llm")]
    assert by_id["T_receive"] == []
    # Al modello arrivano solo le attivita' senza proposte lessicali.
    asked = calls[0]["messages"][1].content
    assert "Approva" not in asked.split("Affermazioni:")[0]
    assert len(calls) == 1
