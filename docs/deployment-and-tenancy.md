# DeliR — Deployment & Multi-Tenancy

> **Documento vivo di handoff.** Se sei un agent che riprende questo lavoro:
> leggi nell'ordine **① Stato attuale → ② PROSSIMO STEP → ③ Blocker**, poi la
> sezione della track su cui lavori. Ogni sezione tecnica ha file, criterio di
> accettazione e stato. Non re-derivare il contesto: la sezione **Snapshot
> codebase** in fondo è la fonte di verità sullo stato *as-of*.

Origine: brainstorm architetturale (settembre 2026) tra Sohayb e Claude su come
deployare DeliR in modo che il `main` sia sempre provabile e che l'app regga i
primi 3–5 clienti pilota senza affidarsi a isolamento "per convenzione".

---

## ① Stato attuale

| Track | Cosa | Stato |
|---|---|---|
| **A — Infra hardening + deploy** | tunnel, chiusura porte, Kamal, build GHCR, zero-downtime | ⬜ non iniziata |
| **B — Tenant boundary end-to-end** | Supabase Auth + membership + kill `default_consultant_id` + code/worker tenant-aware + RLS workspace | ⬜ non iniziata |

**Gate cliente #1** = Track B chiusa. Fino ad allora staging/prod possono girare
con token condiviso + Cloudflare Access (allowlist email).

**Le due track sono parallele.** Track A non dipende da Track B.

Legenda stato step: ⬜ non iniziato · 🟡 in corso · ✅ fatto · ⛔ bloccato

---

## ② PROSSIMO STEP

> **Tenere sempre aggiornato.** Quando completi uno step: (1) spunta la checkbox
> nello step, (2) aggiorna la tabella *Stato attuale*, (3) sposta questo
> puntatore allo step successivo, (4) scrivi cosa hai imparato nelle *Note*
> dello step, (5) aggiungi una riga al *Changelog* in fondo.

**AZIONE CORRENTE: risolvere i 2 blocker restanti (sezione ③).** Sono decisioni/verifiche
che spettano a Sohayb, non ad un agent. Nessuno step tecnico parte prima.

Quando i blocker sono chiusi:
- **Track A → step A1** (Cloudflare Tunnel + chiusura porte OCI).
- **Track B → step B1** (progetto Supabase ES256 + JWT verifier + prod-guard).

Si può iniziare **Track A e Track B in parallelo** (agent diversi, file
disgiunti: A tocca `ops/`, `.github/`, `Dockerfile`, `.kamal/`; B tocca
`backend/security.py`, `backend/memory/scope.py`, `backend/workers/`,
`backend/db/`, migrations).

---

## ③ Blocker (decisioni di Sohayb — bloccano l'inizio)

1. **VM Oracle A1 — UNKNOWN.**
   Va guardata la console OCI. *Always Free* garantisce solo **2 OCPU / 12 GB**
   totali di Ampere A1; i 4 OCPU / 24 GB possono essere temporanei (crediti
   trial). **Regola di progetto: PROD deve reggere a 2 OCPU / 12 GB.**
   Conseguenza già decisa: niente 2° Neo4j always-on per lo staging → Neo4j
   staging **on-demand**.
   → *Serve:* specifica reale della VM + se il data stack (`ops/docker-compose.yml`)
   è già su o è greenfield.

2. **Dominio su Cloudflare — UNKNOWN.**
   Cloudflare Tunnel richiede che la zona DNS del dominio sia su Cloudflare (non
   serve trasferire il registrar, basta puntare i nameserver).
   → *Serve:* nome dominio + conferma che i NS vanno/sono su Cloudflare.
   Decisione proposta: `delir.<tld>` FE su Vercel, `api.delir.<tld>` +
   `api-staging.delir.<tld>` via Tunnel.

3. **Trigger deploy staging — CONFERMATO 2026-09-03.**
   Con una sola VM non si vuole un rollout backend ad ogni PR.
   Decisione confermata: `develop` → deploy staging · label `deploy-staging` su PR
   per on-demand · `main` + CI verde + approval → deploy prod.
   → *Stato:* confermato da Sohayb.

---

## Architettura target

```text
                              INTERNET
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
        delir.<tld>  (Vercel)            api.delir.<tld>  (Cloudflare)
        FE statico, React 19/Vite               │ Tunnel (outbound, no inbound)
                 │                               ▼
                 │ login                   cloudflared (VM)
                 ▼                               │
          Supabase Auth  ──── JWT ES256 ─────────┤
          (solo identity)                        ▼
                                           kamal-proxy  (zero-downtime swap)
                                                 │
                                           FastAPI (backend.app:app)
                                          verifica JWT · membership · tenant
                                                 │
                    ┌────────────────────────────┼───────────────────────┐
                    ▼                            ▼                        ▼
             Postgres (pgvector)          Neo4j 5 Community          Prosimos
             canonical + workspace        projection (ricostruibile) stateless, sync
             + checkpoint LangGraph            │
                    │                          │
              graph/ingest/mem0 worker  ───────┘

  STAGING: stessa VM. FastAPI staging + DB `*_staging` (ruoli separati) +
  neo4j-staging ON-DEMAND. api-staging.delir.<tld> dietro Cloudflare Access.

  OCI inbound: 22/80/443/5432/7474/7687/8000 TUTTE CHIUSE.
  Amministrazione: laptop → Tailscale → SSH privato.
```

### Principi non negoziabili

1. **Supabase autentica *chi sei*. DeliR decide *cosa puoi fare*.**
   Authentication (Supabase) e Authorization (FastAPI + membership su Postgres
   Oracle) restano separate.
