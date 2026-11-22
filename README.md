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

To start an isolated environment with one command, use:

```powershell
npm run env:dev       # DEV data stack, then the existing live-reload app
npm run env:staging   # full STAGING stack, http://127.0.0.1:18000/
npm run env:prod-sim  # same verified app/Prosimos images, separate config and data
```

In PowerShell, use `npm.cmd run ...` if the local execution policy blocks
`npm.ps1` (for example, `npm.cmd run env:staging`).

`env:dev` requires the existing ignored `ops/.env`. The other two commands
generate their own ignored environment files on first use. Run STAGING before
PROD-SIM so the latter can promote the same images without rebuilding. Use
`npm run env:staging:stop` or `npm run env:prod-sim:stop` to release RAM while
keeping data. See [ops/local-release.md](ops/local-release.md) for teardown and
runtime checks.

Open STAGING at `http://127.0.0.1:18000/` or PROD-SIM at
`http://127.0.0.1:28000/`. The sign-in form asks for the environment's
`DELIR_DEFAULT_TENANT_ID` and `DELIR_API_TOKEN` from its ignored
`ops/.env.staging` or `ops/.env.prod-sim` file. DEV uses its live-reload URL
and does not require this sign-in. Browser sessions are separate by port.
The [three-environment browser check](docs/release/milestone-01-frontend-evidence.md)
records the actual DEV, STAGING, and PROD-SIM results.

```bash
cd frontend
npm run dev
npm run build
npm run typecheck
```

Frontend architecture: [docs/frontend-stack.md](docs/frontend-stack.md) (frozen decisions) and [docs/frontend-structure.md](docs/frontend-structure.md) (`src/` layout)

Deployment & multi-tenancy (living handoff doc, always carries the next step):
[docs/deployment-and-tenancy.md](docs/deployment-and-tenancy.md)

Current source roles:

- `frontend/src`: canonical active frontend and original chat UI.

Do not duplicate the chat. The chat module remains the canonical chat experience and should be reused for Consultant, Project, and Process contexts.
