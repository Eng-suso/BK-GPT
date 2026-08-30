# Frontend Step 6 — Vertical slice `/projects` (fatto)

Data: 2026-08-30
Branch: `frontend-enterprise-foundation`

Prima rotta migrata. Target: `docs/design/` (Main + ProjectDetail).

---

## Cosa è cambiato

### Contract / types

- `Project` + `ProjectProcess` spostati da `features/projects/projectData.ts` → **`contracts/workspace.ts`** (dove già vivono `Client`, `ProjectSource`, `ProjectDecision`). Importatori aggiornati: `HomePage`, `features/process/ProcessWorkspace`.
- `apiProjectSchema` ora esportato (serviva per il dettaglio single-project).
- **Eliminati**: `projectData.ts`, `projectUiData.ts` (240 righe di mock derivato: KPI/roadmap/team/issue inventati), `ProjectsPage.tsx`, `ProjectWorkspace.tsx`.

### `features/projects/`

```
api.ts        useProjectsQuery / useProjectQuery / useProjectSourcesQuery /
              useProjectDecisionsQuery — TanStack Query su http() + zod (contracts)
              + projectKeys (query key namespacing)
types.ts      re-export Project/ProjectProcess + PROJECT_TABS + projectStatusTone()
columns.tsx   ColumnDef<Project>[] per DataTable (nome blu + sottotitolo, owner
              troncato, StatusIndicator, ProgressBar)
routes/
  ProjectsListPage.tsx    PageHeader + toolbar (search debounced + filtri) +
                          DataTable + DataTablePagination (client-side) + DetailPanel
  ProjectDetailPage.tsx   PageHeader + tab underline + Panoramica/Processi/Fonti/
                          Decisioni (dati reali) + Analisi/KPI/Team → EmptyState
                          "non disponibile" + DetailPanel. "Processi" apre
                          <ProcessWorkspace> inline (non ancora migrato)
index.ts
```

### Shell — rifatto premium (Tailwind, non più `.product-*`)

- `app/AppLayout.tsx` — grid `60px | 1fr` (`lg:212px | 1fr`), righe `60px | 1fr`, `h-dvh`
- `components/shell/GlobalSidebar.tsx` — wordmark blu, icone lucide, barra blu sull'attivo, **collassa a icone < lg** (label via `title`)
- `components/shell/TopBar.tsx` — tenant / search / date-range / bell(3) / `LanguageMenu` / user. Presentazionale (wiring dopo). Niente più prop `activeSection`.
- `components/shell/LanguageMenu.tsx` — dropdown it/en (shadcn `dropdown-menu`)
- `sections.ts` — icone lucide per sezione, `labelKey` i18n
- Test `TopBar.test.tsx` riscritto per il nuovo componente

### Router

- `/projects` → `ProjectsListPage` (nuovo)
- `/projects/:projectId` → `ProjectDetailPage` (nuovo)
- Altre rotte invariate (pagine pre-migrazione)

### i18n

- `locales/{it,en}/projects.json` (namespace `projects`)
- `common.json` + `nav.primary`, `nav.profile` accorciato ("Impostazioni" / "Settings")
- `i18n/index.ts` registra il namespace `projects`

### `theme.css` — mini-reset (preflight ancora OFF)

Aggiunto in `@layer base` il normalize per `button`/`input`/`textarea`/`select` + `h1-6`/`p`/`ul`/`ol`/`dl` — mirava ai `<button>`/`<input>`/`<ul>` nuovi che senza preflight prendevano bordo/box/indent UA. Il CSS legacy (unlayered) e le utility Tailwind (`@layer utilities`) vincono comunque.

### Hook

- `lib/hooks/useDebouncedValue.ts`
- `lib/hooks/useWorkspaceRefresh.ts` — bridge evento `workspace:refresh` → `queryClient.invalidateQueries`

---

## Verifica

| Check | Esito |
|---|---|
| `npx tsc --noEmit` | ✅ 0 |
| `npm run lint` | ✅ 0 |
| `npm run build` | ✅ |
| `npx vitest run` | ✅ 7/7 |
| **Validazione visiva** (backend reale + Playwright) | ✅ desktop 1600 — lista e dettaglio con dati veri, i18n it/en, riga selezionata, milestone da backend, tab "non disponibile" |
| Mobile 390 | ⚠️ sidebar collassa a icone; DetailPanel nascosto < xl; contenuto usabile ma non ottimizzato — pass mobile dedicato in Step 8 |

Screenshot in scratchpad: `projects-list.png`, `project-detail.png`, `projects-list-en.png`, `projects-list-mobile.png`.

## Debito noto

- `DetailPanel` nascosto < `xl` (non c'è drawer mobile) — Step 8
- Colonna `Proc.` allineamento a destra imperfetto; barra a 0% poco visibile
- `ProcessWorkspace` + `ChatExperience` ancora legacy (glass) — Step 8c
- `frontend-dev-guidelines` vuole `useSuspenseQuery` + boundary; usato `useQuery` + stati espliciti (Skeleton/Empty/Error) perché è ciò che il design specifica e non serve infra error-boundary nuova. Divergenza annotata.
- Pagine non migrate (Home/Clients/Models/Archive/Consultant) montate nel nuovo AppLayout: shell premium ok, il loro contenuto è ancora `.enterprise-*`/`.workspace-*` — Step 8a/8b.

## Prossimo — Step 7

Validazione pattern: review dei composti riusabili, reset baseline Playwright visual/a11y, gate "la prossima rotta costa meno". Poi Step 8: `/clients` → `/models` → Home/Archive → chat de-glass → ⌘K.