2. **`X-DeliR-Tenant-ID` = selezione, non autorizzazione.** Il server verifica
   sempre `membership(jwt.sub, tenant)`; il contesto RLS si imposta dalla
   membership *risolta*, mai da un header/param del client.
3. **I job asincroni sono self-describing.** Nessun worker legge
   `settings.default_consultant_id`: il tenant/consultant sta nella riga di coda.
4. **La PROD VM esegue artefatti, non li costruisce.** Build su CI → GHCR → la VM
   fa solo `pull`.
5. **Postgres canonical = fonte di verità del disaster recovery.** Neo4j è
   projection: ricostruibile dal canonical, non entra nel RPO critico.
6. **Un solo failure domain accettato deliberatamente** (VM singola, Postgres
   singolo) per motivi di costo. Scelta razionale per 3–5 pilota, da rivedere
   dopo.

---

## Track A — Infra hardening + deploy

Obiettivo: `main` sempre deployato, zero-downtime, rollback in un comando,
origine privata, nessuna porta inbound sulla VM.

### A1 — Cloudflare Tunnel + chiusura totale inbound OCI  ⬜
- **Cosa:** `cloudflared` come service nel compose della VM (`restart: unless-stopped`,
  **1 replica** — 2× sullo stesso host non è HA, è solo per upgrade senza taglio).
  Ingress: `api.delir.<tld> → http://kamal-proxy:80`,
  `api-staging.delir.<tld> → http://kamal-proxy-staging:80`.
  Poi chiudere su OCI security list + `ufw`: 22, 80, 443, 5432, 7474, 7687, 8000.
- **SSH solo via Tailscale:** installare `tailscaled` sulla VM, `tailscale up`,
  SSH consentito solo dalla tailnet.
- **Cloudflare Access** su `api-staging.*`: policy allowlist email (Zero Trust
  free ≤ 50 utenti).
- **File:** nuovo `ops/docker-compose.prod.yml` (o override), config `cloudflared`
  (`ops/cloudflared/config.yml` + credentials file come secret, **non** in git).
- **Accettazione:** `nmap` dall'esterno non vede nessuna porta aperta;
  `curl https://api.delir.<tld>/health` risponde attraverso il tunnel; SSH
  dall'IP pubblico rifiutato, da Tailscale ok.
- **Note:** _(vuoto)_

### A2 — Dockerfile backend ARM64  ⬜
- **Cosa:** multi-stage. Stage 1 `python:3.14-slim` + `uv sync --locked` (il
  progetto è **solo backend** nell'immagine: il FE sta su Vercel, non serve più
  buildare `frontend/`). Entrypoint: `alembic upgrade head` +
  `alembic -c alembic_workspace.ini upgrade head` **sotto `pg_advisory_lock`**,
  poi `exec uvicorn backend.app:app --host 0.0.0.0 --port 8000`.
  Target platform `linux/arm64`.
- **Disattivare la migrazione allo startup dell'app** in prod/staging: oggi
  `backend/app.py:36` chiama `ensure_schema()` ad ogni boot → durante uno swap
  zero-downtime due container migrano in parallelo. Aggiungere
  `RUN_MIGRATIONS_ON_STARTUP` (default `true` per dev locale, `false` in
  prod/staging); l'entrypoint/hook è l'**unico** migratore.
- **File:** `Dockerfile` (root), `.dockerignore`, `backend/settings.py` (+flag),
  `backend/app.py` (gate su `ensure_schema()`).
- **Accettazione:** `docker build --platform linux/arm64 .` produce immagine che
  parte con DSN validi e serve `/health`; due container avviati insieme non
  vanno in deadlock sulle migration.
- **Note:** _(vuoto)_

### A3 — Health/readiness reale  ⬜
- **Cosa:** `/health` resta liveness povera. Aggiungere `/health/ready` che
  verifica: Postgres canonical + workspace raggiungibili, Alembic a head ( entrambe
  le tracce). Kamal usa `/health/ready` come gate prima dello switch traffico.
- **File:** `backend/app.py` (o `backend/api/routes/observability.py`, che ha già
  `/v1/observability/queues`).
- **Accettazione:** con DB spento `/health/ready` → 503; con DB su e migration a
  head → 200.
- **Note:** _(vuoto)_

### A4 — CI: build immagine → GHCR  ⬜
- **Cosa:** nuovo job in `.github/workflows/ci.yml` (o workflow separato
  `deploy.yml`): `docker buildx` cross-build `linux/arm64` via QEMU, cache layer
  su GHCR, push `ghcr.io/<org>/delir-backend:<sha>` + `:main`. Trigger su push
  `main` e `develop` **dopo** i gate di qualità (`needs: [ci-success]` o
  `workflow_run`).
- **Fallback:** se la build emulata è troppo lenta (qualche dep compila da
  sorgente) → runner GitHub `ubuntu-24.04-arm` (a pagamento, solo minuti build).
  **Mai** build sulla VM di PROD.
- **File:** `.github/workflows/deploy.yml`, secret repo `GHCR_TOKEN`.
- **Accettazione:** push su `main` produce un'immagine ARM64 taggata su GHCR.
- **Note:** _(vuoto)_

### A5 — Kamal 2: prod + staging  ⬜
- **Cosa:** `.kamal/deploy.yml` con destinazioni `production` e `staging`.
  Kamal gestisce **solo** i container app + `kamal-proxy` (lo swap zero-downtime
  + hold delle richieste). Il data stack (`postgres`, `neo4j`, `prosimos`) resta
  compose separato sulla VM (stabile, INV-3). Prosimos condiviso prod/staging
  (stateless). `neo4j-staging` avviato on-demand da un hook `pre-connect`
  (`docker compose start neo4j-staging`), stop schedulato dopo inattività.
  TLS termina all'edge Cloudflare → `kamal-proxy` in HTTP piano, **nessun
  Let's Encrypt sulla VM**.
