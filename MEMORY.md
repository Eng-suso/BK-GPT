# DeliR Agent Memory

## 2026-09-03 - Deployment and multi-tenancy handoff start

User request:
- Find the file titled `DeliR - Deployment & Multi-Tenancy`.
- Follow it precisely.
- Record every action in this `MEMORY.md` so another agent can continue.

Actions completed:
- Loaded project-local skill `.agents/skills/delir-enterprise-delivery/SKILL.md`.
- Located the handoff file at `docs/deployment-and-tenancy.md`.
- Confirmed README links to `docs/deployment-and-tenancy.md` as the active deployment and multi-tenancy handoff document.
- Read `docs/deployment-and-tenancy.md` in full.
- Checked for an existing root `memory.md`; none existed before this file was created.
- Checked git status before editing. The worktree already had multiple modified/untracked files, including `docs/deployment-and-tenancy.md`; those were treated as pre-existing user/agent changes and were not reverted.
- User clarified the intended handoff filename is `MEMORY.md`; repository search found no existing tracked `MEMORY.md`, so this file was renamed from `memory.md` to `MEMORY.md`.
- User asked what "specifica reale" means for the Oracle A1 VM blocker.
- User confirmed blocker 3: staging deploy trigger policy is approved as proposed.
- Attempted to update `docs/deployment-and-tenancy.md`; first patch did not apply because the file contains mojibake/encoding artifacts around symbols. Will patch using stable ASCII context.
- Updated `docs/deployment-and-tenancy.md` successfully using the real UTF-8 symbols: current action now says 2 remaining blockers, blocker 3 is marked confirmed, and changelog has a 2026-09-03 Codex entry.

Current state from `docs/deployment-and-tenancy.md`:
- Track A, infra hardening and deploy, is not started.
- Track B, tenant boundary end-to-end, is not started.
- The document currently says the current action is to resolve blockers first. After the user confirmation, only two blockers remain open.
- The document explicitly says no technical step starts before those blockers are closed.

Blocking questions for Sohayb:
- VM Oracle A1: confirm the real VM shape from OCI console, meaning actual OCPU count, RAM, shape name, architecture, boot volume/storage, OS image, whether the VM is Always Free or trial/paid, and whether the data stack in `ops/docker-compose.yml` is already running or greenfield.
- Cloudflare/domain: provide the domain name and confirm DNS nameservers are or will be on Cloudflare.
- Staging deploy trigger: resolved. Sohayb confirmed the proposed policy: `develop` deploys staging, PR label `deploy-staging` deploys staging on demand, `main` plus green CI plus approval deploys prod.

Next allowed actions after blockers are answered:
- Track A can start at A1: Cloudflare Tunnel plus closing OCI inbound ports.
- Track B can start at B1: Supabase ES256 auth project, JWT verifier, and production startup guard.

Important constraints to preserve:
- Do not store secrets, credentials, tokens, private keys, raw client data, health data, banking data, or non-anonymized PII in this file.
- Do not begin A1/B1 implementation until the three blocker decisions above are supplied or explicitly waived by Sohayb.
- When a step is completed in `docs/deployment-and-tenancy.md`, update that document exactly as it instructs: checkbox/status, `Stato attuale`, `PROSSIMO STEP`, step notes, and changelog.

## 2026-09-17 - Next-step clarification

- Sohayb asked for the next actions step by step.
- Re-read the project delivery skill, `MEMORY.md`, and the blocker/next-step sections of `docs/deployment-and-tenancy.md`.
- Confirmed blocker 3 (staging deploy trigger) is resolved; blockers 1 (Oracle A1 VM and data stack status) and 2 (domain/Cloudflare nameservers) remain open.
- No infrastructure or application changes were made in this turn. Next: obtain those two confirmations, record them in this file and the handoff document, then begin A1 and B1 as directed by the handoff.

## 2026-09-17 - Read-only tenant isolation review

