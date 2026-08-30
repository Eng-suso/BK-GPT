# Frontend Stack — Decisioni congelate

Data: 2026-08-30
Contesto: migrazione `frontend/src` a UI enterprise con design system. Vedi [frontend-audit.md](frontend-audit.md).

---

## Principio guida

DeliR **non** deve diventare un fat client. Tutta la logica di dominio resta su FastAPI + LangGraph.
Il frontend è **solo** view + interazione:

| Client (React) | Server (FastAPI/LangGraph) |
|---|---|
| rendering, layout, navigazione | routing agenti, capability, prerequisiti |
| stato UI effimero (tab, pannelli, filtri) | business rules, autorizzazione, calcoli decisionali |
| validazione di superficie (zod: formato) | validazione vera, validazione BPMN, readiness |
| cache risposte server (TanStack Query) | persistenza (workspace DB, checkpoint) |
| editing canvas → manda XML al server | trasformazioni dati, aggregazioni, KPI |

Regole:
- `lib/api.ts` = unico strato che parla al backend. Componenti non fanno `fetch` diretto.
- Niente business logic nei componenti. Componente > ~200 righe o con `if` di dominio → sposta server o in hook sottile.
- Trasformazione dati pesante → nuovo endpoint, non `useMemo` gigante.
- Il FE non conosce lo schema di routing agenti. Riceve stato, mostra.

---

## Piattaforma

| Layer | Scelta | Versione target | Note |
|---|---|---|---|
| UI runtime | React | 19 (`^19.2`) | già installato |
| Language | TypeScript | `^5.9` | già |
| Bundler/dev | Vite | 8 (`^8`) | già |
| Routing | **React Router 7** | `^7` | **library mode** (`createBrowserRouter` / `<RouterProvider>`). NIENTE framework mode (plugin Vite / SSR / loader / action). I dati li possiede TanStack Query, non i loader RR. |
| Server state | **TanStack Query** | `^5` | cache, invalidazione, retry. Sostituisce `lib/workspaceEvents.ts` (bus custom) con `queryClient.invalidateQueries`. |
| Tabelle | **TanStack Table** | `^8` | headless: sort, filtro, paginazione, selezione, colonne configurabili. Render con primitive shadcn `table`. |
| Componenti | **shadcn/ui** | CLI `@latest` (target Tailwind v4 + React 19) | copy-paste in `src/ui/`. Radix sotto. Stile "new-york", modalità CSS variables. |
| Primitive a11y | Radix UI | current (fine 2024+) | pinnare esplicito per evitare warning peer-dep con React 19 |
| Styling | **Tailwind CSS v4** | `^4` | CSS-first (`@theme`, niente `tailwind.config.js`). `@theme inline` mappa i token DeliR esistenti. `corePlugins.preflight` / reset **OFF** finché la chat non è migrata (step 8c). |
| Variants | class-variance-authority + clsx + tailwind-merge | current | dipendenze shadcn. Helper `cn()` in `lib/utils.ts`. |
| Form | react-hook-form + **zod** | rhf `^7`, zod `^4` (già) | zod già usato in `contracts/`. |
| Icone | **lucide-react** | current | default shadcn. Rimpiazza tutti i glifi testo (`"H"`, `"v"`, `"x"`…). |
| Font | **Geist** | pacchetto `geist` | self-host, no Google Fonts. Rimuovere `<link>` Inter da `index.html`. `body { font-family: var(--font-family-geist) }` (token già pronto). |
| i18n | i18next + react-i18next | current | locale `it` (default) + `en`. `locales/it/*.json`, `locales/en/*.json`. `<html lang>` dinamico. Switcher nel user menu. |
| Testing | Storybook 10 · Vitest 4 · Testing Library · Playwright | già installati | story obbligatoria per ogni primitiva. Baseline visual/a11y da resettare dopo lo slice. |

**No dark mode.** `color-scheme: light` resta. Non definire override dark. (Retrofit possibile in futuro ma fuori ambito: oggi solo `:root`.)

---

## Decisioni operative

### Migrazione — rotta per rotta

- Ordine: `/projects` (slice) → `/clients` → `/models` → Home, Archive → chat → process studio.
- Rotta migrata: la nuova UI è **l'unica** per quella rotta. Il codice vecchio (componente + CSS relativo) viene **cancellato dal file** nello stesso PR.
- **Nessun feature flag.** La rotta o è vecchia o è nuova.
- Gate (step 7): la 2ª rotta deve costare meno della 1ª. Se no → i pattern non sono giusti, torna a validazione.

### Contract API

- `/projects` usa il contract **già esistente** in `frontend/src/contracts/workspace.ts` (schemi zod + `toProject`/`toProcess`/`toClient`).
- Backend `/v1/workspace/*` è reale — lo slice ci si aggancia via TanStack Query, niente mock nuovo.
- Dati che il backend non ha (KPI, roadmap, team, scadenze, owner progetto): tab relative → **EmptyState "non disponibile"**. Non reintrodurre mock derivato.
- `projectUiData.ts` → da eliminare progressivamente. Marcare `@deprecated` finché la tab che lo usa non è migrata.
- Estensioni backend (`PATCH /projects/{id}`, campi owner/due_date/kpi su `ProjectResponse`) = decisione separata, non frontend.

### CSS

- Token system (`styles/tokens/`) **non si tocca**. Si aggiunge solo un file ponte `@theme inline` per Tailwind v4.
- `app-shell.css` (4149 righe) e `<style>` inline `index.html`: smantellati per pezzi, seguendo le rotte. Ogni classe globale muore quando la rotta che la usa è migrata.
- Nuovi componenti: Tailwind v4 utilities + primitive shadcn. CSS Module solo per casi complessi (canvas BPMN).
- `!important` (23 occorrenze) e hex hardcoded → rimossi durante la migrazione, non prima.

### ⌘K command palette

- Step **8d**, non nello slice.
- Prerequisiti: router stabile, route vere, search data endpoint, primitive `command`/`dialog`, azioni definite.

### `app/` blueprint

- Non esiste (vedi audit). Si costruisce fresh.
- Aggiornare `README.md` + `docs/ui-architecture.md`: rimuovere ogni riferimento a `app/`.
- Riferimento di struttura più vicino: pattern `.enterprise-*` in `ProjectsPage`/`ProjectWorkspace` (layout: breadcrumb + page-header + tabella + drawer). Idea buona, CSS da rifare.

---

## Dipendenze da aggiungere (Foundation, step 4)

```
# runtime
react-router-dom@^7
@tanstack/react-query@^5
@tanstack/react-table@^8
react-hook-form@^7
lucide-react
geist
i18next react-i18next
class-variance-authority clsx tailwind-merge

# dev / build
tailwindcss@^4 @tailwindcss/vite   # plugin Vite v4
# shadcn init: npx shadcn@latest init  (verificare output = config v4, non tailwind.config.js)

# pinnare esplicito (peer-dep React 19)
@radix-ui/*  → versioni current
```

Config:
- `vite.config.ts` + `tsconfig.json`: alias `@/` → `src/`
- `components.json` (shadcn)
- file ponte token: `src/styles/theme.css` → `@import` token + `@theme inline { --color-background: var(--background); ... }`
- `index.html`: rimuovere `<link>` Inter, rimuovere (dopo step 8c) il `<style>` inline

---

## Non-obiettivi

- SSR / RSC / Next.js — no. App autenticata, nessun SEO, bpmn-js è client-only.
- Dark mode — no.
- Riscrivere il token system — no, è buono.
- Loader/action di React Router — no, li fa TanStack Query.
- Migrare tutto in un colpo — no, rotta per rotta.
