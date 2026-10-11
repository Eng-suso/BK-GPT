"""SIM-07 (C3): le affermazioni dei file del cliente come fonte dei parametri.

Gate G5: l'abbinamento e' lessicale e proposto; diventa fonte ``declared`` solo
dopo la conferma del consulente; una durata citata resta un riferimento.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.claims import SourceClaim, duration_hint, propose
from backend.workspace_database import get_bpmn_model, get_process
from backend.workspace_storage import WorkspaceSource, WorkspaceSourceClaim, workspace_connection

BPMN = (Path(__file__).resolve().parents[2] / "ops" / "prosimos" / "spike" / "p2p_mini.bpmn").read_text(encoding="utf-8")


def _claim(claim_id: int, statement: str, quote: str = "", verified: bool = True) -> SourceClaim:
    return SourceClaim(id=claim_id, statement=statement, quote=quote or statement, quote_verified=verified, source_id="s1")


def test_an_activity_is_matched_by_the_root_of_its_words():
    claims = [
        _claim(1, "Le richieste vengono approvate dal responsabile entro circa 2 giorni."),
        _claim(2, "Il magazzino riceve la merce il lunedì."),
    ]
    [proposal] = propose("Approva richiesta", claims, {"s1": "procedura.pdf"})
    assert proposal.claim_id == 1
    assert proposal.source_name == "procedura.pdf"
    assert proposal.score == 1.0
    assert proposal.duration_hint is not None and proposal.duration_hint.seconds == 2 * 86_400


def test_a_long_name_needs_at_least_half_of_its_words():
    claims = [_claim(1, "La fattura viene registrata."), _claim(2, "La fattura del fornitore viene verificata e registrata.")]
    proposals = propose("Verifica fattura fornitore", claims, {})
    assert [p.claim_id for p in proposals] == [2]


def test_at_most_three_proposals_best_first_and_verified_quotes_first():
    claims = [_claim(i, "Approva l'ordine.", verified=i != 2) for i in range(1, 6)]
    proposals = propose("Approva", claims, {})
    assert [p.claim_id for p in proposals] == [1, 3, 4]


def test_nothing_is_proposed_for_words_too_short_or_empty():
    assert propose("Fai", [_claim(1, "Fai questo")], {}) == []


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("ci vuole mezz'ora", 1800), ("circa tre ore", 3 * 3600), ("15 min per pratica", 900),
     ("1,5 ore", 5400), ("entro due settimane", 2 * 604_800), ("nessuna durata qui", None)],
)
def test_a_quoted_duration_is_read_as_a_reference(text, seconds):
    hint = duration_hint(text)
    assert (hint.seconds if hint else None) == seconds


def _source_with_claims(bpmn_model_id: str, statements: list[str]) -> list[int]:
    project_id = get_process(get_bpmn_model(bpmn_model_id)["process_id"])["project_id"]
    source_id = f"src-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).isoformat()
    with workspace_connection() as session:
        session.add(WorkspaceSource(id=source_id, tenant_id="local", project_id=project_id,
                                    name="procedura-acquisti.pdf", type="document", meta="PDF"))
        session.flush()
        rows = [WorkspaceSourceClaim(tenant_id="local", source_id=source_id, ordinal=i, statement=text,
                                     segment_ordinal=0, anchor_ref="§1", quote=text, quote_verified=True,
                                     content_hash="h", prompt_version="v", extracted_at=now)
                for i, text in enumerate(statements)]
        session.add_all(rows)
        session.flush()
        return [row.id for row in rows]


def test_the_panel_receives_the_proposals_of_each_activity(api_client, new_bpmn_model):
    bpmn_model_id = new_bpmn_model()
    [claim_id] = _source_with_claims(bpmn_model_id, ["Approva ogni ordine il responsabile, in circa 30 minuti."])

    response = api_client.post(f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-claims", json={"current_bpmn_xml": BPMN})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sources"] == 1
    approve = next(a for a in body["activities"] if a["element_id"] == "T_approve")
    assert approve["proposals"][0]["claim_id"] == claim_id
    assert approve["proposals"][0]["source_name"] == "procedura-acquisti.pdf"
    assert approve["proposals"][0]["duration_hint"] == {"text": "30 minuti", "seconds": 1800.0}
    assert next(a for a in body["activities"] if a["element_id"] == "T_pay")["proposals"] == []


def _run_request(claims: list[dict]) -> dict:
    return {**CreateSimulationRunRequest(
        total_cases=10,
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600},
            {"element_id": "T_approve", "mean_seconds": 1800, "claims": claims},
            {"element_id": "T_pay", "mean_seconds": 600},
        ],
    ).model_dump(mode="json"), "current_bpmn_xml": BPMN}


def test_a_confirmed_claim_becomes_the_declared_source_of_the_duration(api_client, new_bpmn_model, fake_engine):
    bpmn_model_id = new_bpmn_model()
    [claim_id] = _source_with_claims(bpmn_model_id, ["Approva ogni ordine il responsabile."])

    created = api_client.post(f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-runs",
                              json=_run_request([{"claim_id": claim_id, "label": "procedura-acquisti.pdf"}]))
    assert created.status_code == 200, created.text

    model = api_client.get(f"/v1/workspace/simulation-runs/{created.json()['id']}/model").json()["model"]
    approve = next(a for a in model["activities"] if a["element_id"] == "T_approve")
    provenance = approve["assignments"][0]["provenance"]
    assert provenance["origin"] == "declared"
    assert provenance["sources"] == [{"kind": "claim", "id": str(claim_id), "label": "procedura-acquisti.pdf"}]
    # Il valore resta quello del pannello: la fonte non lo sostituisce.
    assert approve["assignments"][0]["duration"]["mean"] == 1800.0


def test_a_claim_from_another_project_is_refused(api_client, new_bpmn_model, fake_engine):
    [elsewhere] = _source_with_claims(new_bpmn_model(), ["Approva ogni ordine il responsabile."])
    response = api_client.post(f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
                               json=_run_request([{"claim_id": elsewhere, "label": "procedura-acquisti.pdf"}]))
    assert response.status_code == 400
    assert fake_engine == []


def test_a_claim_that_no_longer_exists_is_a_400_with_the_reason(api_client, new_bpmn_model, fake_engine):
    response = api_client.post(f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs",
                               json=_run_request([{"claim_id": 999_999_999, "label": "sparito.pdf"}]))
    assert response.status_code == 400
    assert "non esiste più" in response.json()["error"]["message"]
    assert fake_engine == []