- Sohayb asked whether the proposed JWT -> membership -> tenant context -> all stores/workers isolation is already covered, without changing code.
- Read-only inspection of auth, settings, canonical RLS, workspace, memory, workers, checkpoints, tests, and the deployment handoff. No application code or tests changed or run.
- Verdict: Track B is partially scaffolded but end-to-end tenant authorization is NOT implemented; pilot-grade cross-tenant isolation cannot be claimed.
- Auth: `backend/security.py:76-113` uses one shared bearer token (or auth disabled by default) and gets tenant/user from request headers; no verified Supabase JWT or membership lookup found. `backend/settings.py:127` defaults auth off.
- Canonical: `backend/db/session.py:60-90` sets RLS GUCs and migrations/versions/0005_rls_policies.py defines tenant policies; `tests/test_canonical_rls.py` has cross-tenant tests. These controls depend on a trustworthy consultant ID upstream.
- Workspace: tenant_id filters exist in `backend/workspace_database.py` and `backend/database.py`, but no workspace RLS found. `backend/database.py:18` uses a bare thread_id primary key. `backend/agent_checkpoint.py` has no tenant context and `backend/services/agent_runtime.py:264-265` derives checkpoint key only from scope_key and thread_id.
- Memory: `backend/memory/scope.py:115`, `backend/memory/semantic/semantic_store.py`, and `backend/workers/ingest_worker.py:38-39` still use default_consultant_id. `backend/memory/gateway.py:827-837` falls back to global mem0_user_id for the default consultant. Mem0 searches also occur in `backend/memory/forget.py:220` and `backend/memory/semantic/semantic_store.py:295`, outside the gateway read path.
- Workers: graph/mem0 queues carry materialized payloads, but ingest worker drains only the default consultant. End-to-end tenant propagation for all jobs is unproven.
- Tests: `tests/test_app.py:121-142` checks chat visibility across two headers with the same shared token; this does not verify distinct authenticated organizations. No full A/B endpoint + retrieval isolation suite found.
- The infrastructure blockers in the handoff remain unchanged; this was an audit only.

## 2026-09-17 - Track B target design discussion

- Sohayb requested a system-design diagram, rationale, and candid assessment of his engineering approach.
- Re-read B1-B8 in `docs/deployment-and-tenancy.md`; checked official Supabase Auth/JWT, OWASP multi-tenant, and PostgreSQL RLS documentation for the design explanation.
- Target design explained: Supabase JWT verified by FastAPI; JWT `sub` maps to local user and active memberships; optional tenant header selects only an authorized organization; server creates AuthPrincipal with org/role/consultant context; canonical and workspace Postgres enforce RLS; Mem0 reads use org-derived namespace via gateway; Neo4j retrieval is scoped and hydrated through canonical; queue rows and workers carry org context; LangGraph checkpoint key includes org; cross-tenant tests cover API/retrieval/jobs/checkpoints.
- Distinguish target architecture from current implementation: Track B steps remain unchecked and this conversation did not close blockers or authorize deployment. No application code was changed.

## 2026-09-17 - Component and API communication design

- Sohayb requested the full component system design: frontend, backend, API requests, and how they communicate.
- Re-read target topology and codebase snapshot in `docs/deployment-and-tenancy.md`; inspected frontend API/security/HTTP/chat streaming references and backend routes/lifespan.
- Design to communicate: browser loads React/Vite static assets from Vercel; browser logs in with Supabase Auth; frontend calls FastAPI over HTTPS through Cloudflare edge -> named Tunnel -> Kamal proxy -> VM; backend verifies JWT, resolves memberships, authorizes tenant and role; backend accesses canonical/workspace/mem0 Postgres, Neo4j projection, OpenAI, Prosimos; queues carry tenant context to workers; chat response streams over authenticated HTTP fetch (current client describes NDJSON), live audio uses WebSocket and needs a separate secure browser-compatible auth design. No direct browser-to-datastore calls.
- Distinguish current vs target: current frontend has bundled shared API/admin token configuration and websocket URL query token; current backend uses shared token/header tenant. Vercel/Tunnel/Kamal, Supabase JWT/membership, workspace RLS and end-to-end tenant-aware workers are planned steps, not completed deployment.
- No application code was changed; open Oracle VM and Cloudflare domain blockers remain open.
