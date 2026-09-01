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
- `postgres/init/02-workspace.sh` — ruolo `delir_workspace`, database
  `workspace` che possiede (stato operativo: clienti/progetti/processi/BPMN/
  simulazioni + cronologia chat + indice memoria episodica)

Per rieseguirli: `docker compose down -v && docker compose up -d`.

## Ruoli Postgres (INV-6)

| Ruolo | Uso | Privilegi |
|---|---|---|
| `delir_super` | solo entrypoint + bootstrap | superuser (mai usato dall'app) |
| `delir_migrator` | Alembic | owner schema `public`, `NOCREATEROLE` |
| `delir_app` | backend | solo DML, `NOBYPASSRLS`, non-owner; su `graph_outbox`/`mem0_projection_log` solo `INSERT` |
| `delir_worker` | worker outbox | solo `SELECT/UPDATE` sulle due code |
| `delir_mem0` | Mem0 OSS | owner del database `mem0` (isolato dallo schema canonical) |
| `delir_workspace` | stato operativo | owner del database `workspace` (isolato: churn alto, niente RLS) |

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
WORKSPACE_DATABASE_URL=postgresql+psycopg://delir_workspace:<pw>@127.0.0.1:55432/workspace
CANONICAL_DATABASE_URL=postgresql+psycopg://delir_app:<pw>@127.0.0.1:55432/delir
CANONICAL_MIGRATOR_URL=postgresql+psycopg://delir_migrator:<pw>@127.0.0.1:55432/delir
CANONICAL_WORKER_URL=postgresql+psycopg://delir_worker:<pw>@127.0.0.1:55432/delir
MEM0_DATABASE_URL=postgresql://delir_mem0:<pw>@127.0.0.1:55432/mem0
MEM0_LLM_MODEL=gpt-4o-mini      # override se il tuo account OpenAI non ce l'ha
NEO4J_PASSWORD=<pw>             # = NEO4J_PASSWORD in ops/.env
```

`WORKSPACE_DATABASE_URL` assente → fallback SQLite in `data/` (solo dev/CI:
SQLite è single-writer, non regge la concorrenza multi-cliente). Migrazione
dei file SQLite esistenti al Postgres:

```bash
WORKSPACE_DATABASE_URL=... uv run python -m scripts.migrate_local_sqlite_to_pg --truncate
```

La custodia grezza degli episodi (`data/episodic/sources/*.md`) è su disco,
non nel DB: su un host nuovo va sincronizzata a parte (`rsync data/episodic/`).

L'app tocca il canonical solo via `backend.db.canonical_session(consultant_id, client_id)`
(imposta il contesto RLS). Mem0 solo via `backend.memory.mem0_client.get_memory()`.

## Stato — schema canonical (migration 0001-0008) ✅

| | |
|---|---|
| 0001 | funzioni contesto `app_consultant_id`/`app_client_id`, `set_updated_at`, backbone `consultant → client → project → process`, grant `delir_app` |
| 0002 | `kg_source` (provenance) · `kg_chunk` (`vector(1536)` + HNSW + tsvector) |
| 0003 | `semantic_memory` / `episodic_memory` / `procedural_memory` — scope `client\|consultant`, lifecycle, `guardrail_status` + gate, provenance |
| 0004 | `graph_outbox` + `mem0_projection_log` (delir_app solo INSERT) + view `v_projection_backlog` |
| 0005 | RLS `ENABLE`+`FORCE` su tenant tables; `consultant` solo `ENABLE` |
| 0006 | catalogo struttura KG L1: `kg_entity` / `kg_relation` / `kg_claim` / `kg_gap` / `kg_contradiction` / `kg_impact` + RLS + trigger. Mappa PG→Neo4j in `backend/memory/knowledge_graph/catalog.py` |
| 0007 | ponte workspace SQLite → canonical (`workspace_id`, seed consulente di default) |
| 0008 | dedup `kg_entity`/`kg_relation` su indice unique PARZIALE `WHERE client_id IS NOT NULL` (fix review) |

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

**Avvio dei worker.** Di default l'app li fa girare in-process: il lifespan
FastAPI avvia due task di background (`backend/workers/supervisor.py`) che
drenano le code, loggano il backlog ogni ~2 min e potano le righe processate
> 14 giorni ogni ora. Nessun processo separato da gestire.

Per scalare / isolarli: `WORKERS_IN_PROCESS=false` + service dedicati.
`FOR UPDATE SKIP LOCKED` rende sicuro anche farli girare in parallelo.

```bash
uv run python -m backend.workers.graph_worker   # loop dedicato
uv run python -m backend.workers.mem0_worker    # loop dedicato
```

**Health + dead-letter.** `GET /v1/observability/queues` → `{pending, stuck}`
per coda (`stuck` = falliti 5 volte). Ispezione / requeue:

```bash
CANONICAL_MIGRATOR_URL=... uv run python -m scripts.queue_admin list
CANONICAL_MIGRATOR_URL=... uv run python -m scripts.queue_admin show <id> [--queue mem0_projection_log]
CANONICAL_MIGRATOR_URL=... uv run python -m scripts.queue_admin requeue-stuck
```

Test: `tests/test_graph_projection.py`, `tests/test_mem0_projection.py`,
`tests/test_queue_supervisor.py`.

## Scrittura KG sul canonical — cutover ✅

`manage_process_evidence` / `save_process_episode` / `index_process_evidence_graph`
/ `manage_project_evidence` scrivono il knowledge graph **solo** sul canonical
Postgres + outbox tramite `backend/memory/knowledge_graph/mirror.py` →
`canonical.write_evidence` (atomico). Il vecchio `store.py` LlamaIndex è
rimosso. Best-effort, mai un'eccezione verso l'agente; il risultato è nel
payload sotto `"canonical_write"`.

- `backend/memory/scope.py` — ponte "project-1"/"proc-1" (workspace SQLite) →
  `client`/`project`/`process` canonical, upsert idempotente su `workspace_id`
  (migration `0007`, che semina anche il consulente unico di default)
- `write_entity` / `write_relation` ora fanno `ON CONFLICT ... DO UPDATE`
  (idempotenti: la stessa entità/relazione menzionata più volte non duplica)

Test: `tests/test_canonical_mirror.py` — chiama il tool vero, verifica i
count del mirror e che l'entità/relazione sia arrivata su Neo4j via il worker.

**Semantic + episodic** (`semantic_store.py` / `episodic_store.py`): la add su
Mem0 resta sincrona e unica (mai due write della stessa memoria); il mirror
scrive la riga `semantic_memory` / `episodic_memory` canonical + una riga di
`mem0_projection_log` **già `applied_at`** con l'`mem0_memory_id` noto — il
worker non deve rifare nulla, è solo audit trail.

**Scope per cliente (INV-13)**: un episodio salvato con `project` risolve il
cliente via `canonical_scope.resolve(project)` e finisce in Mem0 con
`client_id` (uuid canonical) nei metadata + nella riga `episodic_memory` con
`scope='client'`. In lettura `search_episode_memory` / il chat progetto
risolvono il `client_id` (read-only, `canonical_scope.resolve_client_id`) e lo
passano a `gateway.memory_search`: recall = memorie consultant-level + quelle
di quel cliente, mai di altri. Best-effort: senza canonical → consultant-level.
La memoria semantica del consulente resta consultant-level per natura (il
plumbing `client_id` c'è comunque).

Test: `tests/test_semantic_episodic_mirror.py`, `tests/test_client_scoped_recall.py`.
Nota: i test che assertano un marker nel recall Mem0 sono fragili se il DB
`mem0` di dev è pieno di memorie di run precedenti — `TRUNCATE delir_memories,
delir_memories_entities` quando serve.

## Lettura — gateway INV-9 ✅

`backend/memory/gateway.py` è l'unico punto di lettura del cervello. Nessun
tool interroga Neo4j / Postgres-KG / Mem0 direttamente.

- **`graph_retrieve`** (grafo tipizzato, retrieval ibrido P3) — usato da
  `retrieve_process_graph_context` / `retrieve_project_graph_context`:
  (1) seed lessicale su `kg_entity.canonical_name` (RLS per client);
  (2) seed vettoriale — embedding della query → cosine su `kg_chunk` (RLS) →
  `source_id` dei chunk → entità con quella provenance;
  (3) fusione RRF dei due ranking;
  (4) espansione k-hop in Neo4j filtrata per `client_id`;
  (5) idratazione dei nomi da Postgres.
  Payload sotto `"knowledge_graph"` con `matches` (triple) + `chunks`
  (contesto testuale più vicino), status `ok|empty|not_configured|error`.
- **`memory_search`** (recall Mem0) — `semantic_store.search_consultant_memory`
  (e quindi `search_bpmn_preferences`, `episodic_store.search_episode_memory`,
  la route `/memory`) passa da qui. `user_id` Mem0 mappato dal `consultant_id`
  (oggi mono-consulente locale); post-filtro per `client_id` sui metadata: le
  memorie consultant-level restano visibili ovunque, quelle client-scoped solo
  nel loro cliente. Status `ok|empty|not_configured|error`.
- **`workspace_read`** (stato operativo) — snapshot scoped della workspace
  SQLite (SoT operativa, INV-8): project + processi + sources/decisions,
  filtrati per `process_ids` (le righe project-level senza `process_id`
  restano). Usato da `retrieve_project_graph_context` per il grounding.
  Status `ok|not_found`.

Se canonical / Neo4j / Mem0 non sono configurati il gateway torna uno status
esplicito e i tool restano funzionanti sul resto.

Test: `tests/test_gateway.py`, `tests/test_gateway_memory.py`,
`tests/test_gateway_workspace.py`, `tests/test_kg_vector_retrieval.py`.

**Gateway INV-9 completo** (`graph_retrieve` + `memory_search` + `workspace_read`).

## Ingestione vettoriale KG — P3 ✅

Se un tool evidence passa `raw_content`, il mirror lo gira a
`canonical.write_evidence(source_text=...)` che:
- registra una `kg_source` (provenance, dedup su `content_hash`);
- splitta il testo in chunk (~1600 char, overlap 200) e li embedda
  (`backend/memory/embeddings.py`, contract v1 = `text-embedding-3-small` /
  1536, INV-4). Senza `OPENAI_API_KEY` i chunk entrano comunque, `embedding`
  NULL (tsvector di fallback);
- mette il `source_id` nei `source_ids` di ogni nodo scritto (provenance
  che il seed vettoriale usa per risalire dalle chunk alle entità).

`kg_source` / `kg_chunk` sono Postgres-only: NON vengono proiettati su Neo4j
(sono l'indice vettoriale, non struttura del grafo).

## Stato L1 (process-consulting per progetto) — solido ✅

Loop completo e non presidiato: evidence tool → `mirror` → `write_evidence`
(atomico, + `kg_source`/`kg_chunk`) → `graph_outbox` → **worker in-process** →
Neo4j; lettura via `gateway.graph_retrieve` (ibrido lessicale+vettoriale+RRF).
Memoria episodica client-scoped. Backlog visibile, dead-letter ispezionabile,
code potate da sole. Stato operativo su Postgres.

## Non ancora fatto

- `semantic_store.py` / `episodic_store.py`: la add su Mem0 resta autoritativa,
  il canonical è mirror audit-only. Ridurli a canonical-first.
- memoria **semantica** client-scoped (l'episodica c'è; la semantica del
  consulente è consultant-level per natura, manca un writer client-scoped)
- **L2** — metodo cross-progetto + learning loop (procedural candidate →
  validazione → playbook promosso → runtime → feedback). Zero fatto.
- **L3** — flusso di ingestione documenti KB cliente (`kg_source`/`kg_chunk`
  ci sono, manca l'upload → chunk → grafo dedicato)
- reranker sul risultato ibrido (oggi RRF puro, nessun cross-encoder)
- backfill embedding di `kg_entity` (colonna esiste, P2 entity resolution)
- `workspace_id` UNIQUE è globale, non per-consultant (latente multi-tenant)
