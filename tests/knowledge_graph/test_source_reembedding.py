"""Un testo gia' nel grafo non si embedda di nuovo.

Ogni pacchetto di evidenza che l'agente estrae da un'intervista porta con se'
l'intervista intera (`source_text`). `write_evidence` calcolava i vettori di
tutti i chunk **prima** di guardare se la sorgente c'era gia': la scrittura era
idempotente, l'embedding no. Tre pacchetti dalla stessa intervista pagavano
l'intervista tre volte e ne buttavano due.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select, text

from backend.settings import settings

if not all((settings.canonical_migrator_url, settings.canonical_database_url)):
    pytest.skip("servono le DSN canonical", allow_module_level=True)

from backend.llm import LlmTask, OperationKind, operation  # noqa: E402
from backend.memory.knowledge_graph import canonical  # noqa: E402
from backend.workspace_storage import WorkspaceLlmUsage, workspace_connection  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)

_INTERVISTA = " ".join(
    f"Passo {n}: l'ufficio crediti controlla il fido del cliente e, se serve, "
    "chiede l'autorizzazione alla direzione amministrativa prima del rilascio."
    for n in range(40)
)


@pytest.fixture()
def scope():
    c, cl = uuid.uuid4(), uuid.uuid4()
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,'reembed')"),
            {"i": c, "e": f"{c}@t.local"},
        )
        conn.execute(text("SELECT set_config('app.current_consultant_id', :v, true)"), {"v": str(c)})
        conn.execute(text("SELECT set_config('app.current_client_id', '', true)"))
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'AcmeReembed')"),
            {"i": cl, "c": c},
        )
    yield {"consultant": str(c), "client": str(cl)}
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": c})


@pytest.fixture()
def embedder(monkeypatch):
    """Il client del fornitore, finto: conta quanti testi gli arrivano."""
    seen = {"calls": 0, "texts": 0}

    class _Response:
        def __init__(self, n, dimensions):
            self.data = [type("_I", (), {"embedding": [0.01] * dimensions})() for _ in range(n)]
            self.usage = type("_U", (), {"prompt_tokens": 50 * n})()

    class _Embeddings:
        def create(self, *, model, input, dimensions):  # noqa: A002 - firma dell'SDK
            seen["calls"] += 1
            seen["texts"] += len(input)
            return _Response(len(input), dimensions)

    class _Client:
        embeddings = _Embeddings()

    def _no_chat(*_args, **_kwargs):
        raise AssertionError("nessun giudizio di chat atteso")

    monkeypatch.setattr(settings, "openai_api_key", "sk-test-reembed")
    monkeypatch.setattr("backend.llm.gateway._embedding_client", lambda: _Client())
    monkeypatch.setattr("backend.llm.gateway._client", _no_chat)
    return seen


def _ingest(scope, entity: str, project: str) -> dict:
    with operation(OperationKind.KG_INGESTION, project_id=project):
        return canonical.write_evidence(
            consultant_id=scope["consultant"],
            client_id=scope["client"],
            entities=[entity],
            source_title="Intervista Finance",
            source_text=_INTERVISTA,
        )


def test_la_stessa_intervista_si_embedda_una_volta_sola(scope, embedder):
    project = f"ws-{uuid.uuid4().hex[:8]}"
    chunks = len(canonical._chunk_text(_INTERVISTA))
    assert chunks > 3, "l'intervista di prova deve avere piu' chunk"

    first = _ingest(scope, "Ufficio crediti", project)
    texts_after_first = embedder["texts"]
    second = _ingest(scope, "Direzione amministrativa", project)
    third = _ingest(scope, "Tesoreria", project)

    assert first["chunks"] == chunks
    assert (second["chunks"], third["chunks"]) == (0, 0)
    # Solo il nome della nuova entita' si embedda; i chunk dell'intervista no.
    assert embedder["texts"] - texts_after_first == 2

    with workspace_connection() as session:
        rows = list(
            session.scalars(select(WorkspaceLlmUsage).where(WorkspaceLlmUsage.project_id == project))
        )
    avoided = [r for r in rows if r.task == LlmTask.EMBEDDING.value and r.outcome == "cache_hit"]
    assert len(avoided) == 2, "il risparmio deve stare nel registro"


def test_un_testo_nuovo_si_embedda_ancora(scope, embedder):
    project = f"ws-{uuid.uuid4().hex[:8]}"
    _ingest(scope, "Ufficio crediti", project)

    with operation(OperationKind.KG_INGESTION, project_id=project):
        counts = canonical.write_evidence(
            consultant_id=scope["consultant"],
            client_id=scope["client"],
            entities=["Ufficio crediti"],
            source_title="Seconda intervista",
            source_text=_INTERVISTA + " Un passo in piu'.",
        )

    assert counts["chunks"] >= 1
