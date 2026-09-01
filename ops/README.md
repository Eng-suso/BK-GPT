# Stack dati — DeliR ("Cervello DeliR")

Un solo `docker-compose` (INV-3): **Postgres** (canonical, INV-1) + **Neo4j
Community** (projection grafo tipizzato). **Mem0 OSS** non è un servizio: è una
libreria in-process nel backend, col vector store nel database `mem0`.

Tutto su `127.0.0.1`. Sulla Oracle Free VM resta sulla rete docker interna,
mai sulla `:443`; l'accesso passa dal gateway applicativo (INV-9).

## Avvio

```bash
cd ops
cp .env.example .env          # cambia TUTTE le password
docker compose up -d
```

Al primo avvio del volume Postgres girano, come superuser:
- `postgres/init/00-bootstrap.sh` — ruoli `delir_migrator` / `delir_app` /
  `delir_worker`, ownership schema `public`, estensioni `vector` + `pg_trgm`
- `postgres/init/01-mem0.sh` — ruolo `delir_mem0`, database `mem0` che possiede,
  estensioni in quel db

Per rieseguirli: `docker compose down -v && docker compose up -d`.

## Ruoli Postgres (INV-6)

| Ruolo | Uso | Privilegi |
|---|---|---|
| `delir_super` | solo entrypoint + bootstrap | superuser (mai usato dall'app) |
| `delir_migrator` | Alembic | owner schema `public`, `NOCREATEROLE` |
| `delir_app` | backend | solo DML, `NOBYPASSRLS`, non-owner; su `graph_outbox`/`mem0_projection_log` solo `INSERT` |
| `delir_worker` | worker outbox | solo `SELECT/UPDATE` sulle due code |
| `delir_mem0` | Mem0 OSS | owner del database `mem0` (isolato dallo schema canonical) |

`delir_app` non possiede le tabelle → `FORCE ROW LEVEL SECURITY` (0005) vale anche per lui.

## Migration

Scritte a mano con `op.execute()`. Girano SEMPRE come `delir_migrator`.

```bash
# dalla root del repo
export CANONICAL_MIGRATOR_URL="postgresql+psycopg://delir_migrator:<pw>@127.0.0.1:55432/delir"
uv run alembic upgrade head
uv run alembic downgrade base     # reversibile
```

## Config app (`.env` alla root del repo)

```
CANONICAL_DATABASE_URL=postgresql+psycopg://delir_app:<pw>@127.0.0.1:55432/delir
CANONICAL_MIGRATOR_URL=postgresql+psycopg://delir_migrator:<pw>@127.0.0.1:55432/delir
CANONICAL_WORKER_URL=postgresql+psycopg://delir_worker:<pw>@127.0.0.1:55432/delir
MEM0_DATABASE_URL=postgresql://delir_mem0:<pw>@127.0.0.1:55432/mem0
MEM0_LLM_MODEL=gpt-4o-mini      # override se il tuo account OpenAI non ce l'ha
NEO4J_PASSWORD=<pw>             # = NEO4J_PASSWORD in ops/.env
```

L'app tocca il canonical solo via `backend.db.canonical_session(consultant_id, client_id)`
(imposta il contesto RLS). Mem0 solo via `backend.memory.mem0_client.get_memory()`.

## Stato — schema canonical (migration 0001-0005) ✅

| | |
|---|---|
| 0001 | funzioni contesto `app_consultant_id`/`app_client_id`, `set_updated_at`, backbone `consultant → client → project → process`, grant `delir_app` |
| 0002 | `kg_source` (provenance) · `kg_chunk` (`vector(1536)` + HNSW + tsvector) |
| 0003 | `semantic_memory` / `episodic_memory` / `procedural_memory` — scope `client\|consultant`, lifecycle, `guardrail_status` + gate, provenance |
| 0004 | `graph_outbox` + `mem0_projection_log` (delir_app solo INSERT) + view `v_projection_backlog` |
| 0005 | RLS `ENABLE`+`FORCE` su tenant tables; `consultant` solo `ENABLE` |
| 0006 | catalogo struttura KG L1: `kg_entity` / `kg_relation` / `kg_claim` / `kg_gap` / `kg_contradiction` / `kg_impact` + RLS + trigger. Mappa PG→Neo4j in `backend/memory/knowledge_graph/catalog.py` |

Test: `tests/test_canonical_rls.py` (6) + `tests/test_kg_catalog.py` (lint B+ + 1 caso RLS), skip senza le due DSN.

## Mem0 OSS ✅

`backend/memory/mem0_client.py` — `mem0.Memory` in-process, vector store = db
`mem0` (pgvector), LLM + embedder = OpenAI, telemetria off, `custom_instructions`
per non tradurre. Niente graph store (il grafo è Neo4j). Disattivato in silenzio
se `MEM0_DATABASE_URL` non è configurata.

Scope oggi = consultant-level (`mem0_user_id`). Lo scope per cliente arriva con
la migrazione della memoria canonica (INV-13).

## Pipeline di proiezione (P1) — porta di scrittura + worker ✅

**Grafo:** `backend/memory/knowledge_graph/canonical.py` — `write_entity` /
`write_relation` / `write_process_node` / `write_claim` / `write_gap` /
`write_contradiction` / `write_impact`. INSERT tabella + riga `graph_outbox`
(payload B+-safe, `assert_projectable`) nella stessa TX. Archi strutturali
(`HAS_CLAIM`, `BLOCKS`, `AFFECTS`, `BETWEEN`) emessi insieme al nodo.
`backend/workers/graph_worker.py` (ruolo `delir_worker`) drena l'outbox →
`projector.py` (MERGE idempotenti). `neo4j_store.purge_client()` per INV-10.

**Mem0:** `backend/memory/canonical_memory.py` — `write_semantic_memory` /
`write_episodic_memory`. INSERT tabella + riga `mem0_projection_log` nella
stessa TX. `backend/workers/mem0_worker.py` drena → Mem0 OSS (`add`/`update`/
`delete`), scrive indietro `mem0_memory_id`.

```bash
uv run python -m backend.workers.graph_worker   # loop
uv run python -m backend.workers.mem0_worker    # loop
```

Test: `tests/test_graph_projection.py`, `tests/test_mem0_projection.py`.

## Mirror sul canonical (P1 slice 3, parziale) — strangler fig ✅

`manage_process_evidence` / `save_process_episode` / `index_process_evidence_graph`
/ `manage_project_evidence` continuano a scrivere sul vecchio `store.py`
(autoritativo per ora) **e in più** specchiano su Postgres canonical + outbox
tramite `backend/memory/knowledge_graph/mirror.py`. Best-effort, mai
un'eccezione verso l'agente; il risultato è nel payload sotto
`"canonical_mirror"`.

- `backend/memory/scope.py` — ponte "project-1"/"proc-1" (workspace SQLite) →
  `client`/`project`/`process` canonical, upsert idempotente su `workspace_id`
  (migration `0007`, che semina anche il consulente unico di default)
- `write_entity` / `write_relation` ora fanno `ON CONFLICT ... DO UPDATE`
  (idempotenti: la stessa entità/relazione menzionata più volte non duplica)

Test: `tests/test_canonical_mirror.py` — chiama il tool vero, verifica i
count del mirror e che l'entità/relazione sia arrivata su Neo4j via il worker.

## Non ancora fatto

- **cutover** — rendere il canonical autoritativo e spegnere `store.py` /
  il path Mem0 diretto in `semantic_store.py` / `episodic_store.py`.
  Poi `rm -rf data/knowledge_graph/`
- procedural memory canonical (playbook appresi, P7)
- gateway INV-9 (`workspace_read` / `graph_retrieve` / `memory_search`) —
  oggi la lettura passa ancora dal vecchio store
- lato retrieval Neo4j via LlamaIndex `Neo4jPropertyGraphStore`
