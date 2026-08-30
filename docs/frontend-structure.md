# Frontend — Struttura `src/` e convenzioni

Data: 2026-08-30
Vedi [frontend-stack.md](frontend-stack.md), [frontend-audit.md](frontend-audit.md).

---

## Target `src/`

```
src/
  main.tsx                  # entry: providers + RouterProvider
  App.tsx                   # (rimane thin, o assorbito in main)

  app/
    router.tsx              # createBrowserRouter, albero rotte
    routes.ts               # costanti path ( ROUTES.projects.detail(id) )
    providers.tsx           # QueryClientProvider + I18nextProvider + ecc.
    AppShell.tsx            # shell: sidebar + topbar + <Outlet/>

  ui/                       # primitive shadcn — generate, non scritte a mano
    button.tsx  input.tsx  badge.tsx  card.tsx  table.tsx
    dropdown-menu.tsx  tabs.tsx  dialog.tsx  breadcrumb.tsx
    skeleton.tsx  sonner.tsx  ...
    index.ts                # re-export

  components/               # composti app-generici (non legati a una feature)
    layout/
      PageHeader.tsx        # breadcrumb + titolo + azioni
      PageBody.tsx
      DetailPanel.tsx       # drawer/pannello laterale
      EmptyState.tsx
    data/
      DataTable.tsx         # wrapper TanStack Table + ui/table
      DataTablePagination.tsx
      DataTableToolbar.tsx
    shell/
      GlobalSidebar.tsx
      TopBar.tsx
      UserMenu.tsx
    feedback/
      ErrorState.tsx
      LoadingState.tsx

  features/                 # una cartella per dominio di prodotto
    projects/
      routes/
        ProjectsListPage.tsx
        ProjectDetailPage.tsx
      components/            # solo roba specifica projects
        ProjectStatusBadge.tsx
        ProjectProcessList.tsx
      api.ts                # query/mutation hooks projects (useProjectsQuery...)
      types.ts              # tipi dominio FE (Project, ProjectProcess)
    clients/
    models/
    home/
    archive/
    process/                # process studio + bpmn canvas
    chat/                   # chat unica (canonica). Riusata da consultant/project/process

  lib/
    api.ts                 # API_BASE (esistente)
    http.ts                # fetch wrapper: baseURL, JSON, HttpError tipizzato
    query.ts               # QueryClient config (staleTime, retry)
    utils.ts               # cn(), formatters puri
    i18n/
      index.ts             # init i18next
    hooks/                 # hook generici (useMediaQuery, useDebounce)

  locales/
    it/  common.json  projects.json  clients.json  ...
    en/  common.json  projects.json  clients.json  ...

  contracts/                # schemi zod + mapper DTO backend<->FE (esiste già)
    workspace.ts

  styles/
    theme.css              # @import token + @theme inline (ponte Tailwind v4)
    tokens/                # primitive.css + semantic.css — NON toccare
    globals.css            # reset scoped + base minima
    app-shell.css          # LEGACY — si svuota rotta per rotta, poi si elimina

  test/
    setup.ts
  types/
    *.d.ts
```

## Regole di collocazione

| Cosa | Dove |
|---|---|
| Primitiva UI generica (Button, Dialog) | `ui/` — generata da shadcn CLI |
| Composto riusabile cross-feature (PageHeader, DataTable) | `components/` |
| Componente usato da UNA sola feature | `features/<x>/components/` |
| Pagina montata da una rotta | `features/<x>/routes/` |
| Hook query/mutation di una feature | `features/<x>/api.ts` |
| Tipo dominio FE | `features/<x>/types.ts` |
| Schema zod + mapper DTO backend | `contracts/` |
| Fetch/HTTP | solo `lib/api/` — mai `fetch` in un componente |
| Costante path | `app/routes.ts` |
| Stringhe visibili | `locales/` — mai stringa hardcoded in un `.tsx` |

