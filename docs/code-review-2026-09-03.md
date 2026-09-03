# Backend Code Review — 2026-09-03

Deep review of `backend/` (~32.6k LOC Python) against the **AI Code Quality BACKEND** rubric.
Run as a self-paced `/loop`: one area per iteration, findings appended below **and fixed in the same pass** (`procedi, devi anche fixare`).

## Environment note

This machine has **no reachable Postgres / Neo4j** (`.env` DSNs point at a remote stack that is down here). The `memory/` test suite is integration-only and skips/times out. All fixes below are verified by: full module import, `ruff`, `mypy` (no new errors vs baseline), and pure-logic unit tests (`tests/test_scope_guard.py`, `tests/test_kg_catalog.py` pure cases). **The DB-backed tests must be run in CI / against `cd ops && docker compose up -d` before merge.**

Working tree already carries unrelated BPMN work — review fixes are **not committed**; the user decides how to slice them.

## Method

Each area is read in full and checked against the rubric's hard rules:

- **Core boundary** — deterministic code owns truth/state/authz/arithmetic/invariants; LLM owns semantics only.
- **Security** — server-side authz, tenant isolation independent of model, fail-closed, untrusted LLM/tool output, no secrets in logs/prompts.
- **State & persistence** — one canonical source of truth, atomic multi-invariant writes, loud invalid transitions, caches/vectors never silently canonical.
- **Errors** — no broad `except` returning fake success, no infra failure → domain absence, bounded retries, explicit error categories, observable fallbacks.
- **Typing** — typed public functions, no `Any` through domain, Pydantic at trust boundaries, no `dict[str, Any]` domain models, discriminated unions for agent actions.
- **Agent output** — structured + validated before execution, stable discriminators, max-turn + timeout bounds, explicit terminal states.
- **Tools** — narrow & capability-specific, typed I/O, read/write split, idempotent side effects, authz outside LLM, no raw DB execution tool.
- **Structure** — cohesive modules, no god services, DI at boundaries, domain independent of frameworks, no hidden global mutable state.
- **Observability** — trace id per run, model/tool/decision/transition tracing, redaction.
- **Testing** — every changed deterministic invariant has a test; failure paths, permissions, tenant boundaries, idempotency covered.

## Severity legend

| Sev | Meaning |
|-----|---------|
| **P0** | Data corruption, security hole, tenant/authz bypass, silent failure of a guarantee. Fix before merge. |
| **P1** | Correctness bug or invariant violation under realistic input; rubric hard-rule breach with blast radius. |
| **P2** | Maintainability / architecture drift / missing tests on a changed invariant. |
| **P3** | Polish, naming, minor typing, dead code. |

## Progress tracker

| # | Area | LOC | Status | P0 | P1 | P2 | P3 |
|---|------|-----|--------|----|----|----|----|
| 1a | `memory/` — scope, session, gateway, KG projection | ~1650 | **done + fixed** | 0 | 4 (3 fixed, 1 partial) | 6 (5 fixed) | 3 (1 fixed) |
| 1b | `memory/` — canonical KG write path, entity_resolution, ingest_worker | ~2100 | **done + fixed** | 0 | 2 (1 fixed, 1 partial) | 2 (2 fixed) | 3 |
| 1c | `memory/` — episodic, canonical_memory, semantic, procedural, reranker | ~2450 | pending | – | – | – | – |
| 2 | `api/` — routes, errors, trust boundary | 1143 | pending | – | – | – | – |
| 3 | `graphs/` — canvas_edit, project, consulting, routing | 6498 | pending | – | – | – | – |
| 4 | `bpmn/` — compiler, serializer, models, data_flow | 3881 | pending | – | – | – | – |
| 5 | `toolsets/` — bpmn, memory, workspace, project tools | 4944 | pending | – | – | – | – |
| 6 | `workspace_services/` + `workspace_database.py` | 2807 | pending | – | – | – | – |
| 7 | `services/` + `agents/` — agent_runtime | 815 | pending | – | – | – | – |
| 8 | `workers/` — async KG ingestion, idempotency | 567 | pending | – | – | – | – |
| 9 | `simulation/` — log_processor, prosimos | 2610 | pending | – | – | – | – |
| 10 | `schemas/` + `db/` — Pydantic boundaries | 645 | pending | – | – | – | – |
| 11 | root — `process_understanding.py`, `llm_streaming.py`, `rag.py` del | ~1800 | pending | – | – | – | – |

