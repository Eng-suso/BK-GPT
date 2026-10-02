"""Il retrieval sulle interviste del golden set, misurato con recall, MRR e nDCG.

Le sei interviste dei due casi entrano nel canonical come fonti di due processi
dello stesso cliente, attraverso il percorso vero (`write_evidence`: chunk +
`kg_source`). Ogni domanda di `queries.json` passa da `graph_retrieve` con lo
scope del suo processo, e i primi k chunk si confrontano con i passi attesi.

Gira sul ramo lessicale, senza embedder: e' deterministico, non spende e quindi
sta in CI come L0, ma misura qualita' e non un'invariante, per questo e' L1.
La baseline (`baseline.json`) ferma le regressioni; il rapporto per domanda
finisce in `tests/golden/reports/retrieval.json`. Il ramo vettoriale si misurera'
con lo stesso dataset, col modello vero e con l'opt-in esplicito.

Il corpus e' piccolo - una decina di chunk per processo - e un recall@5 alto qui
dice poco. Il numero che conta e' quello che si muove quando cambia il
retrieval: chunking, tokenizzazione, fusione, reranking.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings
from tests.evals.retrieval_metrics import (
    RetrievalSet,
    aggregate,
    passages_in,
    retrieval_regressions,
    score_query,
)

pytestmark = pytest.mark.skipif(
    not (settings.canonical_migrator_url and settings.canonical_database_url and settings.neo4j_password),
    reason="servono le DSN canonical e NEO4J_PASSWORD",
)

HERE = Path(__file__).resolve().parent
GOLDEN = HERE.parents[1] / "golden"
DATASET = RetrievalSet.load(HERE / "queries.json")
BASELINE = HERE / "baseline.json"
REPORT = GOLDEN / "reports" / "retrieval.json"


def _ctx(conn, consultant_id, client_id=None):
    conn.execute(text("SELECT set_config('app.current_consultant_id', :v, true)"), {"v": str(consultant_id)})
    conn.execute(
        text("SELECT set_config('app.current_client_id', :v, true)"),
        {"v": str(client_id) if client_id else ""},
    )


@pytest.fixture(scope="module")
def corpus():
    """Un cliente, un progetto, un processo per caso, le interviste come fonti."""
    from backend.memory import embeddings
    from backend.memory.knowledge_graph import canonical, neo4j_store

    migrator = create_engine(settings.canonical_migrator_url, future=True)
    consultant, client, project = (uuid.uuid4() for _ in range(3))
    cases = sorted({query.case for query in DATASET.queries})
    processes = {case: uuid.uuid4() for case in cases}

    with migrator.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i, :e, 'retrieval')"),
            {"i": consultant, "e": f"{consultant}@eval.local"},
        )
        _ctx(conn, consultant)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i, :c, 'Golden')"),
            {"i": client, "c": consultant},
        )
        conn.execute(
            text("INSERT INTO project (id, client_id, consultant_id, name) VALUES (:i, :cl, :c, 'Golden')"),
            {"i": project, "cl": client, "c": consultant},
        )
        for case, process in processes.items():
            conn.execute(
                text(
                    "INSERT INTO process (id, project_id, client_id, consultant_id, name) "
                    "VALUES (:i, :p, :cl, :c, :n)"
                ),
                {"i": process, "p": project, "cl": client, "c": consultant, "n": case},
            )

    with pytest.MonkeyPatch.context() as patch:
        # Ramo lessicale e basta: senza questo, una chiave nell'ambiente
        # renderebbe il numero dipendente dal modello di embedding.
        patch.setattr(embeddings, "available", lambda: False)
        for case, process in processes.items():
            for source in sorted((GOLDEN / case / "sources").glob("*.md")):
                canonical.write_evidence(
                    consultant_id=str(consultant),
                    client_id=str(client),
                    project_id=str(project),
                    process_id=str(process),
                    process_name=case,
                    source_title=source.name,
                    source_text=source.read_text(encoding="utf-8"),
                    source_kind="interview",
                )
        yield {
            "consultant": str(consultant),
            "client": str(client),
            "project": str(project),
            "processes": {case: str(process) for case, process in processes.items()},
            "migrator": migrator,
        }

    with migrator.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": consultant})
    neo4j_store.purge_client(str(client))
    migrator.dispose()


def _chunks_of(corpus, process_id: str) -> list[tuple[str, str]]:
    """Tutti i chunk delle fonti di un processo: (source_id, contenuto)."""
    with corpus["migrator"].begin() as conn:
        _ctx(conn, corpus["consultant"], corpus["client"])
        rows = conn.execute(
            text(
                "SELECT c.source_id, c.content FROM kg_chunk c "
                "JOIN kg_source s ON s.id = c.source_id "
                "WHERE s.client_id = :cl AND s.process_id = CAST(:pr AS uuid)"
            ),
            {"cl": corpus["client"], "pr": process_id},
        ).all()
    return [(str(row.source_id), row.content) for row in rows]


def test_retrieval_brings_the_passages_a_consultant_would_point_to(corpus):
    from backend.memory import embeddings, gateway

    results = []
    leaks = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(embeddings, "available", lambda: False)
        for query in DATASET.queries:
            process_id = corpus["processes"][query.case]
            in_process = _chunks_of(corpus, process_id)
            own_sources = {source_id for source_id, _ in in_process}
            passages = [passage.quote for passage in query.passages]

            answer = gateway.graph_retrieve(
                consultant_id=corpus["consultant"],
                client_id=corpus["client"],
                query=query.query,
                scope_project_id=corpus["project"],
                scope_process_id=process_id,
                limit=25,
            )
            chunks = answer.get("chunks") or []
            leaks.extend(
                f"{query.id}: chunk di un altro processo ({chunk['source_title']})"
                for chunk in chunks
                if chunk["source_id"] not in own_sources
            )
            results.append(
                score_query(
                    query.id,
                    [chunk["content"] for chunk in chunks],
                    passages,
                    k=DATASET.k,
                    relevant_in_corpus=sum(1 for _, content in in_process if passages_in(content, passages)),
                )
            )

    current = aggregate(results)
    report = {
        "k": DATASET.k,
        "arm": "lexical",
        **current,
        "queries": [result.as_dict() for result in results],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Lo scope e' un'autorizzazione, non un ranking: un chunk di un altro
    # processo non deve arrivare nemmeno in fondo alla lista.
    assert not leaks, "\n".join(leaks)

    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    found = retrieval_regressions(current, baseline.get("lexical", {}))
    assert not found, "regressioni del retrieval lessicale:\n" + "\n".join(found)
