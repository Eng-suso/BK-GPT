# Frontend Audit — Step 1

Data: 2026-08-30
Scopo: base per la migrazione UI enterprise (design system shadcn/ui, rotta per rotta).

---

## 1a. Stato frontend attuale

### Piattaforma (già moderna)

`frontend/package.json` è già alla generazione target:

| Pacchetto | Versione | Nota |
|---|---|---|
| react / react-dom | ^19.2.7 | React 19 **già installato** |
| vite | ^8.0.3 | |
| zod | ^4.4.3 | |
| typescript | ^5.9.3 | |
| storybook | ^10.5.8 | infra presente, 2 stories reali |
| vitest | ^4.1.10 | + @vitest/coverage-v8 |
| @testing-library/react | ^16.3.2 | |
| bpmn-js | ^18.21.0 | + properties-panel, token-simulation |

**Mancano** (da aggiungere in Foundation): `react-router`, `@tanstack/react-query`, `@tanstack/react-table`, `tailwindcss` v4 + postcss, `class-variance-authority` + `clsx` + `tailwind-merge`, `react-hook-form`, `lucide-react`, `geist`, `i18next` + `react-i18next`.

### Entry / routing

- `main.tsx` → `App` → `AppRoot`
- `AppRoot.tsx`: `useState<ShellSection>("projects")` + `renderSection()` switch. **Nessun router, nessun URL, nessun deep-link.**
- `src/app/routes.ts`: 127 byte, di fatto morto.
- `AppShell` = `GlobalSidebar` (`.product-*`) + `TopBar` + `<main>`.

### Tre linguaggi CSS sovrapposti in un unico file

`src/styles/app-shell.css` — **4149 righe, 752 selettori, 23 `!important`, 5 media query.**
Famiglie di classi (prefisso → n. selettori):

| Famiglia | Selettori | Dove usata |
|---|---|---|
| `process-*` | 143 | ProcessWorkspace, ProcessBpmnCanvas |
| `workspace-*` | 69 | Home, Models, Clients, Archive |
| `project-*` | 68 | (legacy, parziale) |
| `product-*` | 54 | AppShell, GlobalSidebar, TopBar |
| `bpmn-*` | 36 | canvas |
| `embedded-*` | 31 | chat embedded |
| `enterprise-*` | 27 | **ProjectsPage, ProjectWorkspace** (la più recente) |
| `drawer-*`, `topbar-*`, `metric-*`, `donut-*`, `roadmap-*`… | resto | sparse |

In più `index.html` ha **~500 righe di `<style>` inline** con un QUARTO linguaggio: glassmorphism (`.viewport`, `.shell`, `.rail`, `.sidebar`, `.composer-box`, `backdrop-filter`, gradient radiali) — usato **solo dalla chat** (`ChatShell`, `ChatExperience`).

Conclusione: 4 design language coesistono. `.enterprise-*` è il tentativo più recente ma incompleto e non tokenizzato.

### Token adoption

Token system (`styles/tokens/primitive.css` + `semantic.css`) è **solido e completo** — non si tocca. Ma i CSS non lo adottano:
- **111** dichiarazioni `font-size: <n>px` hardcoded (esistono `--font-size-100..900`)
- hex fuori token: `#fef3c7`, `#fde68a`, `#92400e` (esistono `--state-warning-*`), `#ffffff`
- rgba() sparsi in index.html invece di `--color-*` / `--shadow-*`
- **Mismatch font**: `--font-family-geist` nei token, ma `index.html` carica **Inter** da Google Fonts. Nessuno dei due applicato in modo consistente. → decisione presa: **Geist**.
- `semantic.css:571-591` ha già i **bridge token shadcn** (`--background`, `--foreground`, `--primary`, `--radius`…). Terreno già preparato per shadcn/ui.

### Data layer — parzialmente reale, molto mock derivato

`lib/api.ts` = solo calcolo `API_BASE`. Nessun client, nessun wrapper. Ogni pagina fa `fetch()` diretto + `zod.parse()`.

**Reale (backend `/v1/workspace/*`):**
- `contracts/workspace.ts` — schemi zod + mapper snake→camel già scritti per Project, ProjectProcess, Client, ProjectSource, ProjectDecision. **Il contract esiste già.**
- ProjectsPage, ProjectWorkspace, HomePage, ClientsPage, ProcessBpmnCanvas fetchano dati veri.