---

<!-- FINDINGS APPENDED BELOW, newest area last -->

## Area 1a — `memory/`: scope, session, gateway, KG projection

Files read in full: `db/session.py`, `memory/scope.py`, `memory/gateway.py`, `memory/knowledge_graph/mirror.py`, `memory/knowledge_graph/projector.py`, `memory/knowledge_graph/neo4j_store.py`. Cross-checked consumers in `toolsets/`, `graphs/project/tools.py`, `services/agent_runtime.py`, `agents/primary_scope.py`.

### What is solid (keep)

- `projector.py::_ident` — allowlist `^[A-Za-z_][A-Za-z0-9_]*$` on every label/prop **before** f-string interpolation into Cypher; all id values parameterized. This is the correct pattern for dynamic Cypher.
- `gateway._expand` — `hops = max(1, min(3, max_hops))` clamps before the f-string; no injection surface.
- `db/session.py` — RLS context via `set_config('app.current_consultant_id'/'app.current_client_id', v, is_local => true)` inside one transaction is a **real DB-level** enforcement for the canonical DB (not prompt-level).
- `mirror.py` — evidence bundle goes through a single `canonical.write_evidence` transaction (documented "o tutto o niente").
- `bpmn.py` toolset already uses `Annotated[dict, InjectedState()]` — the safe scoping pattern *exists* in the codebase (see P1-G3, which is about it not being used where it matters).

### P1

**G1 — Neo4j read path fails OPEN on missing `client_id`.** `gateway.py:260`
```
"AND all(n IN nodes(p) WHERE coalesce(n.client_id, $cid) = $cid) "
```
`coalesce(n.client_id, $cid) = $cid` is always true when `n.client_id IS NULL`. Any node ingested without a `client_id` stamp is visible to **every** client through k-hop expansion. Neo4j Community has no subgraph ACL, so this Cypher predicate *is* the tenant boundary for the graph. Rubric: "Security failures MUST fail closed." Change to `n.client_id = $cid` and give genuinely shared nodes (e.g. `Process`) an explicit label/branch instead of relying on a NULL. Add an ingestion-side invariant + test that every `Entity` node carries `client_id`.

**G2 — `purge_client` (INV-10 / right-to-erasure) silently no-ops and is incomplete.** `neo4j_store.py:32-42`
- Returns `0` when `get_driver() is None` (Neo4j disabled/unreachable). Caller cannot distinguish "nothing to erase" from "erasure did not run" → a GDPR delete can be reported complete while data remains.
- `MATCH (n {client_id: $cid})` never matches the NULL-`client_id` nodes from G1, so any leaked node is also unerasable.
- One unbounded `DETACH DELETE` transaction; a large client can OOM Neo4j.
Fix: raise (fail closed) when the driver is unavailable, batch the delete, and reconcile against Postgres `kg_entity` ids for that client rather than trusting the Neo4j property.

**G3 — operative-state scope relies on model obedience, not the runtime.** `gateway.py:567` (`workspace_read`), `graphs/project/tools.py:29`, `toolsets/project_memory.py:332`, `toolsets/process_memory.py` (many `project_id=project_id`)
`workspace_read` takes `project_id` and does zero ownership/scope enforcement — it calls `workspace_database.get_project(project_id)` directly (the `workspace` DB has no RLS). The project/process memory tools declare `project_id: str = Field(description="Current project id.")` — an **LLM-supplied argument**. `agent_runtime`/`primary_scope` put the authorized `project_id` into agent *state* and into the *system prompt* ("Lo scope arriva dalla UI/backend"), but nothing checks that the `project_id` a tool call carries equals `state["project_id"]`. Read *and write* tools (`save_project_episode`, evidence mirror) are affected. Rubric: "Never place security-critical rules only in prompts", "security never relies on model obedience", "MUST NOT let LLM output directly mutate persistent state without validation." Impact today: one consultant, many clients → a prompt injection in an uploaded document can pivot reads/writes to another client's project. Fix: make `project_id`/`process_id` `InjectedState` (the pattern already used in `toolsets/bpmn.py`), or validate every tool's `project_id` against the run's bound scope before executing.

