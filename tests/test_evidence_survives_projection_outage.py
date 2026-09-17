"""Tre interviste restano tre interviste anche con Neo4j e Mem0 giu'.

Postgres e' la source of truth; Neo4j e Mem0 sono proiezioni, e le proiezioni
sono asincrone. Se un guasto delle proiezioni potesse svuotare cio' che il
consulente vede, DeliR sarebbe epistemicamente cieco proprio nel momento in cui
ha piu' bisogno di ricordare: un processo con tre interviste sul tavolo
diventerebbe un processo senza evidenza, e il piano che ne esce un `Start ->
End`.

Il guasto qui e' simulato dove entra davvero — il registro dei claim proiettati
solleva — e si verifica che cio' che arriva all'estrattore sia lo stesso corpus,
voce per voce, con la sola aggiunta di una dichiarazione di degrado.
"""

from __future__ import annotations

import pytest

from backend.agents.process_synthesis import evidence_corpus
from backend.graphs.process import nodes


PROJECT_ID = "proj-1"
PROCESS_ID = "proc-1"

# Tre voci sullo stesso processo, come le registra il workspace.
INTERVIEWS = [
    {
        "id": "src-1",
        "name": "Intervista Francesca Neri",
        "type": "interview_transcript",
        "process_id": PROCESS_ID,
        "content": "Acquisti crea e invia l'ordine al fornitore. "
                   "L'autorizzazione del responsabile e' sempre richiesta.",
        "summary": "Ciclo passivo, reparto Acquisti",
        "participants": ["Francesca Neri"],
        "has_content": True,
    },
    {
        "id": "src-2",
        "name": "Intervista Paolo Ricci",
        "type": "interview_transcript",
        "process_id": PROCESS_ID,
        "content": "Per importi piccoli l'approvazione puo' non essere formalizzata.",
        "summary": "Ciclo passivo, reparto Produzione",
        "participants": ["Paolo Ricci"],
        "has_content": True,
    },
    {
        "id": "src-3",
        "name": "Intervista Marco Villa",
        "type": "interview_transcript",
        "process_id": PROCESS_ID,
        "content": "Quando serve con urgenza il reparto contatta direttamente il fornitore.",
        "summary": "Urgenze",
        "participants": ["Marco Villa"],
        "has_content": True,
    },
]

PROJECTED_CLAIMS = [
    {
        "claim": "Acquisti crea e invia l'ordine al fornitore",
        "attributed_to": "Francesca Neri",
        "source_name": "Intervista Francesca Neri",
        "epistemic_status": "reported",
    }
]


@pytest.fixture()
def workspace(monkeypatch):
    """Il registro operativo risponde; le proiezioni le decide il test."""
    monkeypatch.setattr(
        nodes, "_authoritative_process_sources", lambda project_id, process_id: list(INTERVIEWS)
    )
    return monkeypatch


def _ledger(monkeypatch, *, claim_ledger) -> dict:
    import backend.toolsets.process_memory as process_memory

    monkeypatch.setattr(process_memory, "process_claim_ledger", claim_ledger)
    return nodes.load_evidence_ledger(PROJECT_ID, PROCESS_ID)


def _projections_up(project_id, process_id):
    return {"status": "ok", "claims": list(PROJECTED_CLAIMS), "count": len(PROJECTED_CLAIMS)}


def _projections_down(project_id, process_id):
    raise ConnectionError("Neo4j irraggiungibile / Mem0 in rate limit")


def test_three_interviews_are_still_three_when_the_projections_are_down(workspace):
    ledger = _ledger(workspace, claim_ledger=_projections_down)

    assert nodes.evidence_count(ledger) == 3, (
        "le fonti stanno in Postgres: un guasto delle proiezioni non puo' azzerarle"
    )
    assert ledger["status"] == "ok"
    assert ledger["claim_status"] == "error"
    assert [item["id"] for item in ledger["sources"]] == ["src-1", "src-2", "src-3"]


def test_the_corpus_carries_every_voice_with_or_without_the_projections(workspace):
    up = evidence_corpus(_ledger(workspace, claim_ledger=_projections_up))
    down = evidence_corpus(_ledger(workspace, claim_ledger=_projections_down))

    for source in INTERVIEWS:
        assert source["content"] in down, f"{source['name']} sparita dal corpus"
        assert source["content"] in up

    # La sezione autoritativa e' la stessa parola per parola: cambia solo cio'
    # che le proiezioni aggiungevano, e la loro assenza viene dichiarata invece
    # che taciuta.
    assert _sources_section(down) == _sources_section(up)
    assert "non concludere che l'evidenza sia assente" in down
    assert "Francesca Neri" in up.split("REGISTRO DEI CLAIM PROIETTATI")[1]


def _sources_section(corpus: str) -> str:
    """Il corpus fino a dove finiscono le fonti agli atti."""
    for marker in ("REGISTRO DEI CLAIM PROIETTATI", "La proiezione dei claim non e'"):
        head, sep, _ = corpus.partition(marker)
        if sep:
            return head.rstrip()
    return corpus.rstrip()


def test_the_plan_is_built_on_the_sources_even_with_the_projections_down(workspace, monkeypatch):
    """Il piano non deve mai uscire come `no_evidence` mentre le fonti ci sono."""
    import backend.workspace_database as workspace_database
    from backend.agents import process_synthesis

    monkeypatch.setattr(
        workspace_database,
        "get_process",
        lambda process_id: {
            "id": PROCESS_ID,
            "name": "Ciclo passivo",
            "project_id": PROJECT_ID,
            "bpmn_model_id": "bpmn-1",
        },
    )
    # L'esito qui e' un fallimento per costruzione (l'estrattore rifiuta), e la
    # via del fallimento rilegge lo snapshot dal workspace: non e' quello che il
    # test verifica, e senza un DB dietro sarebbe l'unica cosa che fallisce.
    monkeypatch.setattr(process_synthesis, "build_process_snapshot", lambda process_id: None)

    # Una chiamata per fonte, in parallelo: si raccoglie cio' che ognuna riceve,
    # non l'ultima che scrive.
    seen: list[tuple[str, str]] = []

    def _extractor(title, source_text, **kwargs):
        seen.append((title, source_text))
        raise RuntimeError("stop: al test interessa cosa riceve l'estrattore, non cosa risponde")

    monkeypatch.setattr(process_synthesis, "build_process_understanding", _extractor)

    import backend.toolsets.process_memory as process_memory

    monkeypatch.setattr(process_memory, "process_claim_ledger", _projections_down)

    outcome = process_synthesis.synthesize_process_plan(PROCESS_ID)

    # Con le proiezioni giu' l'estrazione non produce niente, e questo e' un
    # guasto dichiarato - non un processo senza evidenza. La differenza e' tutta
    # qui: `synthesis_failed` si riprova, `no_evidence` disegna `Start -> End`.
    assert outcome.action == "synthesis_failed"
    assert seen, "l'estrattore non e' stato chiamato: le fonti non sono arrivate fin li'"
    assert {title for title, _ in seen} == {"Ciclo passivo"}

    received = "\n".join(corpus for _, corpus in seen)
    for source in INTERVIEWS:
        assert source["content"] in received, (
            "l'estrattore ha ricevuto un corpus senza le interviste: e' cosi' che "
            "tre voci diventano Start -> End"
        )
