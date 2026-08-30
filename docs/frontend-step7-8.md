# Frontend Step 7 (validazione pattern) + Step 8a/8b (sezioni)

Data: 2026-08-30
Branch: `frontend-enterprise-foundation`

---

## Step 7 — pattern estratti (gate)

Dopo `/projects`, la duplicazione è stata estratta in composite riusabili:

| Nuovo | Cosa |
|---|---|
| `components/layout/WorkspaceListView` | shell schermata lista: main-col scrollabile (header + toolbar + tabella) + DetailPanel a destra (`hidden < xl`) |
| `components/data/ListToolbar` | search input + filter chips |
| `lib/hooks/usePagedList` | search debounced + paginazione client-side + `range` per la label |

`ProjectsListPage` refactorato su questi. **Gate**: `/clients` costruito subito dopo con lo stesso set → ~180 righe, zero componenti nuovi (solo query hook + column def + stringhe). Pattern validato.

## Step 8a — `/clients`

`features/clients/{api,types,columns,routes/ClientsListPage,index}` — `useClientsQuery`, `clientStatusTone`, DataTable + DetailPanel (settore, stato, referente, processi, documenti). i18n `clients.json` it/en. Eliminato `ClientsPage.tsx`.

## Step 8b — Home / Models / Archive

- **`features/home/HomePage`** — riscritto premium: PageHeader + 3 metric card (Clienti/Progetti/Processi da dati reali) + 2 liste (progetti/clienti recenti con `StatusIndicator`, link ai dettagli). Usa `useProjectsQuery` + `useClientsQuery` (eccezione documentata alla regola no-cross-feature per il dashboard di aggregazione).
- **`features/models/ModelsPage`** + **`features/archive/ArchivePage`** — erano 100% mock (array hardcoded / vuoti, nessun endpoint). Ora: PageHeader + `EmptyState` "In arrivo" onesto. ~185 righe mock eliminate ciascuno.

## Pulizia

- Eliminati: `components/workspace/` (5 componenti, non più usati), `components/shell/PlaceholderPage.{tsx,stories,test}` (dead code)
- `components/shell/types.ts` ricreato (serviva a `routes.ts`/`sections.ts`)
- `components/workspace` non più referenziato da nessuna pagina

## Bug fix

**`contracts/workspace.ts`** — `apiClientSchema.status` era `z.enum(["Attivo","Da seguire","Prospect"])`, ma il backend restituisce stringhe libere ("Cliente"). La `parse` falliva → Home e `/clients` in errore. Ora `z.string()` + `normalizeClientStatus()` con lookup + fallback "Prospect" (come già fa `toProject` per project/process status). Il backend usa status/phase/stage free-form: il FE normalizza sempre.

## `theme.css` — reset esteso

Aggiunto a `@layer base` (preflight ancora OFF): reset per `h1-6`/`p`/`ul`/`ol`/`dl` (indent UA) e `a { color/text-decoration: inherit }` (link sottolineati UA). Legacy markdown/menu CSS unlayered vince dove servono bullet/underline.

## Verifica

| Check | Esito |
|---|---|
| tsc / lint / build | ✅ 0 |
| vitest | ✅ 3/3 (era 7 — le 4 di `PlaceholderPage` rimosse col componente morto) |
| Visiva desktop 1600 (Playwright + backend reale) | ✅ `/home` `/projects` `/clients` `/models` `/archive` — dati veri, EmptyState onesti, sidebar premium, nessun sottolineato UA |

## Rotte — stato

| Rotta | Stato |
|---|---|
| `/projects`, `/projects/:id` | ✅ migrata (Step 6) |
| `/clients` | ✅ migrata |
| `/home` | ✅ migrata |
| `/models`, `/archive` | ✅ scaffold premium (no backend) |
| `/consultant` | ⚠️ `ChatExperience` legacy glass |
| process studio (dentro `/projects/:id`) | ⚠️ `ProcessWorkspace` legacy |

## Prossimo — Step 8c/8d

- **8c**: de-glass chat (`ChatExperience`, `ChatShell`), rimuovere `<style>` inline da `index.html`, `ProcessWorkspace`/`ProcessBpmnCanvas` al look nuovo, **preflight Tailwind ON**, valutare svuotamento `app-shell.css`. PR ad alto rischio, isolata.
- **8d**: ⌘K command palette + primitive rimanenti (select, popover, form, command).
