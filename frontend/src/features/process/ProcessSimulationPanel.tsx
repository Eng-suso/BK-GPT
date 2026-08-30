import React from "react";
import { useTranslation } from "react-i18next";

import { HttpError } from "@/lib/http";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
import { EmptyState } from "@/components/feedback";
import { StatusIndicator, type StatusTone } from "@/components/status";
import { cn } from "@/lib/utils";
import type { ProjectProcess } from "../../contracts/workspace";
import {
  getProsimosSimulationRun,
  listProsimosSimulationRuns,
  runProsimosSimulation,
} from "./simulationApi";
import type { SimulationRun } from "./simulationTypes";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;

const RUN_TONE: Record<SimulationRun["status"], StatusTone> = {
  pending: "pending",
  completed: "ok",
  failed: "danger",
};

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
  const { t } = useTranslation("process");
  const fieldId = React.useId();
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
        // No simulation-runs resource yet for this model → empty, not an error.
        if (err instanceof HttpError && err.status === 404) {
          setRuns([]);
          setError(null);
          return;
        }
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

    setError(t("simulation.timeout"));
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

  const runStatusLabel = (status: SimulationRun["status"]) =>
    t(`simulation.status.${status}`, { defaultValue: status });

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 p-3 xl:grid-cols-[minmax(300px,360px)_minmax(0,1fr)]">
      <section
        aria-label={t("simulation.scenario.title")}
        className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-card shadow-sm"
      >
        <PanelHeader
          eyebrow={t("simulation.scenario.eyebrow")}
          title={t("simulation.scenario.title")}
          trailing={
            <span className="rounded-md border border-border bg-muted/60 px-2 py-1 text-xs font-medium text-muted-foreground">
              {process.stage}
            </span>
          }
        />

        <div className="grid grid-cols-1 gap-2.5 overflow-auto p-3.5 sm:grid-cols-2">
          <Field
            id={`${fieldId}-name`}
            label={t("simulation.fields.scenarioName")}
            className="sm:col-span-2"
          >
            <Input
              id={`${fieldId}-name`}
              type="text"
              value={scenarioName}
              onChange={(event) => setScenarioName(event.target.value)}
            />
          </Field>
          <Field id={`${fieldId}-cases`} label={t("simulation.fields.cases")}>
            <Input
              id={`${fieldId}-cases`}
              type="number"
              min={1}
              max={100000}
              value={totalCases}
              onChange={(event) => setTotalCases(Number(event.target.value))}
            />
          </Field>
          <Field id={`${fieldId}-arrival`} label={t("simulation.fields.arrival")}>
            <Input
              id={`${fieldId}-arrival`}
              type="number"
              min={1}
              value={arrivalIntervalMinutes}
              onChange={(event) =>
                setArrivalIntervalMinutes(Number(event.target.value))
              }
            />
          </Field>
          <Field
            id={`${fieldId}-duration`}
            label={t("simulation.fields.taskDuration")}
          >
            <Input
              id={`${fieldId}-duration`}
              type="number"
              min={1}
              value={taskDurationMinutes}
              onChange={(event) =>
                setTaskDurationMinutes(Number(event.target.value))
              }
            />
          </Field>
          <Field id={`${fieldId}-cost`} label={t("simulation.fields.costPerHour")}>
            <Input
              id={`${fieldId}-cost`}
              type="number"
              min={0}
              step={0.01}
              value={costPerHour}
              onChange={(event) => setCostPerHour(Number(event.target.value))}
            />
          </Field>
          <Field
            id={`${fieldId}-resources`}
            label={t("simulation.fields.resources")}
          >
            <Input
              id={`${fieldId}-resources`}
              type="number"
              min={1}
              max={1000}
              value={resourceAmount}
              onChange={(event) => setResourceAmount(Number(event.target.value))}
            />
          </Field>
          <Field
            id={`${fieldId}-pool`}
            label={t("simulation.fields.resourcePool")}
            className="sm:col-span-2"
          >
            <Input
              id={`${fieldId}-pool`}
              type="text"
              value={resourceName}
              onChange={(event) => setResourceName(event.target.value)}
            />
          </Field>
        </div>

        <div className="px-3.5 pb-3.5">
          <Button
            type="button"
            className="w-full"
            disabled={isRunning}
            onClick={() => void handleRun()}
          >
            {isRunning ? t("simulation.running") : t("simulation.run")}
          </Button>
        </div>

        {error && (
          <p
            role="alert"
            className="mx-3.5 mb-3.5 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs leading-relaxed font-medium text-destructive"
          >
            {error}
          </p>
        )}
      </section>

      <section
        aria-label={t("simulation.output.title")}
        className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-card shadow-sm"
      >
        <PanelHeader
          eyebrow={t("simulation.output.eyebrow")}
          title={t("simulation.output.title")}
          trailing={
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isLoadingRuns}
              onClick={() => {
                setIsLoadingRuns(true);
                setReloadKey((current) => current + 1);
              }}
            >
              {t("simulation.refresh")}
            </Button>
          }
        />

        {isLoadingRuns && runs.length === 0 ? (
          <div className="p-3.5">
            <EmptyState variant="inline" title={t("simulation.loading")} />
          </div>
        ) : runs.length === 0 ? (
          <div className="p-3.5">
            <EmptyState variant="inline" title={t("simulation.empty")} />
          </div>
        ) : (
          <div className="grid min-h-0 grid-cols-1 overflow-hidden lg:grid-cols-[240px_minmax(0,1fr)]">
            <ul className="grid content-start gap-2 overflow-auto border-b border-border bg-muted/30 p-2.5 lg:border-r lg:border-b-0">
              {runs.map((run) => {
                const isActive = activeRun?.id === run.id;
                return (
                  <li key={run.id}>
                    <button
                      type="button"
                      aria-pressed={isActive}
                      onClick={() => setActiveRun(run)}
                      className={cn(
                        "grid w-full gap-1 rounded-md border border-border bg-card px-2.5 py-2 text-left transition-colors hover:bg-accent/60",
                        isActive && "border-primary bg-accent",
                      )}
                    >
                      <span className="truncate text-xs font-semibold text-foreground">
                        {run.scenario_name}
                      </span>
                      <StatusIndicator
                        tone={RUN_TONE[run.status]}
                        label={runStatusLabel(run.status)}
                      />
                      <span className="text-[11px] font-medium text-muted-foreground">
                        {formatDate(run.created_at)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>

            {activeRun && (
              <SimulationRunDetail
                run={activeRun}
                statusLabel={runStatusLabel(activeRun.status)}
              />
            )}
          </div>
        )}
      </section>
    </div>
  );
};

function PanelHeader({
  eyebrow,
  title,
  trailing,
}: {
  eyebrow: string;
  title: string;
  trailing?: React.ReactNode;
}) {
  return (
    <header className="flex min-h-[58px] items-center justify-between gap-3 border-b border-border px-3.5 py-3">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          {eyebrow}
        </p>
        <h3 className="mt-0.5 text-sm font-semibold text-foreground">{title}</h3>
      </div>
      {trailing}
    </header>
  );
}

function Field({
  id,
  label,
  className,
  children,
}: {
  id: string;
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={id} className="text-[11px] font-semibold text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}

function SimulationRunDetail({
  run,
  statusLabel,
}: {
  run: SimulationRun;
  statusLabel: string;
}) {
  const { t } = useTranslation("process");
  const taskCount = Array.isArray(run.scenario.task_resource_distribution)
    ? run.scenario.task_resource_distribution.length
    : 0;
  const gatewayCount = Array.isArray(run.scenario.gateway_branching_probabilities)
    ? run.scenario.gateway_branching_probabilities.length
    : 0;

  return (
    <article className="grid content-start gap-3 overflow-auto p-3.5">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Kpi label={t("simulation.kpi.engine")} value={run.engine} />
        <Kpi label={t("simulation.kpi.status")} value={statusLabel} />
        <Kpi label={t("simulation.kpi.tasks")} value={taskCount} />
        <Kpi label={t("simulation.kpi.gateways")} value={gatewayCount} />
      </div>

      {run.error ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs leading-relaxed font-medium text-destructive"
        >
          {run.error}
        </p>
      ) : (
        <>
          {run.outputs.length > 0 && (
            <div className="rounded-md border border-border bg-muted/40 p-2.5">
              <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t("simulation.outputs")}
              </span>
              <ul className="grid list-disc gap-1 pl-4 text-xs text-foreground/80">
                {run.outputs.map((file) => (
                  <li key={file}>{file}</li>
                ))}
              </ul>
            </div>
          )}
          <details className="rounded-md border border-border bg-muted/40 p-2.5" open>
            <summary className="cursor-pointer text-xs font-semibold text-foreground">
              {t("simulation.jsonSummary")}
            </summary>
            <pre className="mt-2.5 max-h-[360px] overflow-auto rounded-md border border-border bg-card p-2.5 font-mono text-[11px] leading-relaxed text-foreground/80">
              {JSON.stringify(run.result, null, 2)}
            </pre>
          </details>
        </>
      )}
    </article>
  );
}

function Kpi({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-muted/40 p-2.5">
      <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <strong className="block truncate text-sm font-semibold text-foreground">
        {value}
      </strong>
    </div>
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
