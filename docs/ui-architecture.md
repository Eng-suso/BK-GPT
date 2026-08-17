# DeliR UI Architecture

## Decision 1: canonical frontend entrypoint

The canonical DeliR frontend is `frontend/src`.

Use these commands from `frontend/`:

```bash
cd frontend
npm run dev
npm run build
npm run typecheck
```

The frontend Vite config points at `frontend/index.html`, which mounts `frontend/src/main.tsx`.
The frontend TypeScript config includes only `frontend/src`.

## Source roles

`frontend/src` is the active product frontend. New UI architecture work starts here.

`frontend/src/features/chat` contains the original chat UI and is the canonical chat source. The chat should be reused for Consultant, Project, and Process contexts instead of being rewritten.

`app` is a Next-style DeliR enterprise UI blueprint. It is a source for shell, navigation, project, client, model, archive, and process workspace structure. It is not currently wired into the active Vite build.

## Integration rule

DeliR provides the product shell and workspaces.
The chat module provides the single canonical chat experience.
BPMN canvas provides the process modeling workspace.

Do not create separate chat implementations for Consultant Chat, Project Chat, and Process Chat. Use the canonical chat component with a scope adapter:

```ts
type ChatScope =
  | { type: "consultant" }
  | { type: "project"; projectId: string }
  | { type: "process"; projectId: string; processId: string };
```

## Migration order

1. Keep `frontend/src` as the active app.
2. Extract the original chat into a reusable `features/chat` module.
3. Build the DeliR shell around that chat.
4. Port DeliR pages from the `app` blueprint as UI-only mock pages.
5. Continue refining the BPMN canvas inside `frontend/src/features/process`.
6. Connect real backend scopes only after the UI architecture is approved.
