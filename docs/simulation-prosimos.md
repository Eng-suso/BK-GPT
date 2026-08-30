# DeliR Prosimos Simulation Integration

## Decision

DeliR uses Prosimos as the external business process simulation engine.
DeliR does not vendor Prosimos source code into `backend/`.

Prosimos responsibilities:

- Execute BPMN business process simulations.
- Apply resource calendars, arrival distributions, branching probabilities, task duration distributions, costs, and batch rules.
- Produce simulation statistics and generated logs.

DeliR responsibilities:

- Store and edit BPMN.
- Build a Prosimos-compatible scenario from DeliR process evidence.
- Keep observed, inferred, and manually entered assumptions separate.
- Call Prosimos through an adapter.
- Present scenario runs, KPI, bottlenecks, and AS-IS / TO-BE comparison.

## GitHub Repositories

Clone these outside the application codebase while evaluating the integration:

```powershell
mkdir C:\Users\sohay\Desktop\external-tools
cd C:\Users\sohay\Desktop\external-tools
git clone https://github.com/AutomatedProcessImprovement/prosimos-microservice.git
git clone https://github.com/AutomatedProcessImprovement/Prosimos.git
git clone https://github.com/AutomatedProcessImprovement/Simod.git
```

Use `prosimos-microservice` first. Use `Prosimos` as the schema/example reference.
Use `Simod` later for event-log based discovery.

## Local Prosimos Service

From the cloned `prosimos-microservice` repository:

```powershell
docker build --progress=plain -f Dockerfile.api -t prosimos-api .
docker run --rm -p 5000:5000 prosimos-api
```

`scripts/dev.ps1` does this automatically (build cache on; set `PROSIMOS_NO_CACHE=1`
to force a clean rebuild, `SKIP_PROSIMOS=1` to skip it).

Prosimos Swagger should be available at:

```text
http://localhost:5000/apidocs/
```

DeliR reads the base URL from:

```text
PROSIMOS_BASE_URL=http://127.0.0.1:5000
PROSIMOS_TIMEOUT_SECONDS=900
```

### Sync vs async mode

Upstream `prosimos-microservice` is async: `POST /api/simulate` enqueues a Celery
task (needs RabbitMQ + Redis + a worker) and returns `{"TaskId": ...}`; the client
polls `GET /api/task?taskId=...`.

DeliR patches `src/api/SimulationApiHandler.py` to run **synchronously by default**
(`simulation_task.apply(...)` in-process, no broker). `POST /api/simulate` then
returns the statistics directly. `Dockerfile.api` runs 6 gunicorn sync workers, so
~5 consultants can simulate concurrently. Original async behaviour is still
available with form field `async=true` or header `X-Prosimos-Async: 1` (requires
the full compose stack).

### Scenario contract notes (prosimos 1.2.6 / pix-framework)

- `norm` distributions need `[mean, std, min, max]` (4 params). min/max bound a
  rejection-sampling loop, so keep them a few std wide.
- `expon` (arrival) needs `[mean, min, max]`: `scale = mean - min`, `loc = min`.
- Statistics come back as multiply json-encoded strings; the adapter decodes
  `ResourceUtilization`, `IndividualTaskStatistics`, `OverallScenarioStatistics`.

### Idempotency

`POST /v1/workspace/bpmn-models/{id}/simulation-runs` derives a key from the
scenario inputs (or takes the client `idempotency_key`). A duplicate submit while
an identical run is still `pending` returns the existing run instead of launching
a second simulation. Once a run finishes, an identical request starts a fresh run
(Prosimos is stochastic — a re-sample is intentional).

## DeliR Folder Structure

```text
backend/
  simulation/
    models.py             # Pydantic internal/boundary models for simulation data
    scenario_builder.py   # BPMN XML -> Prosimos scenario JSON payload
    prosimos_adapter.py   # HTTP adapter to prosimos-microservice
    result_parser.py      # Extract generated file names from Prosimos response
    service.py            # Application orchestration
    storage.py            # SQLite run persistence

  api/routes/
    simulation.py         # /v1/workspace simulation endpoints

  schemas/
    simulation.py         # public API request/response contracts

frontend/src/features/process/
  ProcessSimulationPanel.tsx
  simulationApi.ts
  simulationTypes.ts
```

## Current API

```text
POST /v1/workspace/bpmn-models/{bpmn_model_id}/simulation-runs
GET  /v1/workspace/bpmn-models/{bpmn_model_id}/simulation-runs
GET  /v1/workspace/simulation-runs/{run_id}
```

The POST endpoint builds a Prosimos scenario and calls:

```text
POST {PROSIMOS_BASE_URL}/api/simulate
```

The request is multipart form data with:

- `startDate`
- `numProcesses`
- `modelFile`
- `simScenarioFile`

The DeliR endpoint returns immediately with a `pending` run and executes Prosimos
in a background task; the frontend polls `GET /v1/workspace/simulation-runs/{run_id}`.

## Next Phase

Add a second input path for companies with event logs:

```text
CSV / XES event log
  -> SIMOD / PIX discovery
  -> Prosimos scenario
  -> Prosimos simulation
  -> DeliR comparison report
```

SIMOD is not required for the first usable Prosimos run.
