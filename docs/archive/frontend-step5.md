# Frontend Step 5 — Design system minimo (fatto)

Data: 2026-08-30
Branch: `frontend-enterprise-foundation`
Target visivo: `docs/design/` (artifact) — direzione "blueprint DeliR + pass premium Trust & Authority".
Skill di progetto usate: `radix-ui-design-system`, `tailwind-design-system`, `frontend-dev-guidelines`, `ui-ux-pro-max` (palette), `CLAUDE.md` routing.

---

## Token — aggiustamenti premium (`src/styles/theme.css`)

Il token system NON è stato toccato. In `theme.css`, dopo l'import dei token, un `:root` ri-punta due semantici + il radius:

```css
--color-action-primary: var(--blue-700);   /* #1d4ed8, non blue-600 — meno "generic SaaS" */
--color-action-primary-hover: var(--blue-800);
--primary: var(--blue-700);
--radius: 0.5rem;                            /* 8px control radius */
```

Aggiunte al bridge `@theme inline`: `--color-success/warning/danger` (+ surface/border) dai token `--state-*`, per le composite status/priority.

## Primitive shadcn (`src/ui/`) — generate + tuning

`badge, breadcrumb, button, card, dialog, dropdown-menu, input, skeleton, sonner, table, tabs, tooltip` (+ `src/ui/index.ts` barrel).

Tuning:
- `button.tsx` — variant `default` con ombra premium a 3 livelli (`0 1px 2px + 0 2px 8px blu + inset highlight`); `destructive` → outline invece di riempito rosso; rimossi i `dark:` non necessari da `outline`/`ghost`.
- `sonner.tsx` — rimosso `next-themes` (DeliR è light-only), `theme="light"` fisso. Dipendenza `next-themes` disinstallata.

Dipendenze aggiunte da shadcn: `@radix-ui/*` via `radix-ui`, `sonner`.
`@tanstack/react-table` già presente (Step 4).

## Composite (`src/components/`)

| File | Cosa |
|---|---|
| `layout/PageHeader.tsx` | breadcrumb (react-router `<Link>`) + titolo + count inline + descrizione + slot azioni |
| `feedback/EmptyState.tsx` | variant `block` (card) / `inline` (pannello), icona lucide, slot azione |
| `feedback/ErrorState.tsx` | icona alert + retry (usa `Button` outline) |
| `status/StatusIndicator.tsx` | punto + label, tone `ok/pending/warning/danger/neutral` sui token domain-role. **Mai pill piena.** |
| `status/PriorityTag.tsx` | tag pieno `alta/media/bassa` — solo per valori categorici in tabella |
| `data/ProgressBar.tsx` | barra 5px + `%` tabular-nums, `role="progressbar"` |
| `data/DataTable.tsx` | generico `<T>` su TanStack Table + `ui/table`. Sort, riga selezionata (barra accento blu a sx), hover, `onRowClick`, skeleton rows, slot `emptyState`, slot `footer` |
| `data/DataTablePagination.tsx` | `‹ 1 2 3 ›` + label totale, finestra di pagine configurabile |
| `panel/DetailPanel.tsx` | compound: `DetailPanel` + `DetailPanelHeader` + `DetailPanelSection` + `DetailPanelKeyValue`. Sezioni separate da hairline, niente card annidate |

Barrel `index.ts` per ogni cartella `components/*`.

Regola dipendenze rispettata: `components/ → ui/ → lib/`. Nessun import verso `features/`.

## Storybook

Story per: `Button`, `Status` (StatusIndicator + PriorityTag), `PageHeader` (List + Detail), `Feedback` (Empty/EmptyInline/Error), `DetailPanel`, `DataTable` (Default/Loading/Empty).
`.storybook/preview.ts` già importa token + `theme.css` + Geist (Step 4).

## Verifica

| Check | Esito |
|---|---|
| `npx tsc --noEmit` | ✅ 0 |
| `npm run lint` | ✅ 0 (inline-disable `react-hooks/incompatible-library` su `useReactTable` — TanStack Table non è React-Compiler-memoizzabile by design) |
| `npm run build` | ✅ (CSS 234 kB / 38 kB gz) |
| `npx vitest run` | ✅ 7/7 |
| `npm run storybook:build` | ✅ |

Non fatto: validazione visiva in browser (`ui-visual-validator`). Rimandata allo Step 6, quando le composite sono montate nella rotta `/projects` reale — screenshot desktop+mobile.

## Note / debito

- `src/ui/*` co-esportano `*Variants` helper (CVA) → override eslint `src/ui/**` già in place (Step 4).
- Molti valori arbitrari Tailwind (`h-[62px]`, `text-[12.5px]`, `bg-[var(--...)]`) — deliberato: il design ha misure fuori dalla scala 4/8 e attinge ai token DeliR (`--slate-200`, `--color-surface-selected`, `--amber-700`). Da consolidare in utility custom se ricorrono.
- `frontend-dev-guidelines` spinge Suspense-first + `useSuspenseQuery`: le composite sono presentazionali (nessun fetch), il pattern si applica allo Step 6. `DataTable` ha già `isLoading` + slot skeleton/empty pronti a fare da fallback Suspense.

## Prossimo — Step 6

Vertical slice `/projects`: montare `PageHeader` + `DataTable` + `DetailPanel` sulla rotta reale, `features/projects/api.ts` (hook TanStack Query su `contracts/workspace.ts` esistente), refresh `AppLayout`/`GlobalSidebar`/`TopBar` al look premium, i18n stringhe. Poi validazione visiva.
