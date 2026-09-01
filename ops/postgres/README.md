# Postgres canonical — DeliR

Il DB autoritativo del piano "Cervello DeliR" (INV-1). Gira in un container
sulla stessa macchina del backend; nel deploy finale (Oracle Free VM) resta
sulla rete docker interna, mai esposto (INV-3 / INV-9).

## Avvio

```bash
cd ops/postgres
cp .env.example .env          # cambia TUTTE le password
docker compose up -d
```

Il primo avvio esegue `init/00-bootstrap.sh` come superuser: crea i tre ruoli
applicativi e abilita `vector` + `pg_trgm`. Gira una sola volta per volume — per
rifarlo: `docker compose down -v && docker compose up -d`.

## Ruoli (INV-6)

| Ruolo | Uso | Privilegi |
|---|---|---|
| `delir_super` | solo entrypoint + bootstrap | superuser (mai usato dall'app) |
| `delir_migrator` | Alembic | owner dello schema `public`, no `CREATEROLE` |
| `delir_app` | backend | solo `SELECT/INSERT/UPDATE/DELETE`, `NOBYPASSRLS`, non-owner |
| `delir_worker` | worker outbox | solo `SELECT/UPDATE` su `graph_outbox` + `mem0_projection_log` (dalla 0004) |

`delir_app` non possiede le tabelle, quindi `FORCE ROW LEVEL SECURITY` (dalla
0005) si applica anche a lui.

## Migration

Le migration sono scritte a mano con `op.execute()` (ruoli, RLS, policy, funzioni,
generated columns, pgvector non si modellano con l'autogenerate). Girano SEMPRE
come `delir_migrator`.

```bash
# dalla root del repo, con canonical_migrator_url in .env oppure in env:
export CANONICAL_MIGRATOR_URL="postgresql+psycopg://delir_migrator:<pw>@127.0.0.1:55432/delir"
uv run alembic upgrade head
uv run alembic downgrade base     # reversibile
```

## Config app (`.env` root)

```
CANONICAL_DATABASE_URL=postgresql+psycopg://delir_app:<pw>@127.0.0.1:55432/delir
CANONICAL_MIGRATOR_URL=postgresql+psycopg://delir_migrator:<pw>@127.0.0.1:55432/delir
CANONICAL_WORKER_URL=postgresql+psycopg://delir_worker:<pw>@127.0.0.1:55432/delir
```

L'app tocca il DB solo via `backend.db.canonical_session(consultant_id, client_id)`,
che apre la transazione impostando il contesto RLS.

## Stato

- **0001** — funzioni di contesto (`app_consultant_id`, `app_client_id`),
  `set_updated_at`, backbone `consultant → client → project → process`, grant
  `delir_app`. ✅
- 0002 — `kg_source`, `kg_chunk` (pgvector). _da fare_
- 0003 — `semantic_memory` / `episodic_memory` / `procedural_memory` + lifecycle. _da fare_
- 0004 — `graph_outbox` + `mem0_projection_log` + grant worker. _da fare_
- 0005 — policy RLS su tutte le tabelle tenant + test CI di isolamento. _da fare_
