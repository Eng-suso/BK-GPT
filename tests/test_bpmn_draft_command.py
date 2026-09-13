"""«Genera BPMN» come comando: veloce, deterministico, e mai una domanda.

Il disegno di una bozza dal piano passava da una catena agentica di dodici-venti
chiamate al modello e poteva finire in `waiting_for_user`. Qui si verificano le
proprieta' che quella catena non poteva avere:

A. **snapshot caldo** - con il piano gia' materializzato non si risintetizza
   niente, non si chiama nessun modello, e il BPMN ha le attivita' del piano;
B. **knowledge graph giu'** - stesso risultato: Neo4j e' una proiezione;
C. **Mem0 in rate limit** - stesso risultato, per lo stesso motivo;
D. **lacune aperte** - la bozza si genera lo stesso e le lacune escono accanto
   al disegno, non al posto del disegno;
E. **l'evidenza cambia** - una quarta intervista rende il piano non corrente, e
   la generazione successiva lavora sulla versione nuova;
G. **regressione di tempo** - il percorso caldo resta dentro il budget;
H. **regressione Esaote** - le tre interviste producono attivita' vere, non
   start -> end.

Servono la DSN workspace e quelle canonical (`cd ops && docker compose up -d`).
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET

import pytest

from backend.settings import settings

if not all((settings.workspace_database_url, settings.canonical_database_url)):
    pytest.skip(
        "servono WORKSPACE_DATABASE_URL e le DSN canonical",
        allow_module_level=True,
    )

from backend import workspace_database as wd  # noqa: E402
from backend.agents.process_snapshot import build_process_snapshot  # noqa: E402
from backend.workspace_services.bpmn_draft import generate_bpmn_draft  # noqa: E402

from tests.test_process_canvas_handoff_e2e import (  # noqa: E402
    INTERVIEWS,
    OPEN_GAP,
    _bind_process_chat,
    _prepare_plan,
    _save_interviews,
    empty_process,  # noqa: F401 - fixture
)


BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

# Il budget del percorso caldo. Non e' l'SLO utente (P95 < 5s dal click, che
# include rete, router e rendering): e' il tetto del lavoro di backend, e serve
# a far fallire una regressione prima che arrivi in produzione.
WARM_PATH_BUDGET_MS = 2_500

# Fasi che devono restare a zero sul percorso caldo. Se una di queste si accende,
# il critical path ha ripreso a fare lavoro che non gli appartiene.
COLD_PHASES = ("plan_synthesis_ms",)


@pytest.fixture(autouse=True)
def _no_live_model(monkeypatch):
    """Il comando non deve chiamare nessun modello: qui non c'e' chiave."""
    monkeypatch.setattr(settings, "openai_api_key", None)


def _flow_nodes(xml: str) -> list[ET.Element]:
    root = ET.fromstring(xml)
    process = root.find(f"{{{BPMN_NS}}}process")
    assert process is not None, "il BPMN generato non contiene un processo"
    return list(process)


def _tags(xml: str) -> list[str]:
    return [element.tag.split("}")[-1] for element in _flow_nodes(xml)]


def _labels(xml: str) -> list[str]:
    return [
        str(element.attrib.get("name") or "").casefold()
        for element in _flow_nodes(xml)
        if element.attrib.get("name")
    ]


@pytest.fixture()
def process_with_plan(empty_process):  # noqa: F811 - fixture di modulo
    """Tre interviste agli atti e il piano gia' materializzato."""
    _save_interviews(empty_process)
    _prepare_plan(empty_process)
    return empty_process


def test_warm_snapshot_drafts_without_touching_the_model(process_with_plan):
    """A. Piano pronto: nessuna sintesi, nessuna chiamata, un BPMN con dentro il lavoro."""
    with _bind_process_chat(process_with_plan["project_id"], process_with_plan["process_id"]):
        result = generate_bpmn_draft(process_with_plan["process_id"])

    assert result.status == "drafted", result.reason
    assert result.metrics["llm_calls"] == 0
    assert result.metrics["tool_calls"] == 0
    for phase in COLD_PHASES:
        assert result.metrics[phase] == 0, f"{phase} non appartiene al percorso caldo"

    tags = _tags(result.xml or "")
    assert tags.count("task") + tags.count("userTask") + tags.count("manualTask") >= 3
    assert "startEvent" in tags and "endEvent" in tags


def test_the_draft_is_read_back_from_the_database(process_with_plan):
    """Nessuna scrittura si dichiara senza rilettura, nemmeno la piu' veloce."""
    with _bind_process_chat(process_with_plan["project_id"], process_with_plan["process_id"]):
        result = generate_bpmn_draft(process_with_plan["process_id"])

    saved = wd.get_bpmn_model(process_with_plan["bpmn_model_id"])
    assert saved is not None and saved["xml"] == result.xml
    assert result.metrics["read_after_write_ms"] >= 0

    versions = wd.list_bpmn_versions(process_with_plan["bpmn_model_id"])
    assert any(item["source"] == "bpmn_draft_command" for item in versions)


def test_the_draft_survives_a_knowledge_graph_outage(process_with_plan, monkeypatch):
    """B. Neo4j e' una proiezione: se e' giu', il disegno esce lo stesso."""
    from backend.memory import gateway

    def _explode(*args, **kwargs):
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(gateway, "graph_retrieve", _explode)
    monkeypatch.setattr(gateway, "claim_ledger", _explode)

    with _bind_process_chat(process_with_plan["project_id"], process_with_plan["process_id"]):
        result = generate_bpmn_draft(process_with_plan["process_id"])

    assert result.status == "drafted", result.reason
    assert len(_tags(result.xml or "")) > 2


