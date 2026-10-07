"""Il confine di lettura del gateway: chi puo' leggere cosa, e se il backend c'e'.

`ReadScope` e' lo scope iniettato in ogni query; `_scope_sql` lo traduce nel
filtro SQL che ogni lettura applica. Qui stanno anche le disponibilita' dei
backend (`graph_available`, ...) e la provenienza delle fonti, che servono sia
al retrieval sia al registro dei claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from backend.memory import mem0_client
from backend.memory.knowledge_graph import neo4j_store
from backend.settings import settings

_WORD = re.compile(r"[\wÀ-ÿ]{3,}")


def graph_available() -> bool:
    return bool(settings.canonical_database_url) and neo4j_store.is_enabled()


def memory_available() -> bool:
    return mem0_client.is_enabled()


def procedural_available() -> bool:
    return bool(settings.canonical_database_url)


@dataclass(frozen=True)
class ReadScope:
    """Il confine dell'evidenza leggibile in una chiamata di retrieval.

    `client_wide` e' la lettura senza confine interno (cutover, sweep, chat
    consulente): si dichiara, non si ottiene per dimenticanza.
    """

    client_id: str
    project_id: str | None = None
    process_id: str | None = None
    client_wide: bool = False

    @property
    def narrowed(self) -> bool:
        return not self.client_wide and bool(self.project_id or self.process_id)


def _scope_sql(scope: ReadScope) -> tuple[str, dict[str, Any]]:
    """Predicato SQL che tiene una riga dentro lo scope, piu' i suoi parametri.

    Una riga entra se e' del processo corrente, oppure se e' project-level
    (nessun processo) nel progetto corrente. Senza processo il confine e' il
    progetto.
    """
    if not scope.narrowed:
        return "", {}
    project = str(scope.project_id) if scope.project_id else None
    if scope.process_id:
        return (
            " AND (process_id = CAST(:sc_pr AS uuid) "
            "      OR (process_id IS NULL "
            "          AND project_id = CAST(:sc_pj AS uuid)))",
            {"sc_pr": str(scope.process_id), "sc_pj": project},
        )
    return " AND project_id = CAST(:sc_pj AS uuid)", {"sc_pj": project}


def _authorized_source_ids(session, scope: ReadScope) -> list[str] | None:
    """Le `kg_source` che questa lettura puo' vedere. `None` = nessun confine."""
    if not scope.narrowed:
        return None
    predicate, params = _scope_sql(scope)
    rows = session.execute(
        text("SELECT id FROM kg_source WHERE client_id = :cl" + predicate),
        {"cl": scope.client_id, **params},
    ).all()
    return [str(row.id) for row in rows]


def _source_provenance(
    session, client_id: str, source_ids: set[str]
) -> dict[str, tuple[str, str | None]]:
    """`source_id -> (titolo, process_id)`, per etichettare i chunk restituiti."""
    if not source_ids:
        return {}
    rows = session.execute(
        text(
            "SELECT id, title, process_id FROM kg_source "
            "WHERE client_id = :cl AND id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"cl": client_id, "ids": list(source_ids)},
    ).all()
    return {
        str(row.id): (row.title or "", str(row.process_id) if row.process_id else None)
        for row in rows
    }