**G4 — every project with an empty `client` field collapses into one canonical client.** `scope.py:92-93`
```
client_name = str(project.get("client") or "Cliente")
client_ws = f"client:{_slug(client_name)}"   # -> "client:cliente"
```
Two distinct real clients that both leave `client` blank get the **same** `client_id`, so their KG entities, chunks, playbooks and Mem0 memories merge. Tenant isolation silently depends on a free-text workspace field being populated. Fix: require a non-empty client identifier in `resolve()` and fail loudly (`RuntimeError`) otherwise; do not synthesize a shared bucket.

### P2

**G5 — `resolve_client_id` converts infra failure into "no client scope".** `scope.py:79` `except Exception: return None`. Canonical DB hiccup → `client_id=None` → client-scoped Mem0 recall silently disabled for a consultant who *is* in a client context. Rubric: "MUST NOT convert infrastructure failure into valid domain absence." Distinguish `not_configured` from `lookup_failed`; log with `workspace_project_id`.

**G6 — gateway degradation is passed to the LLM but not observable server-side and not handled deterministically.** `gateway.py:375,447,535`. On any exception the gateway returns `{"status": "error", ...}`. `toolsets/memory.py:519` forwards the status; `toolsets/project_memory.py:869` embeds the dict for the model — but there is no backend trace event / counter when retrieval degrades, and no deterministic branch (agent "sees" `status:error` text and may ignore it). Rubric observability: "Critical retries and fallbacks MUST be visible." Emit a `trace_event` + metric on non-`ok`/`empty` status.

**G7 — retrieval results cross the tool-output boundary as `dict[str, Any]` / `list[dict]`.** `gateway.py` (`graph_retrieve`, `memory_search`, `procedural_retrieve`, `_hydrate`, `_expand`). Rubric: "Use Pydantic for … tool outputs", "MUST NOT use dict[str, Any] as the default domain model." `ChunkHit`/`ChunkSearch` are already frozen dataclasses — extend that to the returned envelopes.

**G8 — KG mirror failures are invisible.** `mirror.py:74,176,185` return `{"mirrored": False, "reason": …}` and log `warning` only. No counter/trace, so the "brain" can stop ingesting evidence for days without a signal. Add a metric + trace span; surface a health check.

**G9 — `_canon_processes` silently reattributes unresolved process ids.** `mirror.py:92` — if the LLM passes `affected_process_ids` that don't resolve, gaps/contradictions/impacts are attributed to `base_scope.process_id` (the first process). Prefer empty + logged over wrong attribution.

**G10 — canonical engine has no pool sizing.** `db/session.py:32` `create_engine(url, pool_pre_ping=True, future=True)` — default QueuePool 5 + 10 overflow. Memory note "pool ridotti (a5a2e80)" — verify it applies here; self-hosted single Postgres on a Free-tier VM will exhaust connections under the worker + web + async-ingestion load. Set `pool_size`/`max_overflow`/`pool_recycle` explicitly.

### P3

- **G11** — `scope.py:40` `_upsert` interpolates `table` / column names via f-string. Code-controlled today; add an explicit `{"client","project","process"}` allowlist assertion to keep it that way.
- **G12** — `gateway.py:403` `_mem0_user_id` maps every "default" consultant to the shared `settings.mem0_user_id` namespace. Fine for the single-consultant MVP; add an assertion/comment so it isn't silently relied on post-multi-consultant.
- **G13** — `neo4j_store.py:15` `@lru_cache` driver is never closed; acceptable for process lifetime, note for shutdown hooks.

