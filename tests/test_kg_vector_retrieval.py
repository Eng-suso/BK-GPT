"""P3 — retrieval ibrido su kg_chunk: arm lessicale (`ts_rank_cd`) + arm
vettoriale (cosine), fusi RRF nel gateway.

Skip senza le DSN canonical + NEO4J_PASSWORD + OPENAI_API_KEY (serve
l'embedder reale per l'arm vettoriale / la fusione).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

_NEEDED = (
    settings.canonical_migrator_url,
    settings.canonical_database_url,
    settings.canonical_worker_url,
    settings.neo4j_password,
    settings.openai_api_key,
)
if not all(_NEEDED):
    pytest.skip(
        "servono le DSN canonical + NEO4J_PASSWORD + OPENAI_API_KEY",
        allow_module_level=True,
    )

from backend.memory import gateway  # noqa: E402
from backend.memory.knowledge_graph import canonical, neo4j_store  # noqa: E402
from backend.workers.graph_worker import drain_once  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


def _rels(result: dict) -> set:
    return {(m["source"], m["relation"], m["target"]) for m in result["matches"]}


def _ctx(conn, cid, clid=None):
    conn.execute(
        text("SELECT set_config('app.current_consultant_id', :v, true)"), {"v": str(cid)}
    )
    conn.execute(
        text("SELECT set_config('app.current_client_id', :v, true)"),
        {"v": str(clid) if clid else ""},
    )


@pytest.fixture()
def scope():
    c, cl, pj, pr = (uuid.uuid4() for _ in range(4))
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,'v')"),
            {"i": c, "e": f"{c}@t.local"},
        )
        _ctx(conn, c)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'AcmeVec')"),
            {"i": cl, "c": c},
        )
        conn.execute(
            text("INSERT INTO project (id, client_id, consultant_id, name) VALUES (:i,:cl,:c,'P')"),
            {"i": pj, "cl": cl, "c": c},
        )
        conn.execute(
            text(
                "INSERT INTO process (id, project_id, client_id, consultant_id, name) "
                "VALUES (:i,:p,:cl,:c,'Order to Cash')"
            ),
            {"i": pr, "p": pj, "cl": cl, "c": c},
        )
    yield {"consultant": str(c), "client": str(cl), "project": str(pj), "process": str(pr)}
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": c})
    neo4j_store.purge_client(str(cl))


def test_source_text_becomes_chunks_and_provenance(scope):
    counts = canonical.write_evidence(
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        project_id=scope["project"],
        process_id=scope["process"],
        process_name="Order to Cash",
        entities=["Ufficio crediti"],
        source_title="Intervista Finance",
        source_text=(
            "L'ufficio crediti blocca l'ordine quando il cliente supera il fido. "
            "Il rilascio richiede l'ok del direttore finanziario entro 48 ore, "
            "altrimenti l'ordine decade e va reinserito da capo."
        ),
    )
    assert counts["chunks"] >= 1

    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        src = conn.execute(
            text("SELECT id FROM kg_source WHERE client_id = :cl"), {"cl": scope["client"]}
        ).one()
        chunk = conn.execute(
            text(
                "SELECT embedding IS NOT NULL AS has_vec, embed_dim "
                "FROM kg_chunk WHERE source_id = :s ORDER BY ordinal LIMIT 1"
            ),
            {"s": src.id},
        ).one()
        assert chunk.has_vec is True
        assert chunk.embed_dim == 1536

        ent = conn.execute(
            text(
                "SELECT source_ids FROM kg_entity "
                "WHERE client_id = :cl AND canonical_name = 'Ufficio crediti'"
            ),
            {"cl": scope["client"]},
        ).one()
        assert str(src.id) in [str(x) for x in ent.source_ids]


def test_vector_seed_recovers_entity_not_named_in_query(scope, wait_projected):
    canonical.write_evidence(
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        project_id=scope["project"],
        process_id=scope["process"],
        process_name="Order to Cash",
        entities=["Direttore finanziario", "Ufficio crediti"],
        relationships=[
            {"source": "Direttore finanziario", "relation": "approves",
             "target": "Ufficio crediti", "confidence": 0.7},
        ],
        source_title="Intervista Finance",
        source_text=(
            "Quando un cliente sfora il limite di credito concesso, la pratica "
            "resta sospesa finche' non arriva l'autorizzazione dalla direzione "
            "amministrativa. Senza quella firma la spedizione non parte."
        ),
    )

    # query semanticamente vicina al chunk, ma non cita i nomi delle entita'
    def _q() -> dict:
        return gateway.graph_retrieve(
            consultant_id=scope["consultant"],
            client_id=scope["client"],
            query="cosa succede se un cliente supera il limite di fido?",
            process_id=scope["process"],
            limit=25,
        )

    target = ("Direttore finanziario", "APPROVES", "Ufficio crediti")
    assert wait_projected(lambda: target in _rels(_q()))
    result = _q()
    assert result["status"] == "ok"
    assert result["chunks"], "il contesto testuale deve tornare"
    assert target in _rels(result)


def test_vector_seed_is_client_scoped(scope):
    canonical.write_evidence(
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        project_id=scope["project"],
        process_id=scope["process"],
        entities=["Segreto industriale"],
        source_title="Nota riservata",
        source_text="Il margine sul prodotto X e' del 42 percento, dato riservato.",
    )
    drain_once()

    result = gateway.graph_retrieve(
        consultant_id=scope["consultant"],
        client_id=str(uuid.uuid4()),  # cliente diverso
        query="qual e' il margine sul prodotto X?",
    )
    assert result["chunks"] == []
    assert result["matches"] == []


def test_lexical_arm_works_without_embedder(scope, monkeypatch, wait_projected):
    """Senza embedder: i chunk entrano senza embedding, il retrieval usa solo
    l'arm lessicale (`ts_rank_cd`) e recupera comunque entita' + contesto."""
    from backend.memory import embeddings

    monkeypatch.setattr(embeddings, "available", lambda: False)

    canonical.write_evidence(
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        project_id=scope["project"],
        process_id=scope["process"],
        process_name="Order to Cash",
        entities=["Comitato fidi", "Ufficio crediti"],
        relationships=[
            {"source": "Comitato fidi", "relation": "autorizza",
             "target": "Ufficio crediti", "confidence": 0.7},
        ],
        source_title="Procedura fidi",
        source_text=(
            "Lo sconfinamento del plafond viene escalato al comitato fidi, che "
            "delibera entro 72 ore prima che l'ufficio crediti sblocchi la pratica."
        ),
    )
    def _q() -> dict:
        return gateway.graph_retrieve(
            consultant_id=scope["consultant"],
            client_id=scope["client"],
            query="chi delibera sullo sconfinamento del plafond?",
            process_id=scope["process"],
        )

    target = ("Comitato fidi", "AUTORIZZA", "Ufficio crediti")
    assert wait_projected(lambda: target in _rels(_q()))
    result = _q()
    assert result["status"] == "ok"
    assert result["chunks"], "l'arm lessicale deve restituire contesto"
    top = result["chunks"][0]
    assert top["lexical_score"] is not None
    assert top["vector_score"] is None  # embedder off
    assert target in _rels(result)


def test_hybrid_fuses_lexical_and_vector(scope, wait_projected):
    canonical.write_evidence(
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        project_id=scope["project"],
        process_id=scope["process"],
        process_name="Order to Cash",
        entities=["Direzione amministrativa"],
        source_title="Intervista Finance",
        source_text=(
            "Quando un cliente supera il limite di fido concesso la pratica "
            "resta sospesa finche' la direzione amministrativa non autorizza."
        ),
    )
    # query che cita parole del testo ('limite di fido') -> entrambi gli arm
    def _q() -> dict:
        return gateway.graph_retrieve(
            consultant_id=scope["consultant"],
            client_id=scope["client"],
            query="cosa succede quando un cliente supera il limite di fido?",
            process_id=scope["process"],
        )

    def _fused(r: dict) -> list:
        return [
            c for c in r["chunks"]
            if c["lexical_score"] is not None and c["vector_score"] is not None
        ]

    assert wait_projected(lambda: bool(_fused(_q())))
    assert _fused(_q()), "almeno un chunk deve avere entrambi i segnali (fusione RRF)"
