"""WS-05: un'intervista raccolta in chat finisce fra le fonti del progetto.

Prima esistevano due mondi separati. Le interviste salvate dalla chat processo
andavano nella memoria episodica: l'agente le citava, ma il consulente che
apriva il pannello Fonti non le trovava. Nel pannello ci arrivavano solo le
evidenze salvate con `save_process_evidence`, e per giunta con una nota che era
un JSON - `confidence`, `graph_rag_indexed` - stampato al posto di una frase.

Qui si verificano le tre cose che rendono la fonte utile: che esista, che sia
legata al processo (quindi apribile e navigabile dal pannello), e che quello che
il consulente legge sia scritto per lui.
"""

from __future__ import annotations

import json
import uuid

import pytest

from backend.settings import settings
from backend.toolsets.process_memory import _evidence_note
from backend.workspace_defaults import (
    DEFAULT_SOURCE_TYPE,
    evidence_type_label,
)


# --- vocabolario: senza database -------------------------------------------

def test_the_raw_evidence_type_becomes_a_word_the_consultant_reads():
    assert evidence_type_label("interview") == "Intervista"
    assert evidence_type_label("interview_notes") == "Intervista"
    assert evidence_type_label("system_export") == "Export di sistema"
    assert evidence_type_label("SYSTEM_EXPORT") == "Export di sistema"


def test_an_unknown_type_is_kept_instead_of_flattened():
    """Chi salva sa cos'e' quella fonte: "Verbale CdA" vale piu' di "Fonte"."""
    assert evidence_type_label("  Verbale   CdA ") == "Verbale CdA"
    assert evidence_type_label("") == DEFAULT_SOURCE_TYPE
    assert evidence_type_label(None) == DEFAULT_SOURCE_TYPE


def test_the_note_is_a_sentence_and_falls_back_to_the_source_text():
    assert _evidence_note("  Sintesi   breve ", "testo originale") == "Sintesi breve"
    assert _evidence_note("", "Il fabbisogno nasce in reparto.") == "Il fabbisogno nasce in reparto."
    assert _evidence_note("", "") == ""


def test_a_long_note_is_cut_instead_of_flooding_the_panel():
    note = _evidence_note("", "parola " * 200, limit=40)

    assert len(note) == 40
    assert note.endswith("…")


# --- comportamento reale: serve il database operativo -----------------------

pytestmark_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)

INTERVIEW_TITLE = "Intervista Operations 2026-09-08"
INTERVIEW_TEXT = (
    "Il fabbisogno nasce in reparto, l'ordine lo emette Acquisti, "
    "la fattura la verifica Amministrazione."
)


@pytest.fixture()
def tenant():
    """Isola il test in un tenant proprio."""
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    try:
        yield
    finally:
        reset_current_tenant_id(token)


@pytest.fixture()
def process(tenant):
    """Un progetto con un processo registrato, come dopo lo STEP 2."""
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(client_id=client["id"], name=f"Acquisti {uuid.uuid4().hex[:6]}")
    record = wd.create_process(project_id=project["id"], name="Gestione acquisto materiali")
    return {"project_id": project["id"], "process_id": record["id"]}


def _sources(project_id: str) -> list[dict]:
    from backend import workspace_database as wd

    return wd.list_project_sources(project_id)


@pytestmark_db
def test_a_saved_interview_shows_up_among_the_project_sources(process, monkeypatch):
    from backend.memory.episodic import episodic_store
    from backend.toolsets.process_memory import manage_process_evidence

    # La memoria episodica ha una sua infrastruttura: qui si verifica il ponte
    # verso il workspace, non il salvataggio dell'episodio.
    monkeypatch.setattr(
        episodic_store, "save_episode_memory", lambda **kwargs: {"status": "saved"}
    )

    manage_process_evidence.invoke(
        {
            "operation": "save_interview",
            "project_id": process["project_id"],
            "process_id": process["process_id"],
            "title": INTERVIEW_TITLE,
            "raw_content": INTERVIEW_TEXT,
            "summary": "Il fabbisogno nasce in reparto; la fattura la verifica Amministrazione.",
        }
    )

    sources = _sources(process["project_id"])
    saved = [source for source in sources if source["name"] == INTERVIEW_TITLE]
    assert len(saved) == 1
    # Legata al processo: e' cio' che la rende apribile e navigabile dal pannello.
    assert saved[0]["process_id"] == process["process_id"]
    assert saved[0]["type"] == "Intervista"
    assert saved[0]["meta"].startswith("Il fabbisogno nasce in reparto")