- **Hook `pre-deploy`:** esegue le migration (vedi A2) sotto advisory lock;
  exit ≠ 0 aborta il deploy. **Disciplina expand/contract obbligatoria:** durante
  lo swap il codice vecchio vede lo schema nuovo per qualche secondo → **mai**
  `DROP COLUMN` / `RENAME` / `ALTER` incompatibile nella migration che precede lo
  swap. Distruttivo = release separata successiva.
- **File:** `.kamal/deploy.yml`, `.kamal/secrets` (da env / vault, **non** git),
  `.kamal/hooks/pre-deploy`.
- **Accettazione:** `kamal deploy` fa rollover senza 5xx visibili;
  `kamal deploy -d staging` colpisce i container/DB staging; `kamal rollback`
  torna alla versione precedente.
- **Note:** _(vuoto)_

### A6 — Deploy da CI  ⬜
- **Cosa:** job `deploy` che, dopo A4, esegue `kamal deploy` (prod su `main` +
  approval) / `kamal deploy -d staging` (`develop` o label). Secret Actions:
  `SSH_PRIVATE_KEY` (VM, via Tailscale o IP), `KAMAL_REGISTRY_PASSWORD`.
- **File:** `.github/workflows/deploy.yml`.
- **Accettazione:** merge su `main` con CI verde → prod aggiornato senza
  intervento manuale; health gate fallito → vecchia versione mantenuta.
- **Note:** _(vuoto)_

### A7 — CORS per le preview Vercel  ⬜
- **Cosa:** `backend/app.py:54` `configured_cors_origins()` accetta solo lista
  esatta. Le preview Vercel hanno URL dinamici. Aggiungere `allow_origin_regex`
  (es. `^https://delir-[a-z0-9-]+\.vercel\.app$`) accanto alla lista esatta per
  prod. Rimuovere `["*"]` quando `delir_auth_enabled` (già così) — ma verificare
  che in prod non sia mai `*`.
- **File:** `backend/app.py`, `backend/settings.py`
  (`delir_cors_allow_origin_regex`).
- **Accettazione:** richiesta da un dominio `*.vercel.app` di preview passa il
  preflight; da un dominio arbitrario no.
- **Note:** _(vuoto)_

### A8 — Backup Postgres off-host + restore testato  ⬜
- **Cosa:** cron notturno sulla VM: `pg_dump` dei **tre** database sullo stesso
  cluster — `delir` (canonical, DR-critico), `workspace` (stato operativo +
  checkpoint LangGraph), `mem0` (vector store Mem0, schema self-managed dalla
  lib) → bucket **OCI Object Storage privato**, server-side encryption, lifecycle
  (retention 30 gg). RPO = 24h (se inaccettabile → dump più frequenti / WAL
  archiving; **decisione da scrivere**). RTO documentato.
  **Restore drill trimestrale** in un DB scratch, non "il dump non ha dato
  errore".
- **Nota Mem0:** anche se OpenAI ri-estrarrebbe i fatti da zero, le memorie già
  consolidate (semantiche + episodiche) sono un asset — il db `mem0` va nel
  backup, non è ricostruibile come Neo4j.
- **File:** `ops/backup/pg_dump.sh`, `ops/backup/README.md` (runbook restore),
  cron entry.
- **Accettazione:** un restore completo in un DB vuoto riproduce lo stato;
  runbook seguito da zero riesce in < RTO dichiarato.
- **Note:** _(vuoto)_

### A9 — Script re-proiezione Neo4j dal canonical  ⬜
- **Cosa:** `scripts/reproject_neo4j_from_canonical.py` — cammina
  `kg_entity` / `kg_relation` / `kg_claim` / `kg_gap` / `kg_contradiction` /
  `kg_impact` del canonical e li MERGE-a su Neo4j (idempotente, per `client_id`).
  Rende vero il principio "Neo4j è disposable". Fino a che non esiste, perdere
  Neo4j = downtime di ricostruzione manuale (0 perdita dati). Ponte intanto:
  `neo4j-admin database dump` **offline** in una maintenance window settimanale
  (Community non ha online backup).
- **File:** `scripts/reproject_neo4j_from_canonical.py`.
- **Accettazione:** `docker compose down neo4j && up -d neo4j && python -m
  scripts.reproject_neo4j_from_canonical` ricostruisce il grafo; `gateway.graph_retrieve`
  torna gli stessi match di prima.
- **Note:** _(vuoto)_

### A10 — Test SSE end-to-end  ⬜
- **Cosa:** test automatico (5–10 min) sul path reale
  browser → Cloudflare → Tunnel → kamal-proxy → FastAPI `StreamingResponse`:
  TTFB, arrivo chunk, idle timeout, reconnect, **deploy mentre lo stream è
  aperto**. I named Cloudflare Tunnel supportano SSE (i Quick Tunnel no).
- **Realtà da accettare:** lo stream chat è one-shot (un turno agente), niente
  resume / `Last-Event-ID`. Deploy a metà turno → turno perso. `drain_timeout`
  di `kamal-proxy` generoso (30–60s, i turni corti finiscono); il **FE deve
  rilevare il drop e mostrare "riconnetto / ripeti"**. C'è già lavoro in volo:
  `backend/llm_streaming.py`, `frontend/src/features/chat/lib/streamSanitizer.ts`.
- **File:** `e2e/` (Playwright), eventuale `frontend/src/features/chat/*`
  (reconnect UI).
