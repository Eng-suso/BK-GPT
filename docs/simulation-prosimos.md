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

The sync-mode changes DeliR needs (see below) are versioned as a patch:
[`ops/prosimos/`](../ops/prosimos/) — patch file, pinned upstream commit
(`81a5297a163011a8adf0b4110e0802bc6d713e51`), and build steps.

```powershell
git clone https://github.com/AutomatedProcessImprovement/prosimos-microservice.git
cd prosimos-microservice
git checkout 81a5297a163011a8adf0b4110e0802bc6d713e51
git apply --3way ..\DeliR-MVP\ops\prosimos\sync-mode.patch
docker build --progress=plain -f Dockerfile.api -t prosimos-api .
docker run --rm -p 5000:5000 prosimos-api
```

`scripts/dev.ps1` does clone + checkout + patch + build automatically (build
cache on; set `PROSIMOS_NO_CACHE=1` to force a clean rebuild, `SKIP_PROSIMOS=1`
to skip it).

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

### BPMN normalization

Prosimos 1.2.6 only simulates a narrow subset of BPMN — plain `<task>`,
`startEvent`, `endEvent`, the four gateways, `intermediateCatchEvent` (and only
with an `event_distribution` entry) — and blows up with a bare `KeyError` on the
element id for anything else. `backend/simulation/bpmn_normalizer.py`
(`normalize_bpmn_for_prosimos`) rewrites a DeliR model into that subset before it
reaches the scenario builder and the engine. Per process:

| DeliR / imported element | Handling |
| --- | --- |
| `userTask` / `serviceTask` / `manualTask` / `scriptTask` / `businessRuleTask` / `sendTask` / `receiveTask` / `callActivity` | retagged to `<task>` |
| `subProcess` / `transaction` / `adHocSubProcess` | retagged to `<task>`, inner elements discarded (black box) |
| `complexGateway` | retagged to `exclusiveGateway` |
| `boundaryEvent` | removed with its exception flow (path not simulated) |
| `intermediateCatchEvent` / `intermediateThrowEvent` | spliced out — predecessor wired straight to successor (zero-duration) |
| multiple `startEvent` | collapsed to one, inbound sources rewired |
| multiple `endEvent` | collapsed to one, inbound flows rewired |
| `laneSet` / `dataObject*` / `textAnnotation` / `association` / `group` | removed |

DI shapes/edges that no longer reference a live element are dropped. Best-effort:
a parse failure returns the original XML so Prosimos reports its own error.

Timer/message intermediate events are currently modelled as zero-duration
pass-throughs. Giving them real durations means emitting an `event_distribution`
section from the scenario builder — a later enhancement.

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
    storage.py            # run persistence (Postgres `workspace` via workspace_connection)

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

## Event-log pipeline (Phase 1 — `feat/simulation-event-log`)

The `/api/simulate` response also names a generated **simulation event log**;
DeliR now fetches it and turns it into a run summary + a compact replay artifact.

### Confirmed Prosimos contract (integration spike, prosimos 1.2.6)

`POST /api/simulate` → JSON with keys:
`ResourceUtilization`, `IndividualTaskStatistics`, `OverallScenarioStatistics`
(each a multiply-json-encoded string), plus `StatsFilename` (`stats_*.csv`) and
`LogsFilename` (`logs_*.csv`).

Files are downloaded from **`GET {PROSIMOS_BASE_URL}/api/simulationFile?fileName=…`**
(`app.py` registers `FileApiHandler` at `/simulationFile` — **not** `/api/file`).

Event log CSV header (with `is_event_added_to_log=False`, so no event rows):
```
case_id,activity,enable_time,start_time,end_time,resource
0,Ricevi richiesta,2026-01-05 09:00:00.000000+00:00,2026-01-05 09:00:00.000000+00:00,2026-01-05 09:09:04.632381+00:00,Operatore_0
```
- `activity` is the task **name**, not its id → name→element-id mapping required
  (first occurrence wins on duplicate names).
- `resource` is `<pool name>_<instance index>` (`Operatore_0`); de-suffix to get
  the pool.
- timestamps: space-separated ISO, microseconds, `+00:00`.
- `end - start` (wall) equals Prosimos `idle_processing_time`; the log has no
  calendar info, so DeliR reports **wall-clock** KPIs
  (`cycle == waiting + processing`, matching Prosimos `idle_cycle_time`).
  Prosimos' calendar-active `cycle_time`/`processing_time` are kept only as
  `summary.prosimosCrossCheck`.

Recorded fixtures: `tests/fixtures/prosimos/{sim_log_sample.csv,simulate_response.json}`.

### Processing — `backend/simulation/log_processor.py`

Full log → **`summary`** (every KPI / P50·P90·P95 / queue stat / diagnostic
bottleneck — the only metric source) **and** → **`replay`** (display only:
≤ `SIM_REPLAY_MAX_CASES` sampled case paths, `SIM_REPLAY_BUCKETS` time buckets,
sequence-flow volumes). Changing the sample size must not move a `summary` number
(regression-tested). Flow volumes are attributed to a sequence flow only when the
BPMN control-flow graph (`flow_graph.py`) has exactly one activity-free path
between the two activities; ambiguous transitions are dropped.

### Storage + API

`WorkspaceSimulationRunArtifact` (own table, PK = `run_id`,
`replay_schema_version`) holds `summary_json` + `replay_json`. Run rows stay lean.

```text
GET /v1/workspace/simulation-runs/{id}          -> run + summary  (no replay blob)
GET /v1/workspace/simulation-runs/{id}/replay   -> { run_id, schema_version, replay }
GET /v1/workspace/bpmn-models/{id}/simulation-runs -> runs + summary each
```

Log fetch / parse failure ⇒ warning, run still `completed`, no artifact
(`/replay` → 404).

## Later phases

Add a second input path for companies with event logs:

```text
CSV / XES event log
  -> SIMOD / PIX discovery
  -> Prosimos scenario
  -> Prosimos simulation
  -> DeliR comparison report
```

SIMOD is not required for the first usable Prosimos run.
