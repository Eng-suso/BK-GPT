"""Cutover: manage_process_evidence scrive il KG sul canonical (Postgres + Neo4j).

Skip senza le tre DSN Postgres + NEO4J_PASSWORD in env.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

_NEEDED = (
    settings.canonical_migrator_url,
    settings.canonical_database_url,
    settings.canonical_worker_url,
    settings.neo4j_password,
)
if not all(_NEEDED):
    pytest.skip(
        "servono CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL / "
        "CANONICAL_WORKER_URL / NEO4J_PASSWORD",
        allow_module_level=True,
    )

from backend import workspace_database  # noqa: E402
from backend.memory.knowledge_graph import neo4j_store  # noqa: E402
from backend.toolsets.process_memory import manage_process_evidence  # noqa: E402
from backend.workers.graph_worker import drain_once  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


@pytest.fixture()
def workspace_process(monkeypatch):
    project_id = f"proj-mirror-{uuid.uuid4().hex[:8]}"
    process_id = f"proc-mirror-{uuid.uuid4().hex[:8]}"
    client_name = f"Acme Mirror {uuid.uuid4().hex[:6]}"

    monkeypatch.setattr(
        workspace_database, "get_project",
        lambda pid: {"id": pid, "name": "Progetto Mirror", "client": client_name}
        if pid == project_id else None,
    )
    monkeypatch.setattr(
        workspace_database, "get_process",
        lambda pid: {"id": pid, "name": "Order to Cash", "project_id": project_id}
        if pid == process_id else None,
    )
    yield project_id, process_id

    with MIGRATOR.begin() as conn:
        client_row = conn.execute(
            text("SELECT id FROM client WHERE workspace_id = :w"),
            {"w": f"client:{client_name.strip().lower().replace(' ', '-')}"},
        ).first()
    if client_row:
        client_id = str(client_row[0])
        with MIGRATOR.begin() as conn:
            conn.execute(text("DELETE FROM client WHERE id = :i"), {"i": client_id})
        neo4j_store.purge_client(client_id)


def test_manage_process_evidence_mirrors_to_canonical(workspace_process):
    project_id, process_id = workspace_process

    raw = manage_process_evidence.invoke(
        {
            "operation": "save_episode",
            "project_id": project_id,
            "process_id": process_id,
            "episode_type": "interview",
            "title": "Intervista Finance",
            "raw_content": "Finance emette fattura dopo la validazione ordine.",
            "entities": ["Finance", "Validazione ordine"],
            "claims": [
                {
                    "claim": "Finance emette fattura dopo validazione ordine.",
                    "process_area": "activity",
                    "source_name": "Intervista Finance",
                    "confidence": "high",
                    "status": "confirmed",
                }
            ],
            "relationships": [
                {
                    "source": "Finance",
                    "relation": "performs",
                    "target": "Validazione ordine",
                    "evidence": "Finance valida l'ordine.",
                    "confidence": 0.8,
                    "confirmed": True,
                }
            ],
        }
    )
    payload = json.loads(raw.split("\n", 1)[1])["payload"]
    mirror = payload["canonical_write"]
    assert mirror["mirrored"] is True
    assert mirror["counts"]["entities"] == 2
    assert mirror["counts"]["relationships"] == 1
    assert mirror["counts"]["claims"] == 1

    ids = _entity_ids(mirror)
    driver = neo4j_store.get_driver()
    # best-effort: se l'app gira, il suo worker in-process puo' aver gia' drenato
    edge = None
    for _ in range(12):
        drain_once()
        with driver.session() as neo:
            edge = neo.run(
                "MATCH (:Entity {entity_id:$s})-[r:PERFORMS]->(:Entity {entity_id:$t}) "
                "RETURN r.confidence AS c",
                s=ids["Finance"], t=ids["Validazione ordine"],
            ).single()
        if edge is not None:
            break
        time.sleep(0.5)
    assert edge is not None
    assert abs(edge["c"] - 0.8) < 1e-6


def _entity_ids(mirror_result: dict) -> dict:
    # il payload di mirror_evidence non porta gli id entita' per nome; li
    # recuperiamo dal canonical con lo scope restituito. kg_entity ha FORCE
    # RLS anche per delir_migrator: serve il contesto.
    scope = mirror_result["scope"]
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.current_consultant_id', :v, true)"),
            {"v": scope["consultant_id"]},
        )
        conn.execute(
            text("SELECT set_config('app.current_client_id', :v, true)"),
            {"v": scope["client_id"]},
        )
        rows = conn.execute(
            text(
                "SELECT canonical_name, id FROM kg_entity "
                "WHERE client_id = :cl AND consultant_id = :c"
            ),
            {"cl": scope["client_id"], "c": scope["consultant_id"]},
        ).all()
    return {row.canonical_name: str(row.id) for row in rows}