def test_the_draft_survives_a_mem0_rate_limit(process_with_plan, monkeypatch):
    """C. Mem0 in 429 non e' una ragione per non disegnare."""
    from backend.memory.semantic import semantic_store

    def _rate_limited(*args, **kwargs):
        raise RuntimeError("429 Too Many Requests")

    for name in ("search_bpmn_preferences", "search_memories"):
        if hasattr(semantic_store, name):
            monkeypatch.setattr(semantic_store, name, _rate_limited)

    with _bind_process_chat(process_with_plan["project_id"], process_with_plan["process_id"]):
        result = generate_bpmn_draft(process_with_plan["process_id"])

    assert result.status == "drafted", result.reason


def test_open_gaps_do_not_stop_the_draft(process_with_plan):
    """D. Una lacuna aperta esce accanto al disegno, non al posto del disegno."""
    snapshot = build_process_snapshot(process_with_plan["process_id"])
    assert snapshot is not None and snapshot.blocking_questions, (
        "il piano di prova deve avere una lacuna bloccante, altrimenti il test non prova niente"
    )

    with _bind_process_chat(process_with_plan["project_id"], process_with_plan["process_id"]):
        result = generate_bpmn_draft(process_with_plan["process_id"])

    assert result.status == "drafted"
    assert any(OPEN_GAP in item for item in result.pending_verification)


def test_a_new_interview_moves_the_draft_to_the_new_version(process_with_plan):
    """E. L'evidenza cambia: la generazione successiva lavora sulla versione nuova."""
    from backend.toolsets.process_memory import manage_process_evidence

    before = build_process_snapshot(process_with_plan["process_id"])
    assert before is not None

    with _bind_process_chat(process_with_plan["project_id"], process_with_plan["process_id"]):
        manage_process_evidence.invoke(
            {
                "operation": "save_interview",
                "project_id": process_with_plan["project_id"],
                "process_id": process_with_plan["process_id"],
                "title": "Intervista Marco Gallo - Amministrazione",
                "raw_content": (
                    "Marco Gallo, Amministrazione. Ricevo la fattura del fornitore e la "
                    "confronto con l'ordine prima di autorizzare il pagamento."
                ),
                "summary": "Verifica fattura",
                "participants": ["Marco Gallo"],
                "entities": ["Marco Gallo", "Amministrazione", "Fattura"],
            }
        )

    after = build_process_snapshot(process_with_plan["process_id"])
    assert after is not None
    assert after.snapshot_id != before.snapshot_id
    assert not after.plan_is_current, "una fonte in piu' rende il piano non corrente"

    with _bind_process_chat(process_with_plan["project_id"], process_with_plan["process_id"]):
        result = generate_bpmn_draft(
            process_with_plan["process_id"], synthesize_missing_plan=False
        )

    # Il piano e' indietro, ma esiste: il comando disegna quello che c'e' e
    # dichiara la versione, invece di fermarsi. Risintetizzarlo e' lavoro della
    # materializzazione, non del disegno.
    assert result.status == "drafted"
    assert result.metrics["process_snapshot_version"] == after.version
    assert result.metrics["llm_calls"] == 0


def test_a_process_without_plan_and_without_evidence_fails_technically(empty_process):  # noqa: F811
    """Un fallimento si dichiara per quello che e', e non si traveste da lacuna."""
    with _bind_process_chat(empty_process["project_id"], empty_process["process_id"]):
        result = generate_bpmn_draft(empty_process["process_id"])

    assert result.status == "failed"
    assert result.issues
    assert result.metrics["llm_calls"] == 0


def test_the_warm_path_stays_inside_its_time_budget(process_with_plan):
    """G. La regressione di tempo si vede qui, non in produzione."""
    with _bind_process_chat(process_with_plan["project_id"], process_with_plan["process_id"]):
        result = generate_bpmn_draft(process_with_plan["process_id"])

    assert result.status == "drafted"
    assert result.metrics["total_ms"] <= WARM_PATH_BUDGET_MS, (
        f"percorso caldo fuori budget: {result.metrics}"
    )
    # Le fasi devono sommare a qualcosa di vicino al totale: se una fase non e'
    # misurata, «dove se ne vanno i secondi» torna a essere un'opinione.
    measured = sum(
        result.metrics[key]
        for key in (
            "load_snapshot_ms",
            "semantic_generation_ms",
            "validation_ms",
            "serialization_di_ms",
            "persistence_ms",
            "read_after_write_ms",
        )
    )
    assert measured <= result.metrics["total_ms"]
    assert measured >= result.metrics["total_ms"] * 0.5


def test_the_three_interviews_produce_real_activities(process_with_plan):
    """H. Regressione Esaote: le tre voci diventano lavoro, non start -> end."""
    with _bind_process_chat(process_with_plan["project_id"], process_with_plan["process_id"]):
        result = generate_bpmn_draft(process_with_plan["process_id"])

    assert result.status == "drafted"
    labels = " | ".join(_labels(result.xml or ""))
    assert "richiesta" in labels
    assert "ordine" in labels
    # Il passaggio di Paolo: senza una sua attivita', Manutenzione sparisce
    # dall'AS-IS e resta il processo di due reparti su tre.
    assert "fornitore" in labels
    tags = _tags(result.xml or "")
    assert tags.count("exclusiveGateway") + tags.count("inclusiveGateway") >= 1, (
        "la decisione sulla soglia deve diventare un gateway"
    )
    assert len(INTERVIEWS) == 3
