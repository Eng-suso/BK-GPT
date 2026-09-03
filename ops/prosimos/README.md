# Prosimos — sync-mode patch

DeliR calls [prosimos-microservice] as its simulation engine. Upstream is
**async** (`POST /api/simulate` enqueues a Celery task, needs RabbitMQ + Redis +
a worker). DeliR runs it **synchronously** so a single container answers with
the statistics directly — see [docs/simulation-prosimos.md](../../docs/simulation-prosimos.md).

That behaviour is a two-file patch. It used to live only on the maintainer's
laptop (uncommitted working-tree edits), which made a fresh host — or CI —
unable to reproduce a run. It is now versioned here.

[prosimos-microservice]: https://github.com/AutomatedProcessImprovement/prosimos-microservice

## What the patch does

| File | Change |
| --- | --- |
| `src/api/SimulationApiHandler.py` | `POST /api/simulate` runs `simulation_task.apply(...)` in-process and returns the stats. Async (`simulation_task.delay`) stays reachable with form field `async=true` or header `X-Prosimos-Async: 1`. Errors return a real message + 400/500 instead of a bare `"Something went wrong"`. |
| `Dockerfile.api` | `python:3.9-slim-buster` → `-bookworm` (buster is EOL, apt mirrors gone). Gunicorn: 6 sync workers (`GUNICORN_WORKERS`), 1800 s timeout (`GUNICORN_TIMEOUT`), request logging to stdout. One worker == one concurrent simulation. |

Pinned upstream base commit: **`81a5297a163011a8adf0b4110e0802bc6d713e51`**
("Update Prosimos to support distribution from pix-framework…").

## Build the image

```bash
# 1. Clone the pinned upstream (outside this repo)
git clone https://github.com/AutomatedProcessImprovement/prosimos-microservice.git \
  ~/external-tools/prosimos-microservice
cd ~/external-tools/prosimos-microservice
git checkout 81a5297a163011a8adf0b4110e0802bc6d713e51

# 2. Apply the DeliR patch
git apply --3way /path/to/DeliR-MVP/ops/prosimos/sync-mode.patch
#   already applied? `git apply --reverse --check …/sync-mode.patch` succeeds.

# 3. Build
docker build -f Dockerfile.api -t prosimos-api .
docker run --rm -p 5000:5000 prosimos-api
```

Swagger: <http://localhost:5000/apidocs/>. DeliR reads `PROSIMOS_BASE_URL`
(default `http://127.0.0.1:5000`).

`scripts/dev.ps1` does clone + checkout + apply + build automatically; set
`PROSIMOS_ROOT` to the clone path or `SKIP_PROSIMOS=1` to skip it.

## Refreshing the patch

If upstream is bumped or the patch is edited in the clone:

```bash
cd ~/external-tools/prosimos-microservice
git diff Dockerfile.api src/api/SimulationApiHandler.py \
  > /path/to/DeliR-MVP/ops/prosimos/sync-mode.patch
```

Then update the pinned commit above and in `docs/simulation-prosimos.md`.
