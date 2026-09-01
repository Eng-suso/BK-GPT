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

Test: `tests/test_canonical_rls.py` (6 casi, skip senza le due DSN in env).

## Mem0 OSS ✅

`backend/memory/mem0_client.py` — `mem0.Memory` in-process, vector store = db
`mem0` (pgvector), LLM + embedder = OpenAI, telemetria off, `custom_instructions`
per non tradurre. Niente graph store (il grafo è Neo4j). Disattivato in silenzio
se `MEM0_DATABASE_URL` non è configurata.

Scope oggi = consultant-level (`mem0_user_id`). Lo scope per cliente arriva con
la migrazione della memoria canonica (INV-13).

## Non ancora fatto in P0

- worker che drena `graph_outbox` + `mem0_projection_log`
- projection contracts (whitelist campi Neo4j / Mem0) + wiring Neo4j (LlamaIndex)
- P0.5: `kg_entity` / `kg_relation` / `kg_claim` / … + catalogo nodi/archi