- **Accettazione:** turno che completa attraverso lo stack; deploy durante lo
  stream → il FE recupera con un retry visibile, niente stato corrotto.
- **Note:** _(vuoto)_

### Track A — fuori scope (per ora)
2° Neo4j always-on · "2× cloudflared per HA" · replica Postgres · Kubernetes ·
managed DB (Fla/Render/Railway — sbatte contro data stack su 127.0.0.1).

---

## Track B — Tenant boundary end-to-end

Obiettivo: passare da `default_consultant_id` hardcoded + tenant fidato-da-header
a: utente autenticato → membership → organizzazione autorizzata → contesto
consultant, propagato **anche nei job asincroni**.

**Stima realistica: 1–2 settimane.** Il JWT verify è la parte facile; il grosso
è disfare `default_consultant_id` / `mem0_user_id` in tutto il request path +
worker + i **tre** datastore (canonical Postgres, workspace Postgres, Mem0
pgvector). Mem0 è il più sensibile: il recall entra nel prompt LLM.

### B1 — Progetto Supabase + JWT verifier + prod-guard  ⬜
- **Supabase:** progetto in **regione EU** (Frankfurt — non si sposta dopo).
  Signing algorithm = **ES256** (attivare/ruotare esplicitamente le asymmetric
  signing keys; il JWKS pubblico serve solo con chiavi asimmetriche). Sign-up
  pubblici **OFF**. Access token TTL = **30 min**.
- **Backend:** middleware FastAPI che verifica il bearer:
  - firma via JWKS `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json`
  - **alg allowlist = esattamente `["ES256"]`** (rifiuta `none`, HS*)
  - `iss == https://<ref>.supabase.co/auth/v1`, `aud == "authenticated"`,
    `role == "authenticated"`, `is_anonymous == false`
  - `exp` / `iat` / `nbf` con leeway 30–60s
  - `sub` UUID valido → è `auth_subject`
  - cattura `session_id` per log/audit
  - **cache JWKS in-memory**, TTL ~10 min, refresh kid-aware, refresh su kid
    sconosciuto, stale-on-error limitato a ~1h poi fail-closed. **NON** cache su
    disco a lunga scadenza (peggiora la revoca).
  - lib: `pyjwt[crypto]` + `PyJWKClient`.
- **Prod-guard:** all'avvio, se `ENVIRONMENT in {production, staging}` e
  `delir_auth_enabled == false` → **errore fatale di startup**. Aggiungere
  anche: DSN non-locali in prod, `iss`/JWKS Supabase configurati.
- **Degradazione outage Supabase:** token già emessi verificabili offline fino a
  `exp` (≤30 min) → richieste normali continuano; login nuovi + refresh
  falliscono. Accettato per il pilot.
- **File:** `backend/settings.py` (`environment`, `supabase_project_ref`,
  `supabase_jwks_url`, `run_migrations_on_startup`), `backend/security.py`
  (verifier), nuovo `backend/auth/supabase_jwt.py`, `pyproject.toml` (`pyjwt[crypto]`).
- **Accettazione:** JWT Supabase valido → `AuthPrincipal` popolato; JWT scaduto/
  alg errato/iss errato → 401; `ENVIRONMENT=production` + auth off → l'app non
  parte. CI resta col path `delir_auth_enabled=false` (fixture fake-JWT per i
  test del path auth, **CI non tocca Supabase**).
- **Note:** _(vuoto)_

### B2 — Modello tenant su Postgres Oracle  ⬜
- **Cosa:** tabelle (workspace DB o nuovo schema `identity`):
  ```
  users          (id, auth_subject UUID unique, email, status[pending|active], created_at)
  organizations  (id, name, created_at)
  memberships    (user_id, organization_id, role[owner|admin|consultant|viewer], status, created_at)
  invites        (id, email_normalized, organization_id, role, invited_by,
                  auth_subject NULL, expires_at, accepted_at)
  audit_log      (id, actor_user_id, organization_id, action, target, payload, created_at)
  ```
- **Mappatura al canonical:** oggi `organizations` DeliR ≈ il "consultant" del
  canonical (`kg_entity` scope, migration 0007 semina UN consultant
  `3fcba7a0-...`). Decidere: `organization_id` DeliR → `consultant_id` canonical
  1:1, oppure un livello in più. Documentare la scelta qui.
- **File:** `backend/database.py` o nuovo `backend/auth/models.py`,
  migration `migrations_workspace/`.
- **Accettazione:** schema migra pulito; seed di un'org + membership per lo
  sviluppo.
- **Note:** _(vuoto)_

### B3 — Risoluzione tenant nel request path  ⬜
- **Cosa:** `require_principal` (in `backend/security.py`) diventa:
  1. verifica JWT (B1) → `sub`
  2. `users` per `auth_subject = sub` (se `status=pending` e primo login →
     transizione a `active`, vedi B6)
  3. `memberships` dell'utente
  4. `X-DeliR-Tenant-ID` = **hint di selezione**: se l'utente ha 1 org →
     ignorato; se multi-org → seleziona, `403` se non membro
  5. `AuthPrincipal` con `user_id`, `organization_id`, `consultant_id` risolto,
     `role`
  6. contesto tenant impostato **dalla membership risolta**
