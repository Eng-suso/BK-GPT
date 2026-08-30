# DeliR Frontend Agent Routing

Use this file as the project-level routing layer for DeliR frontend, UI, and UX work.

Load the smallest relevant skill set for the task. Do not load every skill by default.

## Skill Location

Frontend/UI/UX skills are vendored locally under:

`.claude/skills/`

These skills were copied from:

`C:\Users\sohay\.codex\skills\antigravity-awesome-skills\skills`

## Default Frontend Direction

DeliR is an enterprise AI process automation PWA. Frontend work should feel operational, dense, reliable, and professional.

Prefer:

- Clear workflow-first interfaces over landing-page composition.
- Stable layouts with predictable navigation.
- Accessible controls and keyboard-safe interactions.
- Enterprise-grade information hierarchy.
- Reusable components, tokens, and design-system consistency.
- Visual validation before declaring UI work complete.

Avoid:

- Decorative dashboards that do not improve task completion.
- Marketing-style hero sections inside the product app.
- Unscoped visual rewrites.
- One-off styling that bypasses local tokens or component patterns.
- Loading unrelated skills for simple edits.

## Core Frontend Stack

Use these when working broadly on DeliR's React frontend:

- `frontend-developer`
- `frontend-dev-guidelines`
- `react-best-practices`
- `react-patterns`
- `react-ui-patterns`
- `react-state-management`
- `zustand-store-ts`

If a referenced skill is not present in `.claude/skills`, continue with the closest installed local skill and do not invent missing skill behavior.

## UI And UX Design

Use when changing screens, layout, visual hierarchy, user flows, product ergonomics, or interaction design:

- `ui-ux-designer`
- `ui-ux-pro-max`
- `web-design-guidelines`
- `frontend-developer`
- `frontend-dev-guidelines`

Use `ui-ux-pro-max` for larger UX passes, complete page redesigns, or multi-screen product flows.

Use `ui-ux-designer` for focused interface decisions, usability improvements, and flow cleanup.

Use `web-design-guidelines` when layout, spacing, typography, responsive behavior, or visual polish is central to the task.

## React Implementation

Use when editing React components, hooks, routing, composition, rendering behavior, or frontend architecture:

- `react-best-practices`
- `react-patterns`
- `react-ui-patterns`
- `react-state-management`
- `frontend-developer`
- `frontend-dev-guidelines`

Use `react-state-management` when state ownership, shared state, async state, forms, or stores are involved.

Use `zustand-store-ts` when Zustand stores or store-like state boundaries are touched.

## BPMN Canvas And Node UI

Use when working on process canvases, node-based interfaces, graph controls, panels, edges, zoom/pan interactions, or diagram UX:

- `react-flow-node-ts`
- `react-ui-patterns`
- `ui-ux-designer`
- `ui-visual-validator`
- `web-design-guidelines`

Prefer stable dimensions for toolbars, node shells, handles, canvas controls, inspectors, and repeated diagram elements.

## Design System, Styling, And Components

Use when editing shared components, design tokens, Tailwind utilities, Radix primitives, buttons, forms, modals, menus, tabs, tables, or reusable UI foundations:

- `tailwind-design-system`
- `tailwind-patterns`
- `radix-ui-design-system`
- `react-ui-patterns`
- `frontend-dev-guidelines`

Use existing tokens and local component conventions before introducing new styles.

## Accessibility

Use when changing interactive components, navigation, forms, modals, keyboard behavior, contrast, focus states, semantic HTML, or screen-reader behavior:

- `accessibility-compliance-accessibility-audit`
- `wcag-audit-patterns`
- `screen-reader-testing`
- `ui-visual-validator`

Accessibility is required for product UI, not an optional polish pass.

## Visual QA

Use before considering substantial UI work complete:

- `ui-visual-validator`
- `web-design-guidelines`
- `accessibility-compliance-accessibility-audit`

For DeliR, visual QA should check desktop and mobile viewports, layout overlap, text clipping, scroll behavior, focus states, and whether the page still feels like an enterprise product surface.

## Recommended Routing By Task

For a new product screen:

- `ui-ux-pro-max`
- `frontend-developer`
- `react-ui-patterns`
- `tailwind-design-system`
- `accessibility-compliance-accessibility-audit`
- `ui-visual-validator`

For a focused component edit:

- `react-ui-patterns`
- `frontend-dev-guidelines`
- `tailwind-patterns`

For stateful frontend behavior:

- `react-state-management`
- `zustand-store-ts`
- `react-best-practices`

For canvas or BPMN UI:

- `react-flow-node-ts`
- `react-ui-patterns`
- `ui-ux-designer`
- `ui-visual-validator`

For a design-system cleanup:

- `tailwind-design-system`
- `radix-ui-design-system`
- `react-ui-patterns`
- `web-design-guidelines`

For accessibility remediation:

- `accessibility-compliance-accessibility-audit`
- `wcag-audit-patterns`
- `screen-reader-testing`

For final frontend verification:

- `ui-visual-validator`
- `accessibility-compliance-accessibility-audit`

## Local Skill Policy

- Keep `.claude/skills` focused on skills that materially improve DeliR frontend execution.
- Do not vendor broad catalogs into `.claude/skills`.
- Copy complete skill folders when adding a skill, including `SKILL.md`, `references/`, `scripts/`, `assets/`, and any other local files.
- Do not store secrets, credentials, tokens, private keys, customer raw data, health data, banking data, or non-anonymized PII in `.claude`.
- When a task spans backend, storage, security, or deployment, do not expand this file automatically. Add those routing sections only when Sohay explicitly asks for them.
