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
