# Frontend Step 8c-3 — app-shell.css purge + preflight ON (fatto)

Data: 2026-08-30
Branch: `frontend-enterprise-foundation`

---

## `app-shell.css` eliminato (−4148 righe)

Filtrato con uno script postcss: dei 535 blocchi di regole, **210 vivi** (referenziati da `className` in `src/**`) → estratti in `src/features/process/process.css`; **325 morti** (`.product-*`, `.enterprise-*`, `.workspace-*`, `.metric-*`, `.model-card`, `.projects-page`, `.project-list/row`, `.donut-*`, `.roadmap-*`, `.managerial-*`, `.gantt-*`, `.milestone-timeline`, `.comment-box`, `.status-pill-ui`, `.project-context-*`, `.process-preview-*`, `.mini-process-diagram`, ...) → scartati.

`src/features/process/process.css` (~36 KB): process studio + BPMN canvas + embedded chat panel + BPMN review card + api-status card + `product-eyebrow`. Include gli override `.djs-*` (bpmn-js) e `.bio-properties-panel*` (bpmn-io) — load-bearing, invariati.

`main.tsx` import: `globals.css → theme.css → features/process/process.css → features/chat/chat.css`.

## Preflight Tailwind ON

`theme.css`: `@import "tailwindcss/preflight.css" layer(base)`. Rimosso il mini-reset a mano (button/input/heading/list/a) — preflight lo fa in modo completo. Tenuto solo `body { font-family; letter-spacing }` + `input:focus { outline:none }` + `.process-bpmn-canvas svg { display: inline }` (preflight forza `svg { display:block }`, romperebbe bpmn-js).

Sicuro perché: `process.css` e `chat.css` sono **unlayered** → vincono su `@layer base` (preflight). Le loro regole esplicite sopravvivono al reset.

## Regressione trovata + fix

`/consultant` (chat `chrome="full"` embedded) era rotta: sidebar conversazioni schiacciata a ~40px. Causa: le regole `.viewport-embedded` / `.chat-shell-embedded` (grid 2 colonne, no nav rail) vivevano in `app-shell.css` e non erano nel whitelist. Fix in `chat.css`:
- `.viewport-embedded { width/height: 100% }`
- `.viewport-embedded .chat-shell-embedded { grid-template-columns: 260px minmax(0,1fr) }` (specificità (0,2,0) per battere `.shell` dentro le media query)
- media query `.shell {` → `.shell:not(.chat-shell-embedded) {`

## Verifica visiva (Playwright + backend reale)

| Superficie | Preflight ON |
|---|---|
| `/home` `/projects` `/clients` `/models` `/archive` | ✅ identiche, nessuna regressione |
| `/consultant` chat | ✅ (dopo fix embedded grid) — sidebar 260px, composer, cronologia |
| process studio (bpmn-js canvas + chat panel + toolbar) | ✅ diagramma renderizza, tutto funziona |

## Bundle

CSS: 217 KB (era 254 con app-shell.css). tsc/lint/build/vitest 3/3 verdi.

## Migrazione — completa

Restano solo debiti opzionali:
- **8d** — ⌘K command palette + primitive `select`/`popover`/`form` on-demand
- Mobile — `DetailPanel` senza drawer < xl; process studio non ottimizzato mobile
- `ChatExperience` (788 righe) / `ChatComposer` (541) — da scomporre
- `process.css` (~36 KB legacy) — un giorno riscrivibile in Tailwind, non urgente