Promozione: componente nato in `features/x/components/` e poi serve a `features/y` → si sposta in `components/`. Non duplicare.

## Convenzioni naming

- **File primitive `ui/`**: kebab-case (`dropdown-menu.tsx`) — così le genera shadcn, non rinominare.
- **File componenti/pagine**: PascalCase (`ProjectsListPage.tsx`, `PageHeader.tsx`).
- **File non-componente** (hook, util, api, config): camelCase (`queryClient.ts`, `useDebounce.ts`).
- **Pagina di rotta**: suffisso `Page` (`ProjectsListPage`). Lista vs dettaglio espliciti (`...ListPage` / `...DetailPage`).
- **Hook query**: `use<Entità>Query` / `use<Entità>Mutation` (`useProjectsQuery`, `useCreateProjectMutation`).
- **Query key**: array namespaced — `["projects"]`, `["projects", id]`, `["projects", id, "sources"]`. Definite in `features/<x>/api.ts`, non sparse.
- **Componente feature-specifico**: prefisso dominio se ambiguo (`ProjectStatusBadge`, non `StatusBadge`).
- **Namespace i18n**: un file per feature (`projects.json`) + `common.json`. Chiave = `feature.area.label` (`projects.list.newButton`).
- **CSS Module** (solo dove serve): `Component.module.css` accanto al componente.
- **Test**: `Component.test.tsx` accanto. Storybook: `Component.stories.tsx` accanto.
- **Barrel `index.ts`**: solo in `ui/` e `components/*/`. Non in `features/` (import espliciti, meglio per tree-shaking e per capire le dipendenze).

## Import alias

`@/` → `src/`. Da configurare in step 4:

`tsconfig.json`:
```json
"compilerOptions": {
  "baseUrl": ".",
  "paths": { "@/*": ["src/*"] }
}
```

`vite.config.ts` + `vitest.config.ts`:
```ts
resolve: { alias: { "@": path.resolve(__dirname, "src") } }
```

Regole import:
- Cross-feature / da `lib` / `ui` / `components` → `@/...` assoluto.
- Dentro la stessa feature → relativo (`./components/X`).
- **Vietato** import tra feature diverse (`features/projects` non importa da `features/clients`). Se serve condividere → sale in `components/` o `lib/`.
- `ui/` non importa da `components/` né `features/`. `components/` non importa da `features/`. Dipendenze solo verso il basso: `features → components → ui → lib/utils`.

## Providers (`app/providers.tsx`)

Ordine di wrapping (esterno → interno):
```
<QueryClientProvider>
  <I18nextProvider>
    <RouterProvider router={router} />
  </I18nextProvider>
</QueryClientProvider>
```
`RouterProvider` monta `AppShell` come layout root, le pagine feature vanno in `<Outlet/>`.

## Rotte (`app/routes.ts`)

```
/                                   → redirect /projects
/projects                           → ProjectsListPage
/projects/:projectId                → ProjectDetailPage
/projects/:projectId/processes/:processId → ProcessStudioPage
/clients            /clients/:clientId
/models
/home
/archive
/consultant                         → chat (scope consultant)
```
Helper tipizzati: `ROUTES.projects.detail(id)` → `/projects/${id}`.
Migrazione: una rotta alla volta punta al componente nuovo; le altre restano sui componenti vecchi finché non migrate.

## Legacy — piano di svuotamento

- `src/components/{chat,layout,navigation,shell,workspace}` attuali: cartelle miste. Non rinominare in blocco. Ogni componente si sposta nella nuova posizione **quando la sua rotta viene migrata**, e il vecchio file si cancella.
- `app-shell.css`: resta finché esiste anche solo una rotta non migrata. Ultima rotta migrata → il file si elimina.
- `<style>` inline `index.html`: eliminato con la migrazione chat (step 8c).
- `features/*/projectUiData.ts` e simili mock: `@deprecated`, eliminati con la tab che li usa.
