"""Invarianti del catalogo Postgres -> Neo4j (P0.5).

Parte pura (sempre): il lint B+ e la coerenza della mappa.
Parte DB (skip senza DSN): kg_entity rispetta la RLS come le altre tenant table.
"""

from __future__ import annotations

import uuid

import pytest

from backend.memory.knowledge_graph import catalog
from backend.settings import settings


def test_assert_projectable_blocks_pii():
    with pytest.raises(ValueError):
        catalog.assert_projectable({"entity_id": "x", "canonical_name": "Mario Rossi"})
    with pytest.raises(ValueError):
        catalog.assert_projectable({"statement": "il CFO di Acme ha approvato X"})
    # props pulite passano
    catalog.assert_projectable(
        {"entity_id": "x", "client_id": "c", "entity_type": "person", "role_type": "CFO"}
    )


def test_no_node_projects_a_forbidden_field():
    for node in catalog.NODES:
        projected = set(node.neo4j_props())
        assert not (projected & catalog.PII_FORBIDDEN_IN_NEO4J), node.label
        # ogni pg_only e' davvero fuori dalla proiezione
        assert not (set(node.pg_only) & projected), node.label


def test_entity_only_projects_whitelisted_attributes():
    entity = catalog.NODE_BY_TABLE["kg_entity"]
    assert entity.attr_whitelist <= catalog.ENTITY_ATTR_WHITELIST
    assert "attributes" in entity.pg_only
    assert "canonical_name" in entity.pg_only


def test_structural_edges_reference_known_node_labels():
    labels = {n.label for n in catalog.NODES}
    for edge in catalog.STRUCTURAL_EDGES:
        assert edge.from_node in labels, edge.label
        assert edge.to_node in labels, edge.label


def test_outbox_aggregate_types_cover_every_kg_table():
    kg_tables = {n.table for n in catalog.NODES if n.table.startswith("kg_")} | {
        e.table for e in catalog.EDGES
    }
    covered = {f"kg_{t}" for t in catalog.OUTBOX_AGGREGATE_TYPES}
    assert kg_tables <= covered, kg_tables - covered


# --- DB ---------------------------------------------------------------

if not settings.canonical_migrator_url or not settings.canonical_database_url:
    pytest.skip(
        "CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL non configurate",
        allow_module_level=True,
    )

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import DBAPIError, ProgrammingError  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)
APP = create_engine(settings.canonical_database_url, future=True)


def _ctx(conn, consultant_id, client_id=None):
    conn.execute(
        text("SELECT set_config('app.current_consultant_id', :v, true)"),
        {"v": str(consultant_id)},
    )
    conn.execute(
        text("SELECT set_config('app.current_client_id', :v, true)"),
        {"v": str(client_id) if client_id else ""},
    )


def test_kg_entity_is_tenant_isolated():
    a, b = uuid.uuid4(), uuid.uuid4()
    a_client, b_client = uuid.uuid4(), uuid.uuid4()
    with MIGRATOR.begin() as conn:
        for cid, name in ((a, "kga"), (b, "kgb")):
            conn.execute(
                text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,:n)"),
                {"i": cid, "e": f"{name}@t.local", "n": name},
            )
        _ctx(conn, a)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'A1')"),
            {"i": a_client, "c": a},
        )
        _ctx(conn, a, a_client)
        conn.execute(
            text(
                "INSERT INTO kg_entity (consultant_id, client_id, scope, entity_type, canonical_name) "
                "VALUES (:c, :cl, 'client', 'person', 'Mario Rossi')"
            ),
            {"c": a, "cl": a_client},
        )
        _ctx(conn, b)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'B1')"),
            {"i": b_client, "c": b},
        )
        _ctx(conn, b, b_client)
        conn.execute(
            text(
                "INSERT INTO kg_entity (consultant_id, client_id, scope, entity_type, canonical_name) "
                "VALUES (:c, :cl, 'client', 'person', 'Anna Bianchi')"
            ),
            {"c": b, "cl": b_client},
        )
    try:
        with APP.begin() as conn:
            _ctx(conn, a, a_client)
            names = conn.execute(text("SELECT canonical_name FROM kg_entity")).scalars().all()
        assert names == ["Mario Rossi"]

        with pytest.raises((DBAPIError, ProgrammingError)):
            with APP.begin() as conn:
                _ctx(conn, a, a_client)
                conn.execute(
                    text(
                        "INSERT INTO kg_entity (consultant_id, client_id, scope, entity_type, canonical_name) "
                        "VALUES (:c, :cl, 'client', 'system', 'SAP')"
                    ),
                    {"c": a, "cl": b_client},
                )
    finally:
        with MIGRATOR.begin() as conn:
            conn.execute(
                text("DELETE FROM consultant WHERE id = ANY(:ids)"), {"ids": [a, b]}
            )