@pytestmark_db
def test_saving_the_same_interview_twice_does_not_duplicate_the_source(process, monkeypatch):
    from backend.memory.episodic import episodic_store
    from backend.toolsets.process_memory import manage_process_evidence

    monkeypatch.setattr(
        episodic_store, "save_episode_memory", lambda **kwargs: {"status": "saved"}
    )
    payload = {
        "operation": "save_interview",
        "project_id": process["project_id"],
        "process_id": process["process_id"],
        "title": INTERVIEW_TITLE,
        "raw_content": INTERVIEW_TEXT,
        "summary": "Prima stesura.",
    }

    manage_process_evidence.invoke(payload)
    manage_process_evidence.invoke({**payload, "summary": "Riformulata dal consulente."})

    saved = [s for s in _sources(process["project_id"]) if s["name"] == INTERVIEW_TITLE]
    assert len(saved) == 1
    # La fonte esistente non viene riscritta: il record dice quando l'evidenza e'
    # entrata nel progetto.
    assert saved[0]["meta"] == "Prima stesura."


@pytestmark_db
def test_an_episode_without_a_title_registers_no_source(process, monkeypatch):
    """Una fonte senza nome nel pannello e' una riga vuota da aprire."""
    from backend.memory.episodic import episodic_store
    from backend.toolsets.process_memory import manage_process_evidence

    monkeypatch.setattr(
        episodic_store, "save_episode_memory", lambda **kwargs: {"status": "saved"}
    )

    manage_process_evidence.invoke(
        {
            "operation": "save_episode",
            "project_id": process["project_id"],
            "process_id": process["process_id"],
            "title": "   ",
            "raw_content": INTERVIEW_TEXT,
        }
    )

    assert _sources(process["project_id"]) == []


@pytestmark_db
def test_the_evidence_tool_writes_a_note_not_a_json_blob(process):
    """Il pannello mostra `meta` cosi' com'e': la' dentro ci va una frase."""
    from backend.graphs.process.tools import save_process_evidence

    result = json.loads(
        save_process_evidence.invoke(
            {
                "process_id": process["process_id"],
                "name": "Export ordini 2026",
                "evidence_type": "system_export",
                "summary": "Ordini di acquisto dell'ultimo trimestre.",
                "provenance_note": "estratto da SAP il 2026-09-08",
                "confidence": "high",
            }
        ).split("\n", 1)[1]
    )

    source = result["payload"]["source"]
    assert source["type"] == "Export di sistema"
    assert source["meta"] == (
        "Ordini di acquisto dell'ultimo trimestre. (estratto da SAP il 2026-09-08)"
    )
    assert "confidence" not in source["meta"]
    assert "graph_rag_indexed" not in source["meta"]
    # Il dettaglio strutturato non sparisce: resta nel payload, che e' materiale
    # di lavoro dell'agente e non prosa per il consulente.
    assert result["payload"]["confidence"] == "high"


@pytestmark_db
def test_the_same_evidence_saved_twice_is_reported_as_existing(process):
    from backend.graphs.process.tools import save_process_evidence

    payload = {
        "process_id": process["process_id"],
        "name": "Export ordini 2026",
        "evidence_type": "system_export",
        "summary": "Ordini di acquisto dell'ultimo trimestre.",
    }
    first = json.loads(save_process_evidence.invoke(payload).split("\n", 1)[1])
    second = json.loads(save_process_evidence.invoke(payload).split("\n", 1)[1])

    assert first["status"] == "created"
    assert second["status"] == "exists"
    assert second["entity_id"] == first["entity_id"]
