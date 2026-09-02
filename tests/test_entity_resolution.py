"""P2 — entity resolution: match di kg_entity prima dell'insert.

Serve un Postgres canonical migrato (pg_trgm + pgvector). Skip senza le due
DSN. Il livello LLM e' testato con un modello fake (deterministico); il livello
vettoriale reale sta in `TestVectorPath`, gated anche su OPENAI_API_KEY.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

if not settings.canonical_migrator_url or not settings.canonical_database_url:
    pytest.skip(
        "CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL non configurate",
        allow_module_level=True,
    )

from backend.db import canonical_session  # noqa: E402
from backend.memory import embeddings  # noqa: E402
from backend.memory.knowledge_graph import entity_resolution as er  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


class FakeLLM:
    """with_structured_output stub: ritorna un _Verdict fisso, registra le call."""

    def __init__(self, match_index: int):
        self.match_index = match_index
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)
        return er._Verdict(match_index=self.match_index, reason="fake")


def _ctx(conn, consultant, client=None):
    conn.execute(
        text("SELECT set_config('app.current_consultant_id', :v, true)"),
        {"v": str(consultant)},
    )
    conn.execute(
        text("SELECT set_config('app.current_client_id', :v, true)"),
        {"v": str(client) if client else ""},
    )


def _insert_entity(
    conn, consultant, client, name, *, entity_type="other", aliases=None, embedding=None
):
    row = conn.execute(
        text(
            "INSERT INTO kg_entity "
            "(consultant_id, client_id, scope, entity_type, canonical_name, aliases, "
            " embedding, embed_model, embed_dim, embed_version, created_by) "
            "VALUES (:c, :cl, 'client', :et, :name, :al, "
            "        CAST(:emb AS vector), :em, :ed, :ev, 'migration') "
            "RETURNING id"
        ),
        {
            "c": str(consultant),
            "cl": str(client),
            "et": entity_type,
            "name": name,
            "al": list(aliases or []),
            "emb": embedding,
            "em": embeddings.EMBED_MODEL if embedding else None,
            "ed": embeddings.EMBED_DIM if embedding else None,
            "ev": embeddings.EMBED_VERSION if embedding else None,
        },
    ).one()
    return str(row.id)


@pytest.fixture()
def scope():
    consultant, client = uuid.uuid4(), uuid.uuid4()
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,'t')"),
            {"i": consultant, "e": f"{consultant}@t.local"},
        )
        _ctx(conn, consultant)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'AcmeER')"),
            {"i": client, "c": consultant},
        )
    yield {"consultant": str(consultant), "client": str(client)}
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": consultant})


def _find(scope, name, **kw):
    with canonical_session(scope["consultant"], scope["client"]) as s:
        return er.find_match(
            s, client_id=scope["client"], entity_type=kw.pop("entity_type", "other"),
            name=name, **kw,
        )


# --- livello 0: esatto -----------------------------------------------------


def test_exact_name_normalized(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        eid = _insert_entity(conn, scope["consultant"], scope["client"], "Ufficio Crediti")

    m = _find(scope, "  ufficio   crediti ", llm=FakeLLM(0))
    assert m is not None
    assert m.entity_id == eid
    assert m.method == "exact_name"


def test_exact_alias(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        eid = _insert_entity(
            conn, scope["consultant"], scope["client"], "CFO",
            aliases=["chief financial officer", "direttore finanziario"],
        )

    m = _find(scope, "Direttore Finanziario", llm=FakeLLM(0))
    assert m is not None and m.entity_id == eid and m.method == "exact_alias"


def test_specific_type_mismatch_blocks_exact(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        _insert_entity(
            conn, scope["consultant"], scope["client"], "Mario Rossi", entity_type="person"
        )

    # stesso nome, ma tipo specifico incompatibile -> nessun match
    llm = FakeLLM(1)
    m = _find(scope, "Mario Rossi", entity_type="system", llm=llm)
    assert m is None
    assert llm.calls == []  # il gate di tipo scarta prima dell'LLM


# --- livello 1+2: trigram -> giudizio -----------------------------------


def test_trgm_candidate_llm_confirms(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        eid = _insert_entity(
            conn, scope["consultant"], scope["client"], "Ufficio Gestione Crediti"
        )

    llm = FakeLLM(1)
    m = _find(scope, "ufficio crediti", llm=llm)
    assert m is not None and m.entity_id == eid and m.method == "llm"
    assert len(llm.calls) == 1


def test_trgm_candidate_llm_rejects(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        _insert_entity(conn, scope["consultant"], scope["client"], "Ufficio Gestione Crediti")

    llm = FakeLLM(0)  # "nessuno"
    m = _find(scope, "ufficio crediti", llm=llm)
    assert m is None
    assert len(llm.calls) == 1


def test_trgm_auto_accept_skips_llm(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        eid = _insert_entity(
            conn, scope["consultant"], scope["client"], "Responsabile Magazzino"
        )

    llm = FakeLLM(0)
    m = _find(scope, "responsabile magazino", llm=llm)  # refuso -> trgm ~0.87
    assert m is not None and m.entity_id == eid and m.method == "auto_trgm"
    assert llm.calls == []


def test_no_candidate_returns_none(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        _insert_entity(conn, scope["consultant"], scope["client"], "Ufficio Crediti")

    llm = FakeLLM(1)
    m = _find(scope, "Sistema di produzione XYZ", llm=llm)
    assert m is None
    assert llm.calls == []


def test_no_llm_no_autoaccept_returns_none(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        _insert_entity(conn, scope["consultant"], scope["client"], "Ufficio Gestione Crediti")

    # use_llm=False e nessun llm iniettato: fascia incerta -> None (conservativo)
    m = _find(scope, "ufficio crediti", use_llm=False)
    assert m is None


def test_consultant_scope_has_no_resolution(scope):
    with canonical_session(scope["consultant"]) as s:
        m = er.find_match(s, client_id=None, entity_type="other", name="qualsiasi")
    assert m is None


# --- livello vettoriale reale -------------------------------------------


@pytest.mark.skipif(not settings.openai_api_key, reason="serve OPENAI_API_KEY")
class TestVectorPath:
    def test_semantic_synonym_via_vector_and_llm(self, scope):
        vecs = embeddings.embed_texts(
            ["Ufficio del Personale", "ufficio risorse umane"]
        )
        assert vecs is not None
        with MIGRATOR.begin() as conn:
            _ctx(conn, scope["consultant"], scope["client"])
            eid = _insert_entity(
                conn, scope["consultant"], scope["client"], "Ufficio del Personale",
                embedding=embeddings.to_pgvector(vecs[0]),
            )

        # "ufficio risorse umane" non e' lessicalmente vicino (parole diverse)
        # ma semanticamente si' (~0.69 coseno): il seed vettoriale lo pesca,
        # l'LLM conferma.
        llm = FakeLLM(1)
        m = _find(
            scope, "ufficio risorse umane",
            name_vec=embeddings.to_pgvector(vecs[1]), llm=llm,
        )
        assert m is not None and m.entity_id == eid
        assert m.method in {"llm", "auto_cosine"}
        assert len(llm.calls) == 1

    def test_unrelated_name_not_matched(self, scope):
        vecs = embeddings.embed_texts(["Direzione Amministrativa", "furgone per consegne"])
        assert vecs is not None
        with MIGRATOR.begin() as conn:
            _ctx(conn, scope["consultant"], scope["client"])
            _insert_entity(
                conn, scope["consultant"], scope["client"], "Direzione Amministrativa",
                embedding=embeddings.to_pgvector(vecs[0]),
            )

        llm = FakeLLM(1)  # anche se l'LLM direbbe si', non deve arrivarci
        m = _find(
            scope, "furgone per consegne",
            name_vec=embeddings.to_pgvector(vecs[1]), llm=llm,
        )
        assert m is None
        assert llm.calls == []  # sotto CANDIDATE_COSINE_MIN: nessun candidato