**Mock/inventato client-side** (`features/projects/projectUiData.ts`, 240 righe) — questo è il debito:
- `projectKpis()` → `"OTIF 88%"`, `"Order Cycle Time 6,2 gg"` hardcoded
- `projectDueDate()` → ritorna la stringa letterale `"30/09/2024"`
- `projectActivities()`, `projectIssues()`, `projectTeam()`, `projectBenefits()`, `projectRisks()`, `projectDecisionRequests()` → array hardcoded / derivati con formule finte (`Math.ceil((100 - progress) / 18)`)
- Fallback `"Marco Bianchi"` / `"Sara Bellini"` in 5 punti
- `TopBar.tsx` → `"Marco Bianchi / Admin"`, `"Gruppo DeliR"`, `"01 mag 2024 - 31 lug 2024"` tutto statico, `<div role="button">` non funzionali

`ProjectWorkspace.tsx` (1036 righe) ha **10 tab** (`overview`, `process-map`, `processes`, `delivery`, `analysis`, `issues`, `recommendations`, `documents`, `team`, `settings`) quasi tutti alimentati da `projectUiData.ts`. Solo `sources`/`decisions` sono reali.

### Componenti

- Nessuna primitiva. `components/workspace/` ha 5 componenti ad-hoc: `ProgressBar`, `StatusBadge`, `WorkspacePage`, `WorkspaceTable` (`<table>` grezza), `WorkspaceToolbar`.
- `components/shell/`: `AppShell`, `GlobalSidebar`, `TopBar`, `PlaceholderPage` (+ 2 stories, 2 test).
- Icone: **zero libreria**. Glifi testo ovunque: `"H"`, `"D"`, `"S"`, `"!"`, `"v"`, `"x"`, `"[]"`, `"*"`, `"<"`, `">"`, `"+"`, `"..."`.
- 18 file `.tsx` dipendono da classi globali `app-shell.css`. 7 `style={{…}}` inline.

### Chat

- `ChatExperience.tsx` (788 righe): gestisce sessioni, streaming NDJSON, review BPMN, trascrizione audio, toast, delete. Molta logica di parsing eventi stream inline.
- `ChatShell.tsx` (249 righe): 2 varianti — `chrome="full"` (standalone, usa `.viewport/.shell/.rail`) e `chrome="panel"` (embedded, `.embedded-chat-panel`). Rispetta la regola "chat unica".
- Dipende dal `<style>` inline di `index.html`. **Migrazione chat = alto rischio, PR isolata (step 8c).**

### A11y — problemi ricorrenti

- Label di navigazione con `aria-hidden="true"` (screen reader non le legge)
- Bottoni-icona con glifo testo, niente `aria-label` in alcuni casi
- `<div role="button" tabIndex={0}>` in TopBar senza handler tastiera
- Focus ring non consistente
- `e2e/accessibility.spec.ts` esiste — copertura da espandere

---

## 1b. `app/` blueprint — NON ESISTE

`README.md` e `docs/ui-architecture.md` citano una cartella `app` ("Next-style DeliR enterprise UI blueprint", fonte per shell/navigation/project/client/model/archive).

**Verificato: non esiste nel repo.**
- Nessuna `app/` a root né in `frontend/` (solo `frontend/src/app/` = AppRoot + routes.ts)
- Nessuna traccia in git history (`git log --all -- app` vuoto)
- `.gitignore` ha `Open-source-DeliR/` — anche quella dir non esiste localmente

→ **Decisione 4 (audit app/) è nulla: niente da analizzare.** La tabella KEEP/ADAPT/REJECT non si applica.
Se hai il blueprint da un'altra parte (altro branch, altra macchina, zip), passalo e lo audito. Altrimenti si costruisce fresh — i pattern `.enterprise-*` in `ProjectsPage`/`ProjectWorkspace` sono il riferimento di struttura più vicino (idea di layout buona: breadcrumb + page-header + tabella + drawer laterale; CSS da rifare).

Aggiornare `README.md` + `docs/ui-architecture.md` per rimuovere il riferimento fantasma.

---

## 1c. Backend workspace API — contract per `/projects`

`backend/api/routes/workspace.py`, prefix `/v1/workspace`. Storage reale: SQLAlchemy (`workspace_storage.py`), persistito in `DATA_DIR`. Non è mock.

### Endpoint esistenti

