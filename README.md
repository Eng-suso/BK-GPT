# DeliR MVP

The active frontend entrypoint is `frontend/src`.

Run the local full app from the repository root:

```bash
npm run dev
```

This starts:

- FastAPI backend on `http://127.0.0.1:8000/`
- Vite frontend on `http://127.0.0.1:3030/`

If a port is already busy, the script uses the next available port.

```bash
cd frontend
npm run dev
npm run build
npm run typecheck
```

Architecture note: [docs/ui-architecture.md](docs/ui-architecture.md)

Deployment & multi-tenancy (living handoff doc, always carries the next step):
[docs/deployment-and-tenancy.md](docs/deployment-and-tenancy.md)

Current source roles:

- `frontend/src`: canonical active frontend and original chat UI.
- `app`: DeliR enterprise shell/workspace blueprint, not wired into the active Vite build.

Do not duplicate the chat. The chat module remains the canonical chat experience and should be reused for Consultant, Project, and Process contexts.
