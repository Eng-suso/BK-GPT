# Frontend Foundation — Step 4 (fatto)

Data: 2026-08-30
Branch: `frontend-enterprise-foundation`
Vedi [frontend-stack.md](frontend-stack.md), [frontend-structure.md](frontend-structure.md).

---

## Cosa è atterrato

### Dipendenze aggiunte (`frontend/package.json`)

Runtime: `react-router-dom@7`, `@tanstack/react-query@5`, `@tanstack/react-table@8`,
`react-hook-form@7`, `lucide-react@1`, `i18next@26` + `react-i18next@17`,
`class-variance-authority`, `clsx`, `tailwind-merge`, `radix-ui@1` (via shadcn),
`@fontsource-variable/geist` + `@fontsource-variable/geist-mono`.

Dev: `tailwindcss@4`, `@tailwindcss/vite@4`.

Rimosso: `@storybook/test@8.6.15` — era la **causa del conflitto peer** (Storybook 10 nel resto del repo, `@storybook/test` fermo a 8). Non importato da nessun file. In SB10 le utility di test stanno in `storybook/test`.

Font: rimosso il pacchetto `geist` (Next-only, usa `next/font`). Sostituito con `@fontsource-variable/geist` (family `"Geist Variable"` / `"Geist Mono Variable"`, self-host).

### Config

| File | Modifica |
|---|---|
| `vite.config.ts` | plugin `@tailwindcss/vite`, alias `@` → `src/` |
| `vitest.config.ts` | alias `@` → `src/` |
| `tsconfig.json` | `baseUrl: "."`, `paths: { "@/*": ["src/*"] }`, include `vitest.config.ts` |
| `components.json` | shadcn — style `new-york`, `rsc:false`, css `src/styles/theme.css`, alias `@/ui`, `@/lib/utils`, iconLibrary `lucide` |
| `eslint.config.js` | override `src/ui/**` → `react-refresh/only-export-components` off (file shadcn generati) |
| `index.html` | rimossi `<link>` Inter + preconnect Google Fonts; inline `<style>` `font-family` → `var(--font-family-geist)` |
| `.storybook/preview.ts` | import token + `theme.css` + font Geist |

### Nuovi file

```
src/styles/theme.css        Tailwind v4 entry. Preflight OFF (@layer theme/utilities
                            solo, niente preflight.css). @theme inline: bridge token
                            DeliR (--background, --primary, --radius, --font-*) -> utility Tailwind.
                            @layer base { body { font-family: var(--font-family-geist) } }
src/lib/utils.ts            cn()
src/lib/http.ts             http<T>() wrapper su API_BASE + class HttpError
src/lib/query.ts            queryClient (staleTime 30s, retry 1, no refetchOnWindowFocus)
src/lib/i18n/index.ts       i18next instance, it (default) + en, persistenza localStorage,
                            <html lang> dinamico
src/locales/{it,en}/common.json   nav / actions / state / language
src/app/routes.ts           ROUTES + helper tipizzati + SECTION_PATH + sectionFromPath()
src/app/router.tsx          createBrowserRouter (library mode). Layout <AppLayout> + rotte
                            che montano le pagine feature ESISTENTI (pre-migrazione)
src/app/AppLayout.tsx       shell: GlobalSidebar + TopBar + <Outlet/>, nav via useNavigate,
                            active section da useLocation
src/app/providers.tsx       QueryClientProvider > I18nextProvider > RouterProvider
src/ui/button.tsx           primo componente shadcn (verifica pipeline)
```

### File rimossi

- `src/App.tsx`, `src/app/AppRoot.tsx` — sostituiti da `providers.tsx` + `router.tsx`
- `src/components/shell/AppShell.tsx` — sostituito da `src/app/AppLayout.tsx`
- `src/components/shell/TopBar.test.tsx` — riscritto: le vecchie asserzioni erano **stale** (attendevano `<h1>` section title / eyebrow "Area lavoro" / bottone "Cerca" che il TopBar attuale non rende). Ora pinnano il comportamento reale. TopBar va comunque ricostruito allo step 8.

### `main.tsx`

Ordine import CSS: font Geist → `tokens/primitive.css` → `tokens/semantic.css` → `styles/theme.css` (bridge Tailwind) → `styles/app-shell.css` (legacy). Render `<AppProviders/>`.

---

## Verifica

| Check | Esito |
|---|---|
| `npx tsc --noEmit` | ✅ 0 errori |
| `npm run build` | ✅ (bundle JS 2.3 MB / 645 kB gzip — code-splitting è lavoro successivo) |
| `npx vitest run` | ✅ 7/7 (era 4 fail per il test TopBar stale, ora sistemato) |
| `npm run lint` | ✅ 0 warning (con override `src/ui/**`) |
| `npm run dev` + transform `main.tsx` / `theme.css` | ✅ 200, nessun errore di trasformazione |
| `npx shadcn add button` | ✅ genera `src/ui/button.tsx`, aggiunge `radix-ui` |

Non verificato ancora: `npm run storybook` build completa (dopo rimozione `@storybook/test` + edit `preview.ts`) → controllare a inizio Step 5.

---

## Note / debito

- **Preflight Tailwind OFF**: le utility funzionano, ma nessun reset globale. Riattivare in Step 8c con la de-glass della chat.
- **Doppio caricamento token**: `index.html` ha `<link href="styles/tokens/index.css">` E `main.tsx` importa primitive+semantic. Serve al FOUC dell'inline `<style>`. Si risolve con la rimozione dell'inline `<style>` (8c).
- **`lib/api/` vs `lib/http.ts`**: usato `lib/http.ts` + `lib/query.ts` piatti invece della cartella `lib/api/` (meno churn, `lib/api.ts` esistente resta). Doc struttura aggiornato.
- **Pagine feature**: ancora quelle pre-migrazione, montate dal router as-is. `AppLayout` usa le classi legacy `.product-shell` (invariate). La miglia zero è: navigazione ora per URL invece di `useState`.
- **Pre-existing uncommitted**: all'inizio sessione il repo aveva già modifiche non committate (backend/*, `ChatExperience.tsx`, `tests/*`) non legate a questo lavoro. Non incluse in questo scope.

## Prossimo — Step 5

Design system minimo (solo per lo slice `/projects`): `input badge card table tabs dropdown-menu breadcrumb skeleton dialog sonner` + composti `PageHeader / DataTable / DetailPanel / EmptyState`. Story per ognuno.
