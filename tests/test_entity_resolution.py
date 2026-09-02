"""P2 — entity resolution: match di kg_entity prima dell'insert.

Serve un Postgres canonical migrato (pg_trgm + pgvector). Skip senza le due
DSN. Il livello LLM e' testato con un modello fake (deterministico); il livello
vettoriale reale sta in `TestVectorPath`, gated anche su OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import time
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
    conn, consultant, client, name, *, entity_type="other", aliases=None,
    embedding=None, created_at=None, source_ids=None, attributes=None,
):
    row = conn.execute(
        text(
            "INSERT INTO kg_entity "
            "(consultant_id, client_id, scope, entity_type, canonical_name, aliases, "
            " attributes, source_ids, embedding, embed_model, embed_dim, embed_version, "
            " created_by, created_at) "
            "VALUES (:c, :cl, 'client', :et, :name, :al, CAST(:attrs AS jsonb), "
            "        CAST(:src AS uuid[]), CAST(:emb AS vector), :em, :ed, :ev, "
            "        'migration', COALESCE(CAST(:ca AS timestamptz), now())) "
            "RETURNING id"
        ),
        {
            "ca": created_at,
            "c": str(consultant),
            "cl": str(client),
            "et": entity_type,
            "name": name,
            "al": list(aliases or []),
            "attrs": json.dumps(attributes or {}),
            "src": [str(s) for s in (source_ids or [])],
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
    project, process = uuid.uuid4(), uuid.uuid4()
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
    yield {
        "consultant": str(consultant), "client": str(client),
        "project": str(project), "process": str(process),
    }
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


def test_typo_variant_goes_through_llm(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        eid = _insert_entity(
            conn, scope["consultant"], scope["client"], "Responsabile Magazzino"
        )

    # refuso: trgm ~0.87 ma nessun auto-merge, decide l'LLM
    llm = FakeLLM(1)
    m = _find(scope, "responsabile magazino", llm=llm)
    assert m is not None and m.entity_id == eid and m.method == "llm"
    assert len(llm.calls) == 1


def test_discriminating_suffix_not_merged(scope):
    """'Segreto A' e 'Segreto B': coseno 0.92, trgm 0.67 -> candidato, ma
    entita' distinte. Senza auto-merge, l'LLM (qui fake=0) le tiene separate."""
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        _insert_entity(conn, scope["consultant"], scope["client"], "Segreto A")

    llm = FakeLLM(0)
    m = _find(scope, "Segreto B", llm=llm)
    assert m is None
    assert len(llm.calls) == 1


def test_no_candidate_returns_none(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        _insert_entity(conn, scope["consultant"], scope["client"], "Ufficio Crediti")

    llm = FakeLLM(1)
    m = _find(scope, "Sistema di produzione XYZ", llm=llm)
    assert m is None
    assert llm.calls == []


def test_no_llm_skips_fuzzy_but_keeps_exact(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        fuzzy = _insert_entity(
            conn, scope["consultant"], scope["client"], "Ufficio Gestione Crediti"
        )
        exact = _insert_entity(
            conn, scope["consultant"], scope["client"], "Direzione Vendite"
        )

    # use_llm=False, nessun llm: il fuzzy resta separato...
    assert _find(scope, "ufficio crediti", use_llm=False) is None
    # ...ma il match esatto continua a funzionare
    m = _find(scope, "  direzione   VENDITE ", use_llm=False)
    assert m is not None and m.entity_id == exact and m.method == "exact_name"
    assert fuzzy != exact


def test_consultant_scope_has_no_resolution(scope):
    with canonical_session(scope["consultant"]) as s:
        m = er.find_match(s, client_id=None, entity_type="other", name="qualsiasi")
    assert m is None


# --- plan_resolution: decisione FUORI dalla transazione di scrittura -----


def test_plan_resolution_returns_match_without_write_tx(scope):
    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"], scope["client"])
        eid = _insert_entity(
            conn, scope["consultant"], scope["client"], "Ufficio Gestione Crediti"
        )

    llm = FakeLLM(1)
    plan = er.plan_resolution(
        scope["consultant"], scope["client"],
        ["ufficio crediti", "Sistema di produzione XYZ"], llm=llm,
    )
    match, _vec = plan.lookup("Ufficio Crediti")
    assert match is not None and match.entity_id == eid and match.method == "llm"
    # il nome senza candidati non entra nel piano
    assert plan.lookup("sistema di produzione xyz")[0] is None
    assert len(llm.calls) == 1


def test_plan_resolution_empty_when_disabled(scope, monkeypatch):
    monkeypatch.setattr(settings, "canonical_entity_resolution", False)
    llm = FakeLLM(1)
    plan = er.plan_resolution(scope["consultant"], scope["client"], ["qualsiasi"], llm=llm)
    assert plan.matches == {} and plan.name_vectors == {}
    assert llm.calls == []  # nessuna chiamata: feature spenta


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
        assert m.method == "llm"
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


# --- integrazione: write_evidence fonde davvero -------------------------

_WEV_NEEDED = (
    settings.canonical_worker_url,
    settings.neo4j_password,
    settings.openai_api_key,
)


@pytest.mark.skipif(
    not all(_WEV_NEEDED), reason="serve CANONICAL_WORKER_URL + NEO4J_PASSWORD + OPENAI_API_KEY"
)
class TestWriteEvidenceResolution:
    def test_second_interview_synonym_folds_into_first(self, scope):
        from backend.memory.knowledge_graph import canonical, neo4j_store
        from backend.workers.graph_worker import drain_once

        with MIGRATOR.begin() as conn:
            _ctx(conn, scope["consultant"])
            conn.execute(
                text(
                    "INSERT INTO project (id, client_id, consultant_id, name) "
                    "VALUES (:i,:cl,:c,'P')"
                ),
                {"i": scope["project"], "cl": scope["client"], "c": scope["consultant"]},
            )
            conn.execute(
                text(
                    "INSERT INTO process (id, project_id, client_id, consultant_id, name) "
                    "VALUES (:i,:p,:cl,:c,'HR onboarding')"
                ),
                {
                    "i": scope["process"], "p": scope["project"],
                    "cl": scope["client"], "c": scope["consultant"],
                },
            )

        common = dict(
            consultant_id=scope["consultant"], client_id=scope["client"],
            project_id=scope["project"], process_id=scope["process"],
            process_name="HR onboarding",
        )
        resolver = FakeLLM(1)  # "e' lo stesso candidato"

        canonical.write_evidence(
            **common,
            entities=["Ufficio del Personale"],
            relationships=[{
                "source": "Ufficio del Personale", "relation": "gestisce",
                "target": "Assunzioni", "confidence": 0.7,
            }],
            source_title="Intervista 1",
            source_text="L'ufficio del personale gestisce le assunzioni e i contratti.",
            resolver_llm=resolver,
        )
        canonical.write_evidence(
            **common,
            entities=["ufficio risorse umane"],
            relationships=[{
                "source": "ufficio risorse umane", "relation": "cura",
                "target": "Onboarding", "confidence": 0.8,
            }],
            source_title="Intervista 2",
            source_text="Le risorse umane curano l'onboarding dei nuovi assunti.",
            resolver_llm=resolver,
        )

        with canonical_session(scope["consultant"], scope["client"]) as s:
            hr = s.execute(
                text(
                    "SELECT id, canonical_name, aliases FROM kg_entity "
                    "WHERE client_id = :cl AND lower(canonical_name) LIKE '%personale%'"
                ),
                {"cl": scope["client"]},
            ).all()
            assert len(hr) == 1, "il sinonimo non deve creare una seconda entita'"
            assert "ufficio risorse umane" in (hr[0].aliases or [])

            # nessuna entita' 'ufficio risorse umane' separata
            dup = s.execute(
                text(
                    "SELECT count(*) FROM kg_entity WHERE client_id = :cl "
                    "AND lower(canonical_name) = 'ufficio risorse umane'"
                ),
                {"cl": scope["client"]},
            ).scalar_one()
            assert dup == 0

            hr_id = str(hr[0].id)
            rel_src = s.execute(
                text(
                    "SELECT relation FROM kg_relation "
                    "WHERE client_id = :cl AND source_entity_id = :e ORDER BY relation"
                ),
                {"cl": scope["client"], "e": hr_id},
            ).scalars().all()
            assert rel_src == ["CURA", "GESTISCE"], "entrambe le relazioni sull'entita' fusa"

        # il gateway trova l'entita' partendo dal nome-alias. best-effort sul
        # drain: se l'app gira, il suo worker in-process puo' aver gia' drenato.
        from backend.memory import gateway

        rels: set = set()
        for _ in range(12):
            drain_once()
            result = gateway.graph_retrieve(
                consultant_id=scope["consultant"], client_id=scope["client"],
                entity_names=["ufficio risorse umane"], process_id=scope["process"],
            )
            rels = {(m["source"], m["relation"], m["target"]) for m in result["matches"]}
            if ("Ufficio del Personale", "CURA", "Onboarding") in rels:
                break
            time.sleep(0.5)
        assert ("Ufficio del Personale", "CURA", "Onboarding") in rels

        neo4j_store.purge_client(scope["client"])


# --- guardie deterministiche del write path ----------------------------


def test_write_entity_stale_match_falls_back_to_insert(scope):
    from backend.memory.knowledge_graph import canonical

    ghost = er.ResolvedEntity(str(uuid.uuid4()), "entita' sparita", "llm")
    new_id = canonical.write_entity(
        scope["consultant"], scope["client"], "other", "Entita' Nuova", match=ghost,
    )
    with canonical_session(scope["consultant"], scope["client"]) as s:
        row = s.execute(
            text("SELECT canonical_name FROM kg_entity WHERE id = :i"), {"i": new_id}
        ).one()
    assert row.canonical_name == "Entita' Nuova"
    assert new_id != ghost.entity_id


def test_write_evidence_skips_self_loop_when_endpoints_resolve_together(scope):
    from backend.memory.knowledge_graph import canonical

    with MIGRATOR.begin() as conn:
        _ctx(conn, scope["consultant"])
        conn.execute(
            text(
                "INSERT INTO project (id, client_id, consultant_id, name) VALUES (:i,:cl,:c,'P')"
            ),
            {"i": scope["project"], "cl": scope["client"], "c": scope["consultant"]},
        )
        _ctx(conn, scope["consultant"], scope["client"])
        _insert_entity(
            conn, scope["consultant"], scope["client"], "Squadra Vendite",
            aliases=["team sales"],
        )

    counts = canonical.write_evidence(
        consultant_id=scope["consultant"], client_id=scope["client"],
        project_id=scope["project"],
        entities=["Team Sales"],
        relationships=[{
            "source": "Team Sales", "relation": "coincide_con", "target": "Squadra Vendite",
        }],
    )
    assert counts["relationships"] == 0  # estremi -> stessa entita' -> saltata

    with canonical_session(scope["consultant"], scope["client"]) as s:
        assert s.execute(
            text("SELECT count(*) FROM kg_relation WHERE client_id = :cl"),
            {"cl": scope["client"]},
        ).scalar_one() == 0
        assert s.execute(
            text("SELECT count(*) FROM kg_entity WHERE client_id = :cl AND status = 'active'"),
            {"cl": scope["client"]},
        ).scalar_one() == 1


# --- sweep: dedup di un grafo gia' sporco (P2.4) -----------------------

_SWEEP_NEEDED = (settings.canonical_worker_url, settings.neo4j_password)


@pytest.mark.skipif(
    not all(_SWEEP_NEEDED), reason="serve CANONICAL_WORKER_URL + NEO4J_PASSWORD"
)
class TestSweep:
    def test_sweep_merges_existing_duplicates(self, scope):
        import datetime as dt

        from scripts import kg_resolve_entities as sweep
        from backend.memory.knowledge_graph import neo4j_store
        from backend.workers.graph_worker import drain_once

        base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        src_surv, src_lose = uuid.uuid4(), uuid.uuid4()
        with MIGRATOR.begin() as conn:
            _ctx(conn, scope["consultant"], scope["client"])
            survivor = _insert_entity(
                conn, scope["consultant"], scope["client"], "Ufficio Crediti",
                created_at=base.isoformat(), source_ids=[src_surv],
                attributes={"role_type": "office"},
            )
            other = _insert_entity(
                conn, scope["consultant"], scope["client"], "Magazzino Centrale",
                created_at=(base + dt.timedelta(days=1)).isoformat(),
            )
            loser = _insert_entity(
                conn, scope["consultant"], scope["client"], "ufficio del credito",
                created_at=(base + dt.timedelta(days=2)).isoformat(),
                source_ids=[src_lose], attributes={"seniority": "senior"},
            )
            conn.execute(
                text(
                    "INSERT INTO kg_relation "
                    "(consultant_id, client_id, scope, source_entity_id, target_entity_id, "
                    " relation, created_by) "
                    "VALUES (:c,:cl,'client',:s,:t,'BLOCCA','migration')"
                ),
                {
                    "c": scope["consultant"], "cl": scope["client"],
                    "s": loser, "t": other,
                },
            )

        # sweep con LLM fake che conferma sempre il primo candidato
        n = sweep.sweep_client(
            scope["consultant"], scope["client"], FakeLLM(1), apply=True, limit=50,
        )
        assert n == 1

        with MIGRATOR.begin() as conn:
            _ctx(conn, scope["consultant"], scope["client"])
            active = conn.execute(
                text(
                    "SELECT canonical_name, aliases, source_ids, attributes FROM kg_entity "
                    "WHERE client_id = :cl AND status = 'active' ORDER BY canonical_name"
                ),
                {"cl": scope["client"]},
            ).all()
            assert [r.canonical_name for r in active] == ["Magazzino Centrale", "Ufficio Crediti"]
            surv_row = next(r for r in active if r.canonical_name == "Ufficio Crediti")
            assert "ufficio del credito" in (surv_row.aliases or [])
            # il survivor assorbe la provenance e gli attributi del loser (#1 review)
            assert {str(x) for x in surv_row.source_ids} == {str(src_surv), str(src_lose)}
            assert surv_row.attributes == {"role_type": "office", "seniority": "senior"}

            dep = conn.execute(
                text("SELECT status, supersedes_id FROM kg_entity WHERE id = :i"),
                {"i": loser},
            ).one()
            assert dep.status == "deprecated"
            assert str(dep.supersedes_id) == survivor

            rel = conn.execute(
                text(
                    "SELECT source_entity_id, target_entity_id, relation "
                    "FROM kg_relation WHERE client_id = :cl"
                ),
                {"cl": scope["client"]},
            ).one()
            assert str(rel.source_entity_id) == survivor
            assert str(rel.target_entity_id) == other

            outbox = conn.execute(
                text(
                    "SELECT op, payload->>'kind' AS kind FROM graph_outbox "
                    "WHERE client_id = :cl AND processed_at IS NULL ORDER BY id"
                ),
                {"cl": scope["client"]},
            ).all()
            kinds = {(o.op, o.kind) for o in outbox}
            assert ("delete", "node_delete") in kinds
            assert ("upsert", "edge") in kinds

        assert drain_once() >= 1

        driver = neo4j_store.get_driver()
        with driver.session() as neo:
            gone = neo.run(
                "MATCH (n:Entity {entity_id:$i}) RETURN count(n) AS c", i=loser
            ).single()["c"]
            assert gone == 0
            edge = neo.run(
                "MATCH (:Entity {entity_id:$s})-[r:BLOCCA]->(:Entity {entity_id:$t}) "
                "RETURN count(r) AS c",
                s=survivor, t=other,
            ).single()["c"]
            assert edge == 1

        neo4j_store.purge_client(scope["client"])