| Metodo | Path | Response |
|---|---|---|
| GET | `/v1/workspace/projects` | `ProjectResponse[]` |
| POST | `/v1/workspace/projects` | `ProjectResponse` |
| GET | `/v1/workspace/projects/{id}` | `ProjectResponse` (404 se assente) |
| GET | `/v1/workspace/projects/{id}/processes` | `ProjectProcessResponse[]` |
| POST | `/v1/workspace/projects/{id}/processes` | `ProjectProcessResponse` |
| GET | `/v1/workspace/projects/{id}/sources` | `ProjectSourceResponse[]` |
| POST | `/v1/workspace/projects/{id}/sources` | `ProjectSourceResponse` |
| GET | `/v1/workspace/projects/{id}/decisions` | `ProjectDecisionResponse[]` |
| POST | `/v1/workspace/projects/{id}/decisions` | `ProjectDecisionResponse` |
| GET | `/v1/workspace/clients` · POST | `ClientResponse[]` / `ClientResponse` |
| GET | `/v1/workspace/processes/{id}` | `ProjectProcessResponse` |
| GET/PUT | `/v1/workspace/bpmn-models/{id}` | `BpmnModelResponse` |
| GET | `/v1/workspace/bpmn-models/{id}/versions` | `BpmnVersionResponse[]` |
| POST | `/v1/workspace/bpmn-models/{id}/versions/{vid}/restore` | `RestoreBpmnVersionResponse` |
| GET | `/v1/workspace/bpmn-models/{id}/review` | `BpmnReviewResponse \| null` |
| POST | `/v1/workspace/bpmn-models/{id}/review/approve` | `ApproveBpmnReviewResponse` |
| DELETE | `/v1/workspace` | reset workspace |

### Contract `/projects` (da `schemas/workspace.py`)

```
ProjectResponse {
  id: str
  client_id: str
  client: str            # nome cliente denormalizzato
  name: str
  phase: str             # libero ("Discovery", "Design"…)
  status: str             # libero; il FE lo restringe a "In corso"|"A rischio"|"Bozza"
  progress: int          # 0-100
  processes: int         # process_count
  next_step: str
  milestones: str[]
  open_issues: str[]
  deliverables: str[]
  process_items: ProjectProcessResponse[]
}

ProjectProcessResponse {
  id: str
  project_id: str
  bpmn_model_id: str
  name: str
  stage: str            # FE restringe a "Discovery"|"AS-IS"|"TO-BE"|"Validazione"
  status: str            # FE restringe a "In corso"|"Da validare"|"Bozza"
  owner: str
  readiness: int        # 0-100
}

ProjectSourceResponse   { id, project_id, process_id: str|null, name, type, meta }
ProjectDecisionResponse { id, project_id, process_id: str|null, title, owner, status }
```

### Gap del contract vs UI enterprise

La UI vuole mostrare (oggi finti in `projectUiData.ts`): KPI, attività/roadmap con date, issue tipizzate (Problema/Rischio/Opportunità), team con ruoli, benefit economici, scadenze reali, owner del progetto.
**Nessuno esiste nel backend.** Opzioni per lo slice:
1. Slice mostra **solo** ciò che il backend dà (projects + processes + sources + decisions). Tab "analysis/team/kpi" → EmptyState "non disponibile". — **consigliato**
2. Estendere `ProjectResponse` backend (owner, due_date, kpis…) — fuori ambito frontend, decisione separata.
3. Tenere il mock derivato dietro `lib/api.ts` marcato `@deprecated`, da rimuovere. — debito.

### Note tecniche

- Snake_case backend → camelCase FE: mapper già in `contracts/workspace.ts` (`toProject`, `toProcess`, `toClient`…). Riusare.
- `status`/`stage`/`phase` sono **stringhe libere** lato backend; il FE fa allow-list con fallback. Mantenere.
- Nessun endpoint di update progetto (solo create + bpmn PUT). `PATCH /projects/{id}` non esiste → azioni "Aggiorna stato" in UI non hanno backend.
- `onWorkspaceChanged` (`lib/workspaceEvents.ts`): event bus custom per invalidare i fetch dopo azioni chat. Con TanStack Query → sostituire con `queryClient.invalidateQueries`.
- CORS backend `allow_origins=["*"]` — ok per dev.

---

## Sintesi rischi migrazione

| Rischio | Impatto | Mitigazione |
|---|---|---|
| 4 design language + CSS 4149 righe | alto | migrazione rotta per rotta, cancella vecchio a rotta migrata |
| `<style>` inline index.html ↔ chat | alto | PR isolata step 8c, preflight Tailwind OFF fino ad allora |
| `projectUiData.ts` mock pervasivo | medio | slice mostra solo dati reali, tab senza backend → EmptyState |
| Nessun router → refactor navigazione | medio | Foundation, RR7 library mode |
| Tailwind v4 reset vs CSS legacy | medio | `corePlugins.preflight: false` iniziale |
| `app/` blueprint inesistente | basso | costruire fresh, aggiornare i doc |
| Storybook/test coverage ~nulla | basso | story obbligatoria per ogni primitiva step 5 |

## Prossimo step

Step 2 — scrivere `docs/frontend-stack.md` con le decisioni congelate.
Poi Step 3 — struttura `src/`.
