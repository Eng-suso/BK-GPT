import React from "react";

import { HttpError } from "@/lib/http";
import type { ProjectProcess } from "../../contracts/workspace";
import {
  getProsimosSimulationRun,
  listProsimosSimulationRuns,
  runProsimosSimulation,
} from "./simulationApi";
import type { SimulationRun } from "./simulationTypes";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;

function delay(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

type ProcessSimulationPanelProps = {
  process: ProjectProcess;
  currentBpmnXml: string | null;
};

export const ProcessSimulationPanel: React.FC<ProcessSimulationPanelProps> = ({
  process,
  currentBpmnXml,
}) => {
  const [scenarioName, setScenarioName] = React.useState("Baseline AS-IS");
  const [totalCases, setTotalCases] = React.useState(100);
  const [arrivalIntervalMinutes, setArrivalIntervalMinutes] = React.useState(30);
  const [taskDurationMinutes, setTaskDurationMinutes] = React.useState(15);
  const [costPerHour, setCostPerHour] = React.useState(35);
  const [resourceAmount, setResourceAmount] = React.useState(1);
  const [resourceName, setResourceName] = React.useState("Operatore");
  const [runs, setRuns] = React.useState<SimulationRun[]>([]);
  const [activeRun, setActiveRun] = React.useState<SimulationRun | null>(null);
  const [isLoadingRuns, setIsLoadingRuns] = React.useState(true);
  const [isRunning, setIsRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [reloadKey, setReloadKey] = React.useState(0);
  const isMountedRef = React.useRef(true);

  React.useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  React.useEffect(() => {
    let isCancelled = false;

    void listProsimosSimulationRuns(process.bpmnModelId)
      .then((nextRuns) => {
        if (isCancelled) return;
        setRuns(nextRuns);
        setActiveRun((current) => current ?? nextRuns[0] ?? null);
        setError(null);
      })
      .catch((err: unknown) => {
        if (isCancelled) return;
        setError(readErrorMessage(err));
      })
      .finally(() => {
        if (isCancelled) return;
        setIsLoadingRuns(false);
      });

    return () => {
      isCancelled = true;
    };
  }, [process.bpmnModelId, reloadKey]);

  function upsertRun(run: SimulationRun) {
    setActiveRun((current) => (current && current.id === run.id ? run : current ?? run));
    setRuns((current) => {
      const rest = current.filter((item) => item.id !== run.id);
      return [run, ...rest].sort((a, b) => b.id - a.id);
    });
  }

  async function pollRunUntilDone(runId: number) {
    const deadline = Date.now() + POLL_TIMEOUT_MS;

    while (Date.now() < deadline) {
      await delay(POLL_INTERVAL_MS);
      if (!isMountedRef.current) return;

      let latest: SimulationRun;
      try {
        latest = await getProsimosSimulationRun(runId);
      } catch (err) {
        if (!isMountedRef.current) return;
        setError(readErrorMessage(err));
        return;
      }

      if (!isMountedRef.current) return;
      upsertRun(latest);
      setActiveRun(latest);

      if (latest.status !== "pending") {
        if (latest.status === "failed" && latest.error) setError(latest.error);
        return;
      }
    }

    setError("Timeout: la simulazione sta impiegando troppo tempo.");
  }

  async function handleRun() {
    setIsRunning(true);
    setError(null);

    try {
      const run = await runProsimosSimulation(process.bpmnModelId, {
        scenarioName,
        totalCases,
        currentBpmnXml,
        arrivalIntervalSeconds: Math.max(1, arrivalIntervalMinutes * 60),
        defaultTaskDurationSeconds: Math.max(1, taskDurationMinutes * 60),
        defaultCostPerHour: costPerHour,
        resourceAmount,
        resourceName,
        idempotencyKey:
          typeof crypto !== "undefined" && "randomUUID" in crypto
            ? crypto.randomUUID()
            : `${process.bpmnModelId}-${Date.now()}`,
      });
      setActiveRun(run);
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);

      if (run.status === "pending") {
        await pollRunUntilDone(run.id);
      }
    } catch (err) {
      setError(readErrorMessage(err));
    } finally {
      if (isMountedRef.current) setIsRunning(false);
    }
  }

  return (
    <div className="simulation-workspace">
      <section className="simulation-config" aria-label="Parametri simulazione">
        <header className="simulation-section-header">
          <div>
            <p className="product-eyebrow">Prosimos</p>
            <h3>Scenario</h3>
          </div>
          <span>{process.stage}</span>
        </header>

        <div className="simulation-form-grid">
          <label>
            <span>Nome scenario</span>
            <input
              type="text"
              value={scenarioName}
              onChange={(event) => setScenarioName(event.target.value)}
            />
          </label>
          <label>
            <span>Casi</span>
            <input
              type="number"
              min="1"
              max="100000"
              value={totalCases}
              onChange={(event) => setTotalCases(Number(event.target.value))}
            />
          </label>
          <label>
            <span>Arrivo medio, min</span>
            <input
              type="number"
              min="1"
              value={arrivalIntervalMinutes}
              onChange={(event) => setArrivalIntervalMinutes(Number(event.target.value))}
            />
          </label>
          <label>
            <span>Durata task, min</span>
            <input
              type="number"
              min="1"
              value={taskDurationMinutes}
              onChange={(event) => setTaskDurationMinutes(Number(event.target.value))}
            />
          </label>
          <label>
            <span>Costo ora</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={costPerHour}
              onChange={(event) => setCostPerHour(Number(event.target.value))}
            />
          </label>
          <label>
            <span>Risorse</span>
            <input
              type="number"
              min="1"
              max="1000"
              value={resourceAmount}
              onChange={(event) => setResourceAmount(Number(event.target.value))}
            />
          </label>
          <label className="simulation-form-wide">
            <span>Pool risorse</span>
            <input
              type="text"
              value={resourceName}
              onChange={(event) => setResourceName(event.target.value)}
            />
          </label>
        </div>

        <button
          type="button"
          className="simulation-run-button"
          disabled={isRunning}
          onClick={() => void handleRun()}
        >
          {isRunning ? "Simulazione in corso..." : "Avvia Prosimos"}
        </button>

        {error && <p className="simulation-error">{error}</p>}
      </section>

      <section className="simulation-results" aria-label="Risultati simulazione">
        <header className="simulation-section-header">
          <div>
            <p className="product-eyebrow">Output</p>
            <h3>Run Prosimos</h3>
          </div>
          <button
            type="button"
            onClick={() => {
              setIsLoadingRuns(true);
              setReloadKey((current) => current + 1);
            }}
            disabled={isLoadingRuns}
          >
            Aggiorna
          </button>
        </header>

        {isLoadingRuns && runs.length === 0 ? (
          <p className="simulation-empty">Caricamento simulazioni...</p>
        ) : runs.length === 0 ? (
          <p className="simulation-empty">Nessuna simulazione eseguita.</p>
        ) : (
          <div className="simulation-runs-layout">
            <ul className="simulation-run-list">
              {runs.map((run) => (
                <li key={run.id}>
                  <button
                    type="button"
                    className={activeRun?.id === run.id ? "is-active" : ""}
                    onClick={() => setActiveRun(run)}
                  >
                    <strong>{run.scenario_name}</strong>
                    <span>{run.status}</span>
                    <small>{formatDate(run.created_at)}</small>
                  </button>
                </li>
              ))}
            </ul>

            {activeRun && <SimulationRunDetail run={activeRun} />}
          </div>
        )}
      </section>
    </div>
  );
};

function SimulationRunDetail({ run }: { run: SimulationRun }) {
  const taskCount = Array.isArray(run.scenario.task_resource_distribution)
    ? run.scenario.task_resource_distribution.length
    : 0;
  const gatewayCount = Array.isArray(run.scenario.gateway_branching_probabilities)
    ? run.scenario.gateway_branching_probabilities.length
    : 0;

  return (
    <article className="simulation-run-detail">
      <div className="simulation-kpi-grid">
        <div>
          <span>Engine</span>
          <strong>{run.engine}</strong>
        </div>
        <div>
          <span>Status</span>
          <strong>{run.status}</strong>
        </div>
        <div>
          <span>Task</span>
          <strong>{taskCount}</strong>
        </div>
        <div>
          <span>Gateway</span>
          <strong>{gatewayCount}</strong>
        </div>
      </div>

      {run.error ? (
        <p className="simulation-error">{run.error}</p>
      ) : (
        <>
          {run.outputs.length > 0 && (
            <div className="simulation-output-files">
              <span>File generati</span>
              <ul>
                {run.outputs.map((file) => (
                  <li key={file}>{file}</li>
                ))}
              </ul>
            </div>
          )}
          <details className="simulation-json" open>
            <summary>Risposta Prosimos</summary>
            <pre>{JSON.stringify(run.result, null, 2)}</pre>
          </details>
        </>
      )}
    </article>
  );
}

function readErrorMessage(error: unknown) {
  if (error instanceof HttpError) {
    const detail = readDetail(error.body);
    return detail || error.message;
  }

  return error instanceof Error ? error.message : "Simulazione non riuscita.";
}

function readDetail(body: unknown) {
  if (
    body &&
    typeof body === "object" &&
    "detail" in body &&
    typeof body.detail === "string"
  ) {
    return body.detail;
  }

  if (
    body &&
    typeof body === "object" &&
    "error" in body &&
    body.error &&
    typeof body.error === "object" &&
    "message" in body.error &&
    typeof body.error.message === "string"
  ) {
    return body.error.message;
  }

  return null;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