- **`X-DeliR-Admin-Token` globale** ([security.py:116](../backend/security.py#L116)) →
  diventa "staff piattaforma DeliR", concetto separato dall'admin *per-org* (che
  è un `role` nella membership). Fuori dal browser.
- **File:** `backend/security.py`, `backend/app.py` (middleware tenant).
- **Accettazione:** utente di org A che chiede `X-DeliR-Tenant-ID: B` → 403;
  utente mono-org → funziona senza header.
- **Note:** _(vuoto)_

### B4 — Kill `settings.default_consultant_id` (+ `settings.mem0_user_id`) nel request path  ⬜
- **Cosa:** il `consultant_id` arriva dall'`AuthPrincipal` (B3), non da
  `settings`. Toccare i chiamanti di `canonical_session(...)` e
  `scope.resolve(...)`:
  - `backend/memory/scope.py` — `resolve()` / `resolve_client_id()` prendono
    `consultant_id` come argomento (oggi riga 81/115/135 usano
    `settings.default_consultant_id`)
  - `backend/memory/gateway.py`, `backend/memory/canonical_memory.py`,
    `backend/toolsets/memory.py`, `backend/memory/procedural/playbook_context.py`,
    `backend/memory/semantic/semantic_store.py`,
    `backend/memory/knowledge_graph/{canonical,entity_resolution,mirror}.py`
  - `backend/agents/scope_guard.py`
- **`settings.mem0_user_id`** (default `"local-consultant"`) è la **stessa classe
  di problema**: `backend/memory/gateway.py:409` `_mem0_user_id()` fa fallback a
  quello per il consultant di default; `backend/memory/semantic/semantic_store.py:158`
  lo usa diretto. Va derivato dal consultant/org autenticato. Dettaglio in **B8**.
- `settings.default_consultant_id` / `settings.mem0_user_id` restano **solo** come
  default per dev locale (auth off).
- **File:** i suddetti (~12 file, vedi Snapshot).
- **Accettazione:** grep `default_consultant_id|mem0_user_id` → solo `settings.py`
  + il ramo auth-off; i test canonical passano con un `consultant_id` iniettato.
- **Note:** _(vuoto)_

### B5 — Job self-describing + worker tenant-aware  ⬜
- **Cosa:** le righe di coda portano il contesto. Migration:
  `kg_ingest_queue`, `graph_outbox`, `mem0_projection_log` + colonne
  `organization_id` / `consultant_id` / `created_by_user_id`. L'enqueue
  (`backend/memory/knowledge_graph/mirror.py`, `backend/toolsets/{project,process}_memory.py`)
  scrive quel contesto dall'`AuthPrincipal`.
  I worker (`backend/workers/{ingest,graph,mem0}_worker.py`) **non** chiamano più
  `_consultant()` = `settings.default_consultant_id` (vedi `ingest_worker.py:38`):
  leggono `consultant_id` dalla riga e aprono `canonical_session(row.consultant_id, …)`.
  `_claim` resta `FOR UPDATE SKIP LOCKED` ma il set RLS per-riga.
  `mem0_worker` in più deve usare il `user_id` Mem0 derivato da quel
  `consultant_id` (non `settings.mem0_user_id`) quando fa `add/update/delete` — vedi **B8**.
- **Checkpointer LangGraph:** i `thread_id` nelle tabelle `checkpoint_*` (create
  da `PostgresSaver.setup()`, fuori Alembic) devono essere **org-scoped**
  (prefisso `org:<id>:<thread>` o composto) — un `thread_id` indovinato da
  un'altra org non deve caricare il suo stato conversazione.
- **File:** `backend/workers/*`, `backend/memory/knowledge_graph/mirror.py`,
  `backend/toolsets/*_memory.py`, migration canonical, punto di creazione
  `thread_id` (route chat / grafi).
- **Accettazione:** job accodato da org A processato con contesto A; un worker
  con due org in coda non mescola; `thread_id` di A non risolvibile da B.
- **Note:** _(vuoto)_

### B6 — Flusso invite-only  ⬜
- **Cosa:**
  1. Admin crea `invites` su Oracle (`email_normalized`, `organization_id`, `role`).
  2. Backend chiama `supabase.auth.admin.inviteUserByEmail()` (**service_role
     key, solo backend, Kamal secret**). Se l'utente Supabase esiste già
     (consulente su più org → errore *"already registered"*): `admin.listUsers()`
     per email → prendi il `sub` esistente.
  3. **Bind subito** `invites.auth_subject = <sub>` + **pre-crea**
     `users(status=pending)` + `memberships(status=pending)`.
  4. Al primo login: `JWT.sub` → `users.auth_subject` → transizione
     `pending → active` (nessuna INSERT tenant-sensitive sotto richiesta, solo
     cambio stato).
  5. **Nessun matching per email.** L'identità primaria è il `sub` UUID.
  6. Admin annulla invito non accettato → `admin.deleteUser(sub)` se quel sub è
     nato solo per quell'invito e non ha mai fatto login (cleanup orfani).
- **File:** `backend/auth/invites.py`, route admin, client Supabase Admin.
- **Accettazione:** invito → utente accetta → membership attiva; email della
  vittima registrata da un attaccante non porta a nessuna membership (bind è sul
  sub, non sull'email).
- **Note:** _(vuoto)_

### B7 — RLS sul workspace DB  ⬜
- **Cosa:** oggi le tabelle `workspace_*` + `chat_*` hanno già la colonna
  `tenant_id` (default `"local"`, indicizzata) e `backend/database.py` filtra
  per `get_current_tenant_id()` in ogni query — ma (a) `tenant_id` viene
  dall'header fidato, (b) il filtro è sparso a mano query per query (uno mancato
  = leak cross-tenant), (c) niente RLS.
  → Aggiungere **RLS sul database `workspace`** con GUC di sessione (stesso
  pattern del canonical, `backend/db/session.py:82`): un solo punto di
  enforcement. Il `tenant_id`/`organization_id` viene dall'`AuthPrincipal`.
  "Workspace niente RLS" era una scelta da single-tenant — multi-tenant la
  ribalta. **Fork architetturale — confermare con Sohayb prima di implementare.**
- **File:** migration `migrations_workspace/`, `backend/local_store.py` /
  nuovo `workspace_session()` che imposta il GUC, `backend/database.py` +
  `backend/workspace_storage.py` (rimuovere i filtri a mano ridondanti dopo RLS).
- **Accettazione:** una query workspace senza GUC impostato → 0 righe (non
  errore silenzioso che ritorna tutto); test cross-tenant come
  `tests/test_canonical_rls.py`.
- **Note:** _(vuoto)_

### B8 — Mem0: isolamento tenant  ⬜
- **Perché è critico:** il recall Mem0 entra nel **prompt dell'LLM**. Un leak
  cross-tenant = contesto confidenziale del cliente A che compare nella chat del
  cliente B. È il datastore più sensibile dei tre.
- **Stato attuale:** `backend/memory/gateway.py:410` dice esplicito *"Mem0 non ha
  tenant ACL"*. Isolamento = filtro `user_id` passato a `memory.search()` +
  **post-filtro `metadata.client_id` in Python** (`gateway.py:465-467`). Tutti i
  consultant condividono **una collection** pgvector (`delir_memories`, db
  `mem0`), **nessuna RLS**. `_mem0_user_id()` fa fallback a
  `settings.mem0_user_id` per il consultant di default.
- **Cosa fare:**
  1. **`user_id` Mem0 = UUID consultant/org autenticato**, mai
     `settings.mem0_user_id` (già impostato in B4). `_mem0_user_id()` diventa
     `str(consultant_id)` puro, niente ramo speciale.
  2. **Ogni lettura Mem0 passa SOLO da `gateway.memory_search` (INV-9).** Grep di
     controllo: nessun `mem0_client.get_memory().search(` fuori da `gateway.py`.
     Aggiungere un test che lo enforce.
  3. **`mem0_worker`**: `add/update/delete` col `user_id` derivato dalla riga di
     coda (B5), non globale.
  4. **Decisione da prendere con Sohayb — collection condivisa vs per-org:**
     - *(pilot)* collection unica + `user_id` namespace + post-filtro `client_id`
       + INV-9 stretto + test cross-tenant. Cheap.
     - *(serio)* `collection_name` per org (`Memory` instance per org, cache
       keyed) → separazione fisica in pgvector. Più tabelle, più RAM. Rimandabile.
  5. **Semantica vs episodica:** oggi la semantica è consultant-level, solo
     l'episodica è client-scoped (INV-13). Con org reali, ridefinire lo scope
     (consultant / org / client) — documentare qui la scelta.
  6. **Schema `mem0` self-managed** dalla lib (non Alembic): l'entrypoint
     migrations non lo tocca, Mem0 crea la sua collection al primo uso. Il
     backup (A8) fa `pg_dump` del db `mem0` comunque.
  7. **Dipendenza hard da OpenAI** (LLM extraction + embedder): OpenAI giù → Mem0
     `add`/`search` degradano. Già best-effort nel codice (`Mem0Disabled`,
     `degradation_counters`), ma va nel DR doc come dipendenza esterna.
- **File:** `backend/memory/gateway.py`, `backend/memory/mem0_client.py`,
  `backend/memory/canonical_memory.py`, `backend/memory/semantic/semantic_store.py`,
  `backend/memory/episodic/episodic_store.py`, `backend/workers/mem0_worker.py`,
  `backend/settings.py`, nuovo test `tests/test_mem0_tenant_isolation.py`.
- **Accettazione:** memoria salvata da org A **non** compare mai nel recall di
  org B (test); grep conferma che nessun path bypassa il gateway; runbook GDPR
  (B10) purga anche Mem0.
- **Note:** _(vuoto)_

### B9 — Frontend: togliere i segreti dal bundle  ⬜
- **Cosa:** `frontend/src/lib/security.ts` legge `VITE_DELIR_API_TOKEN` e
  `VITE_DELIR_ADMIN_TOKEN` → **entrambi finiscono nel bundle browser**. Vanno
  rimossi. `appendAuthQueryParams()` mette `?api_token=` in URL (SSE/WS) → in
  log, referrer, analytics: sostituire con header `Authorization` o URL firmato a
  scadenza.
  Integrare `supabase-js` sul FE: login → sessione → `Authorization: Bearer
  <access_token>`, refresh automatico gestito dalla lib.
  `VITE_API_BASE_URL`: Production → `https://api.delir.<tld>`; Preview →
  `https://api-staging.delir.<tld>` (env separati su Vercel).
- **File:** `frontend/src/lib/security.ts`, `frontend/src/lib/api.ts`,
  `frontend/src/lib/http.ts`, `frontend/src/features/chat/components/ChatComposer.tsx`
  (costruzione URL SSE), setup Vercel.
- **Accettazione:** `grep -r VITE_DELIR .*TOKEN frontend/` → nessun risultato;
  il bundle buildato non contiene token; SSE autenticata via header.
- **Note:** _(vuoto)_

### B10 — GDPR: runbook cancellazione + regione  ⬜
- **Cosa:** right-to-erasure ora tocca 3 sistemi. Runbook "delete user":
  `admin.deleteUser(sub)` su Supabase **+** purge righe Oracle (riusare
  `neo4j_store.purge_client()` / INV-10 già esistente per i dati cliente) **+**
  purge memorie Mem0 dell'org (`memory.delete_all(user_id=...)` per lo scope
  consultant/org, vedi B8). Documentare la separazione: identity (email, auth) su
  Supabase EU / business data + memoria su Oracle.