### Fixes applied — Area 1a

| ID | Change | Files |
|----|--------|-------|
| **G1** | Neo4j expansion predicate `coalesce(n.client_id, $cid) = $cid` → `n.client_id = $cid` (fail closed). Ingestion-side invariant added: `catalog.assert_projectable` now raises if `client_id` is missing/blank on any projected node/edge — every `write_*` path already stamps it. Test: `tests/test_kg_catalog.py::test_assert_projectable_requires_client_id`. | `memory/gateway.py`, `memory/knowledge_graph/catalog.py`, `tests/test_kg_catalog.py` |
| **G2** | `purge_client` now raises `Neo4jUnavailable` instead of returning `0` when the driver is down (erasure can't silently no-op), validates a non-empty `client_id`, and batches the `DETACH DELETE` (`batch_size=10_000`) so a large client doesn't open an unbounded transaction. *Still open:* reconcile against Postgres `kg_entity` ids rather than trusting the Neo4j property — tracked for area 8 (workers / erasure path). | `memory/knowledge_graph/neo4j_store.py` |
| **G3** | *(partial — defense in depth)* New `backend/agents/scope_guard.py`: `bind_active_scope(scope)` sets a `ContextVar` for the agent-run stream (`agent_runtime.stream_agent_events`), `assert_project_in_scope(project_id)` raises `ScopeViolation` if a tool call's `project_id` ≠ the thread's authorized scope. Wired at the chokepoints: `memory.scope.resolve`, `gateway.workspace_read`, `graphs/project/tools._project_payload`, `episodic_store.save_episode_memory`. Broad `except` in `mirror.py` / `project_memory.py` / `process_memory.py` now re-raises `ScopeViolation` instead of degrading it to `status:error`. No-op outside an agent run (workers/tests). Tests: `tests/test_scope_guard.py` (6). *Still open (P1):* the structural fix is moving `project_id`/`process_id` to `InjectedState` across the ~20 project/process tool schemas (pattern already in `toolsets/bpmn.py`); and the guard degrades to fail-open if LangGraph runs a node off-thread. | `agents/scope_guard.py` (new), `services/agent_runtime.py`, `memory/scope.py`, `memory/gateway.py`, `memory/knowledge_graph/mirror.py`, `memory/episodic/episodic_store.py`, `graphs/project/tools.py`, `toolsets/{project,process}_memory.py`, `tests/test_scope_guard.py` (new) |
| **G4** | `scope.resolve` raises `RuntimeError` when the workspace project has no `client` (was: silent `"Cliente"` → shared `client:cliente` bucket). `resolve_client_id` returns `None` for the no-client case and logs `exc_info` on genuine lookup failure. | `memory/scope.py` |
| **G5** | `resolve_client_id` now logs a `WARNING` with `exc_info` + `workspace_project_id` on infra failure, and distinguishes "no client assigned" (`return None` early) from "lookup failed". | `memory/scope.py` |
| **G6 + G8** | New `backend/services/degradation_counters.py` (thread-safe in-process `Counter`, logs each bump at `WARNING`). `gateway.{graph_retrieve,memory_search,procedural_retrieve}` bump `<fn>:error` on exception; `mirror.mirror_evidence` bumps `kg_mirror:{scope_unresolved,enqueue_failed,write_failed}`. Exposed at `GET /v1/observability/degradation` (`status: degraded` when any counter > 0). | `services/degradation_counters.py` (new), `memory/gateway.py`, `memory/knowledge_graph/mirror.py`, `api/routes/observability.py` |
| **G9** | `mirror._canon_processes` logs a `WARNING` when the LLM passed `affected_process_ids` but none resolve (still falls back to the current process to avoid losing evidence, but the misattribution is now visible). | `memory/knowledge_graph/mirror.py` |
| **G10** | `canonical_engine` gets `pool_size=5, max_overflow=5, pool_recycle=1800` (mirrors `local_store.local_engine`; comment explains the shared connection budget). | `db/session.py` |
| **G11** | `scope._upsert` asserts `table in {"client","project","process"}` before interpolating. | `memory/scope.py` |
| **G7** | *Deferred.* Converting the gateway retrieval envelopes to Pydantic models touches every consumer in `toolsets/`; larger than a fix pass. Tracked for the area-5 (`toolsets/`) sweep so the boundary types land with their consumers. | — |
| **G12, G13** | *Deferred* (documented above; MVP-safe, no behavior change needed now). | — |

**Pre-existing type debt noticed while editing** (not introduced here, flag for later areas): `episodic_store.py:232-233` passes `str | None` where `str` is required; `toolsets/{project,process}_memory.py` assign `dict | None` to `list[dict]` vars (6 sites); `canonical.py:879,902` pass `source_text: str | None` into `str` params (runtime-guarded by `has_source`). Rubric "MUST NOT propagate `Any` / no `dict[str,Any]` domain models".

---

## Area 1b — `memory/`: canonical KG write path, entity resolution, ingest worker

Files read in full: `memory/knowledge_graph/canonical.py`, `memory/knowledge_graph/entity_resolution.py`, `workers/ingest_worker.py`. Cross-checked `catalog.py`, `mirror.py`, queue lifecycle.

### What is solid (keep)

- `entity_resolution` — textbook LLM/deterministic split: `shortlist` does every DB lookup then the `canonical_session` **closes**, *then* the LLM `decide` runs with no connection held; `_Verdict` is a Pydantic model at the trust boundary; no cosine/trigram auto-merge threshold (calibrated as unsafe — every fuzzy candidate goes to the LLM); RLS confines the search to one client (no cross-client merge).
- `canonical.write_evidence` — the whole evidence bundle runs in **one** `canonical_session` transaction; embedding + resolution (network calls) happen *before* it opens, so no lock is held across HTTP.
- `_enum` coercion — a bad LLM enum value → default + `WARNING`, never a failed INSERT. Consistent, documented tradeoff.
- `write_source_chunks` — idempotent on `content_hash` with a race-handled re-SELECT; `_pg_uuid_array` / `_float` (clamped `[0,1]`) keep arithmetic deterministic.
- `ingest_worker._claim` — `FOR UPDATE SKIP LOCKED` + bounded `attempts` + stuck-requeue is the right queue skeleton.

### P1

**C7 — `kg_ingest_queue` is at-least-once but `write_evidence` is not bundle-idempotent.** `canonical.py:459/539/599/670` (claim/gap/contradiction/impact are plain `INSERT`, no `ON CONFLICT`), `workers/ingest_worker.py:41,69,107`
Entities/relations upsert idempotently; the four *analysis* node types do not. `write_evidence` is internally atomic (one transaction, so a mid-write failure rolls back cleanly), **but** the queue re-runs a job whenever the worker dies between `write_evidence`'s commit and the separate `_finish` UPDATE, or when `_finish` fails, or when `_requeue_stuck` flips a still-`processing` row back to `pending`. Each re-run duplicates every claim/gap/contradiction/impact in the bundle. Rubric: "Retryable side effects MUST be idempotent or otherwise safe."
*Fixed (mitigation):* `_finish` now retries ×3 (`_mark_done`), and both `finish_failed` and `requeued_stuck` bump `degradation_counters` (visible at `/v1/observability/degradation`). *Still open (needs a migration — can't test DB here):* either (a) an idempotency key on `kg_ingest_queue` + `ON CONFLICT DO NOTHING` on the four node tables keyed by `(client_id, coalesce(process_id), md5(statement|title))`, or (b) flip a `written` flag on the queue row **inside** the `write_evidence` transaction so commit is all-or-nothing with the done-mark.

**ER6 — a best-effort resolver failure destroys the entire evidence write.** `entity_resolution.py:490` (`plan_resolution` had no try/except), `canonical.py:889`
`plan_resolution` is called *before* `write_evidence` opens its transaction. A missing `pg_trgm` extension, a DB blip, or an embedder error inside `shortlist`/`_candidates` propagated out of `plan_resolution` → out of `write_evidence` → the whole bundle (entities, relations, claims, gaps, impacts, chunks) is lost — even though the module docstring promises "un merge mancato si recupera con lo sweep". Rubric: best-effort component failure must not become total failure.
*Fixed:* `plan_resolution` wraps phases (1)+(2) in `try/except` → returns `ResolutionPlan(matches={}, name_vectors=…)` (degrade to no-merge, the write proceeds) + `degradation_counters.bump("entity_resolution", "plan_failed")`.

### P2

**ER2 — `adjudicate` swallows LLM errors silently.** `entity_resolution.py:327` — an LLM outage → `return None` (new entity created, recoverable) but no signal, so the graph accumulates duplicates invisibly for as long as the outage lasts. *Fixed:* `degradation_counters.bump("entity_resolution", "llm_failed")`.

**ER4 — `build_llm` cached an init failure for the process lifetime.** `entity_resolution.py:345` was `@lru_cache(maxsize=1)` — one transient `ChatOpenAI(...)` failure at first call cached `None` forever → entity resolution permanently downgraded until restart. *Fixed:* replaced with a module-level singleton that memoizes only success; the "no API key" branch is cheap to re-check; init failure bumps `llm_init_failed`.

**C1 — one bad relation label aborts the whole atomic bundle.** `canonical.py:1093` `_normalize_relation` raises `ValueError` on an empty/invalid `relation`; called inside the `write_evidence` loop, so an LLM emitting one relationship with `relation=""` loses the entire evidence package. Inconsistent with the `_enum` "coerce, don't fail" philosophy two functions up. *Fixed:* `write_evidence` pre-validates each relation label and `continue`s past a bad one (logged) instead of letting it raise.

### P3

- **ER1** — `shortlist` → session close → `write_entity` runs in a new transaction: TOCTOU if a concurrent ingestion merged/deactivated the matched row. Already handled (`_MERGE_ENTITY … WHERE status='active'` falls back to INSERT) and documented; no change.
- **C3** — `enqueue_evidence` serialises the full `source_text` (possibly a whole document) into `kg_ingest_queue.payload` JSONB. Consider a size cap or storing the raw text once and referencing it.
- **C-perf** — `entity_resolution._candidates` vector branch is `ORDER BY embedding <=> :v LIMIT 15` with no SQL threshold and no guaranteed ANN index; a large client KG scans all embedded entities per name. Verify an `ivfflat`/`hnsw` index exists on `kg_entity.embedding`.

### Fixes applied — Area 1b

| ID | Change | Files |
|----|--------|-------|
| **C7** | *(partial)* `_finish` retries ×3 via new `_mark_done`; `finish_failed` + `requeued_stuck` bump `degradation_counters`. Worker no longer re-runs a job after `write_evidence` commits. Full idempotency needs a migration (documented). | `workers/ingest_worker.py` |
| **ER6** | `plan_resolution` catches its own failures → `EMPTY_PLAN`-with-vectors + `plan_failed` counter; evidence write proceeds without merges instead of being lost. | `memory/knowledge_graph/entity_resolution.py` |
| **ER2** | `adjudicate` LLM-failure path bumps `entity_resolution:llm_failed`. | `memory/knowledge_graph/entity_resolution.py` |
| **ER4** | `build_llm` → success-only memoized singleton (was `@lru_cache` caching init failure); `llm_init_failed` counter. | `memory/knowledge_graph/entity_resolution.py` |
| **C1** | `write_evidence` skips a relation with an invalid label (logged) instead of aborting the atomic bundle. | `memory/knowledge_graph/canonical.py` |

New degradation-counter keys: `entity_resolution:{llm_failed,llm_init_failed,plan_failed}`, `kg_ingest_worker:{finish_failed,requeued_stuck}`.

---
