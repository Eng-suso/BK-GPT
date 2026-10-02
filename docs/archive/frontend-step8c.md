# Frontend Step 8c-1 — Chat de-glass + index.html cleanup (fatto)

Data: 2026-08-30
Branch: `frontend-enterprise-foundation`

---

## Cosa è cambiato

### `index.html` — svuotato

Rimosso l'intero blocco `<style>` (~1000 righe: box-sizing, html/body, glassmorphism chat `.viewport`/`.shell`/`.rail`/`.sidebar`/`.composer-box`/`.message`, `svg` globale, responsive). Ora `index.html` è ~20 righe: solo `<link>` token + `<div id="root">` + script.

Le variabili `--bg-viewport`/`--bg-shell`/`--primary-dark` ecc. erano usate solo dentro quel blocco → eliminate senza impatto.

### `src/styles/globals.css` (nuovo)

Le regole base che servono a tutta l'app, portate fuori dall'inline:
`* { box-sizing: border-box }`, `html, body { margin:0; height:100dvh; overflow:hidden; background: var(--color-surface-app); ... }`, `[hidden]`.

### `src/features/chat/chat.css` (nuovo)

Tutto lo stile chat portato fuori da `index.html` e **de-glassato**:
- `.viewport` gradient radiali ambient → `background: var(--color-surface-app)` piatto
- `.shell`/`.rail`/`.topbar`/`.btn-pill-light` glass (`backdrop-filter`, `rgba(255,255,255,.x)`) → superfici solide su token
- `.message.user` bolla glass con blur → `bg: var(--color-surface-muted)` + bordo, radius 14
- `.composer-box` capsula glass 24px + inset white + blur → bianco, bordo `--color-border-strong`, radius 12, ombra sottile, focus ring blu
- `.btn-send` / `.btn-new-chat` gradient near-black → `var(--blue-700)` solido + ombra premium
- `.rail-btn.active` / `.history-item.active` near-black → `var(--color-surface-selected)` + `--blue-700`
- `.model-select` pill full → radius 8
- `svg` globale → scoped a `.viewport svg, .embedded-chat-panel svg`
- `.toast` mantenuto (dark, ok)
- responsive (3 breakpoint) mantenuto, blur rimosso

**Nessuna modifica a JSX/logica della chat.** `ChatExperience` (streaming, sessioni, review BPMN, audio) invariato — solo il CSS cambia. Le classi restano identiche.

### `main.tsx`

Import order: `tokens → globals.css → theme.css → app-shell.css → features/chat/chat.css`.

## Verifica

| Check | Esito |
|---|---|
| tsc / lint / build | ✅ 0 |
| vitest | ✅ 3/3 |
| Visiva `/consultant` (Playwright + backend + chat reale con cronologia) | ✅ chat de-glassata, funzionante, coerente con lo shell premium — composer piatto, Invia blu, sessione attiva blu-wash, bolle utente piatte |
| Visiva `/projects` | ✅ invariata (globals.css copre box-sizing/html-body dopo la rimozione dell'inline) |

## Non fatto (8c-2 / 8c-3)

- **Process studio** — `ProcessWorkspace` + `ProcessBpmnCanvas` usano ancora `.process-*` / `.workspace-splitter` / `.bpmn-*` da `app-shell.css`. Funzionanti, non glass, ma legacy. Da migrare a Tailwind.
- **Purge `app-shell.css`** — grossa parte è morta (`.product-*`, `.enterprise-*`, `.workspace-*`, `.metric-*`, `.model-*`, `.donut-*`, `.roadmap-*` — zero riferimenti dopo le migrazioni). ~2500 righe eliminabili. Restano vive: `.process-*`, `.embedded-chat-*`, `.bpmn-*`, `.bpmn-review-*`, `.api-status-card`, `product-eyebrow`.
- **Preflight Tailwind ON** — dopo purge + process studio, così il reset globale non rompe il CSS legacy. Il mini-reset in `theme.css @layer base` copre l'essenziale nel frattempo.

---

## Step 8c-2 — Process studio (fatto, light pass)

`ProcessWorkspace` + `ProcessBpmnCanvas` non erano glass (usano superfici solide su token) — il problema era solo tipografia ultra-bold + toolbar datata. Pass leggero, **nessun rewrite**:

- `app-shell.css`: `font-weight: 800 → 600` (58 occorrenze), `900 → 650` globali — l'app-shell legacy ora usa pesi premium
- `.process-bpmn-toolbar-actions button` → radius 8, peso 500, ombra sottile, hover su muted
- `.process-view-switch button.is-active` → senza bordo blu, ombra sottile
- `.process-workspace h2` → 17px, tracking -0.02em
- Il pannello chat nello studio (`.embedded-chat-panel`) eredita il de-glass di 8c-1
- Il canvas bpmn-js (`.djs-*`) e gli override `.bio-properties-panel` invariati (critici)

Verificato visivamente: studio BPMN reale (pool/lane, diagramma) dentro lo shell premium, chat de-glassata, toolbar pulita. Funzionante.

`ProcessBpmnCanvas` (888 righe, lifecycle bpmn-js / history / save / import-export / node inspector) **non riscritto in Tailwind** — costo alto, rischio alto, valore marginale basso (una vista annidata). Resta su `.process-bpmn-*` da `app-shell.css`.

## Stato migrazione — funzionalmente completa

| Superficie | Stato |
|---|---|
| `/home` `/projects` `/projects/:id` `/clients` `/models` `/archive` | ✅ premium |
| `/consultant` (chat) | ✅ de-glassata |
| process studio | ✅ de-glassato + polish |
| Design system (`ui/` + `components/`) + Storybook | ✅ |
| Shell (sidebar/topbar/i18n it-en) | ✅ |

## Resta (non user-facing / opzionale)

- **8c-3** — purge `app-shell.css`: ~2500 righe morte (`.product-*`/`.enterprise-*`/`.workspace-*`/`.metric-*`/`.donut-*`/`.roadmap-*` — 0 riferimenti). Solo perf/manutenzione. Poi **preflight Tailwind ON** (il mini-reset in `theme.css` copre l'essenziale nel frattempo). Da fare come pass dedicato e attento.
- **8d** — ⌘K command palette (shadcn `command` + `dialog`), primitive rimanenti (`select`, `popover`, `form`) quando una rotta le richiede.
- Mobile: `DetailPanel` senza drawer < xl; `ProcessBpmnCanvas` non ottimizzato mobile.
- `ChatExperience` (788 righe) e `ChatComposer` (541) da scomporre — debito, non bloccante.