- **File:** `docs/gdpr-runbook.md`, `scripts/delete_user.py`.
- **Accettazione:** eseguito su un utente di test, non restano righe né su
  Supabase né su Oracle né su Neo4j né nella collection Mem0.
- **Note:** _(vuoto)_

### Track B — decisioni già prese
- Supabase **solo Auth**, non database applicativo. Piano Free (50k MAU); pausa
  progetto dopo 7gg inattività = **ASSUNZIONE** che i pilota generino traffico
  sufficiente; `$25/mo` Pro appena c'è un cliente pagante.
- `email_verified` **non** usato (non è un claim documentato dell'access token) —
  risolto dal bind `auth_subject` all'invito (B6).
- Deny-list revoca sessione **fuori dal P0**: si accetta revoca entro ≤30 min
  (TTL access token); session check via `GET /auth/v1/user` solo sulle op
  sensibili (`delete`, `export`, `role/membership change`, `invite`,
  `account settings`), fail-closed se Supabase è giù.
- Mem0: per il pilot **collection unica + `user_id` namespace + INV-9 stretto**,
  non collection per-org (rimandata). Isolamento application-enforced: dipende
  dal fatto che **ogni** recall passi da `gateway.memory_search` — da blindare
  con un test (B8).

---

## Alternative scartate (con motivo)

| Scartata | Perché |
|---|---|
| FE servito da FastAPI (single origin) | Sohayb vuole FE pubblico su Vercel + preview per PR. Split-origin già supportato (`API_BASE` seam). |
| PaaS (Fly/Render/Railway) | Data stack progettato per `127.0.0.1` + Oracle Free; managed Postgres/Neo4j = costo. |
| Build ARM sulla VM di PROD | Satura CPU/RAM/IO mentre gira il pilot. CI builda, VM fa pull. |
| GH runner `ubuntu-24.04-arm` come default | A pagamento su repo privata. QEMU cross-build prima, runner ARM solo se lento. |
| 2° Neo4j staging always-on | Regola "PROD regge a 2 OCPU / 12 GB". Staging Neo4j on-demand. |
| Cache JWKS su disco per sopravvivere agli outage | Peggiora la revoca. In-memory TTL ~10 min. |
| Deny-list revoca via webhook Supabase nel P0 | Nessuna garanzia documentata logout→webhook. TTL 30 min + check su op sensibili. |
| `email_verified` nel flusso invito | Non è claim documentato dell'access token. Bind `auth_subject` all'invito. |
| Kamal accessory per tutto il data stack | Data stack stabile, raramente cambia. Kamal solo app + proxy; data stack compose separato (INV-3). |
| 2× cloudflared = HA | Stesso host = stesso failure domain. 1 replica; 2 solo per upgrade senza taglio. |
| Mem0 collection per-org nel P0 | Più tabelle + una `Memory` instance per org (RAM). Pilot: collection unica + `user_id` namespace + INV-9 stretto + test cross-tenant. Per-org rimandata. |

---

## Snapshot codebase (as-of: brainstorm iniziale — aggiornare quando cambia)

> Fonte di verità sullo stato *prima* di Track A/B. Se implementi uno step,
> aggiorna la riga corrispondente.

### Runtime / build
- Backend: FastAPI, entrypoint `backend.app:app`, `uvicorn`, `uv`, Python `>=3.14`
  (`pyproject.toml`). Nome pacchetto legacy `suso-gpt`.
- Frontend: `frontend/`, Vite 8 + React 19, build → `frontend/dist`. Root
  `package.json` orchestra dev (`scripts/dev.ps1`, PowerShell).
- **Nessun `Dockerfile` per l'app.** Solo `ops/docker-compose.yml` per il data
  stack.
- CI: `.github/workflows/ci.yml` — `backend-quality` (ruff/mypy/pytest con
  Postgres+Neo4j via compose), `frontend-quality` (eslint/tsc/vitest/storybook),
  `playwright` (6 progetti), `ci-success` gate. **Nessun job di deploy.**

### Data stack (`ops/docker-compose.yml`)
- `postgres` = `pgvector/pgvector:pg16`, `127.0.0.1:5432`, volume `delir_pgdata`.
- `neo4j` = `neo4j:5-community`, `127.0.0.1:7474/7687`, volume `delir_neo4jdata`,
  heap 512M–1G + pagecache 512M.
- Ruoli Postgres (bootstrap `ops/postgres/init/*.sh`): `delir_super` (entrypoint),
  `delir_migrator` (Alembic, owner schema), `delir_app` (DML, NOBYPASSRLS),
  `delir_worker` (solo le 2 code), `delir_mem0` (db `mem0`), `delir_workspace`
  (db `workspace`).
- Migration: 2 tracce — canonical (`alembic.ini` / `migrations/`, a mano, RLS,
  0001–0013) + workspace (`alembic_workspace.ini` / `migrations_workspace/`,
  `create_all` dai modelli). Comandi:
  `uv run alembic upgrade head` + `uv run alembic -c alembic_workspace.ini upgrade head`.
- Checkpoint LangGraph (`checkpoint_*`): creati da `PostgresSaver.setup()`, **fuori
  Alembic**, nel db `workspace`.
- Mem0 = **libreria in-process** (`mem0ai` dep, non un servizio). Vector store =
  db `mem0` (pgvector, stesso cluster), ruolo `delir_mem0`, collection
  `delir_memories`. LLM + embedder = **OpenAI** (dipendenza hard). History
  in-memory (`:memory:`). Schema creato dalla lib al primo uso (non Alembic).
  Disattivato in silenzio se `MEM0_DATABASE_URL` non è configurata
  (`Mem0Disabled`). In CI Mem0 è **off** (nessun `MEM0_DATABASE_URL`).
- Prosimos = immagine Docker separata (`Dockerfile.api` in repo esterna
  `external-tools/prosimos-microservice`), `:5000`, sim sincrona dentro la HTTP
  call (timeout 900s).

### Auth (stato attuale — da sostituire in Track B)
- `backend/settings.py`: `delir_auth_enabled=False` (default), `delir_api_token`,
  `delir_admin_token`, `delir_allowed_tenant_ids`, `delir_cors_origins`,
  `default_consultant_id="3fcba7a0-4e34-59ed-9937-6879896bbdad"` (seed
  migration 0007), `workers_in_process=True`.
- `backend/security.py`: `require_principal` — auth off → `AuthPrincipal(is_admin=True)`;
  auth on → **singolo bearer token condiviso** (`compare_digest`). Tenant da
  header `X-DeliR-Tenant-ID`, verificato **solo** contro allowlist statica
  `delir_allowed_tenant_ids` (nessun controllo membership).
  `authenticate_websocket` accetta `?api_token=` query param.
- `backend/app.py:74` middleware tenant: `set_current_tenant_id` dall'header.
  `backend/app.py:54` `configured_cors_origins()`: `["*"]` se auth off, altrimenti
  lista esatta da settings.
- Frontend `frontend/src/lib/security.ts`: legge `VITE_DELIR_API_TOKEN`,
  `VITE_DELIR_ADMIN_TOKEN`, `VITE_DELIR_TENANT_ID` (+ `window.DELIR_*` runtime).
  `authHeaders()` → `X-DeliR-Tenant-ID` + `Authorization: Bearer`.
  `appendAuthQueryParams()` → `?tenant_id=` + `?api_token=` in URL.
- `/health` (`backend/app.py:117`) = `{"status":"ok"}` incondizionato.

### Contesto tenant / RLS
- **Canonical** (`backend/db/session.py`): `canonical_session(consultant_id, client_id)`
  è l'unico accesso; imposta GUC `app.current_consultant_id` /
  `app.current_client_id` via `set_config(..., true)`. Pool 5+5. RLS `ENABLE`+`FORCE`
  su tenant tables (migration 0005). `tests/test_canonical_rls.py`.
- **Workspace** (`backend/database.py`, `backend/workspace_storage.py`): **niente
  RLS**. Tabelle `workspace_*` + `chat_sessions` + `chat_messages` hanno colonna
  `tenant_id` (String, `default="local"`, indexed). `backend/database.py` filtra
  a mano per `get_current_tenant_id()` in ogni query; `chat_sessions.thread_id`
  è PK nuda (non composta col tenant).
- **Mem0** (`backend/memory/gateway.py`, `backend/memory/mem0_client.py`):
  **nessuna tenant ACL** (commento esplicito `gateway.py:410`). Isolamento =
  `filters={"user_id": _mem0_user_id(consultant_id)}` su `memory.search()` +
  post-filtro `metadata.client_id` in Python (`gateway.py:465-467`). Collection
  unica condivisa. `_mem0_user_id()` (`gateway.py:409`) → `settings.mem0_user_id`
  (default `"local-consultant"`) per il consultant di default, altrimenti l'UUID.
  `settings.mem0_user_id` usato diretto in `semantic_store.py:158`. Lettura Mem0
  centralizzata su `gateway.memory_search` (INV-9) — ma non c'è un test che lo
  enforce.
- `settings.default_consultant_id` hardcoded — usato in ~12 file:
  `backend/memory/scope.py` (righe 81, 115, 135), `backend/workers/ingest_worker.py`
  (`_consultant()`, riga 38), `backend/memory/{gateway,canonical_memory}.py`,
  `backend/memory/knowledge_graph/{canonical,entity_resolution}.py`,
  `backend/toolsets/memory.py`, `backend/memory/procedural/playbook_context.py`,
  `backend/memory/semantic/semantic_store.py`, `backend/db/__init__.py`,
  `backend/settings.py`.

### Worker
- `backend/workers/supervisor.py`: `run_queue_workers()` — 3 task di background
  nel lifespan FastAPI (`ingest` + `graph` + `mem0`), `ThreadPoolExecutor(2)`,
  no-op sotto pytest, no-op se `workers_in_process=False` o canonical non
  configurato.
- Code: `kg_ingest_queue` (drenata da `ingest_worker` come `delir_app`),
  `graph_outbox` + `mem0_projection_log` (drenate come `delir_worker`).
  `FOR UPDATE SKIP LOCKED`. Tutte assumono **un solo consultant**.
- `mem0_worker` drena `mem0_projection_log` → Mem0 OSS (`add/update/delete`) col
  `user_id` = consultant (oggi globale). `canonical_memory.py:59` scrive
  `"user_id": str(consultant_id)`.

---

## Changelog

| Data | Chi | Cosa |
|---|---|---|
| _(brainstorm iniziale)_ | Sohayb + Claude | Doc creato. Architettura target + Track A/B definite. Nessuno step tecnico iniziato: si attende risoluzione dei 3 blocker. |
| _(brainstorm, +Mem0)_ | Sohayb + Claude | Mem0 aggiunto come terzo datastore tenant-sensitive: nuovo step **B8** (isolamento tenant), `mem0_user_id` nel kill-list di B4, `mem0_worker` in B5, backup A8 esteso ai 3 db, GDPR B10 purga anche Mem0, snapshot + alternative aggiornati. |
| 2026-09-03 | Codex | Blocker 3 confermato da Sohayb: `develop` deploya staging, label `deploy-staging` su PR per on-demand, `main` + CI verde + approval deploya prod. Restano aperti i blocker VM Oracle A1 e dominio Cloudflare. |
