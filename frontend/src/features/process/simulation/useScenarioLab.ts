import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { HttpError } from "@/lib/http";

import { useBpmnModelQuery } from "../api";
import {
  getProsimosSimulationRun,
  fetchScenarioTemplate,
  runProsimosSimulation,
} from "./simulationApi";
import type { ScenarioTemplate, SimulationRun } from "./simulationTypes";
import {
  loadScenarioDraft,
  saveScenarioDraft,
  scenarioToInput,
  seedDraftFromTemplate,
  type ScenarioDraft,
} from "./simulationScenario";
import { resolveActiveRun, useSimulationSection } from "./useSimulationSection";
import { useInputConfidence } from "./useInputConfidence";
import type { InputConfidence } from "./simulationProvenance";
import type { ScenarioProvenance } from "./simulationTypes";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;
const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export type ScenarioLab = {
  bpmnXml: string | null;
  template: ScenarioTemplate | null;
  templateLoading: boolean;
  draft: ScenarioDraft;
  updateDraft: (next: ScenarioDraft) => void;
  provenance: ScenarioProvenance | null;
  confidence: InputConfidence;
  activeRun: SimulationRun | null;
  isRunning: boolean;
  isPending: boolean;
  error: string | null;
  handleRun: () => Promise<void>;
};

/**
 * The shared scenario workbench: the persisted draft, the element template, the
 * input-confidence roll-up and the run+poll machinery. Panoramica and the
 * scenario builder both drive the same lab so a run launched from either shows
 * up everywhere without a reload.
 */
export function useScenarioLab(): ScenarioLab {
  const { t } = useTranslation("process");
  const queryClient = useQueryClient();
  const { process, runs: sectionRuns, refetchRuns } = useSimulationSection();

  const modelQuery = useBpmnModelQuery(process.bpmnModelId);
  const bpmnXml = modelQuery.data?.xml ?? null;

  const [pickedRunId, setPickedRunId] = React.useState<number | null>(null);
  const [polledRun, setPolledRun] = React.useState<SimulationRun | null>(null);
  const [isRunning, setIsRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const mountedRef = React.useRef(true);

  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const activeRun: SimulationRun | null = React.useMemo(() => {
    if (polledRun) return polledRun;
    if (pickedRunId != null) {
      return sectionRuns.find((r) => r.id === pickedRunId) ?? null;
    }
    return resolveActiveRun(sectionRuns, undefined);
  }, [polledRun, pickedRunId, sectionRuns]);

  const [storedDraft, setStoredDraft] = React.useState<ScenarioDraft>(() =>
    loadScenarioDraft(process.bpmnModelId),
  );

  const templateQuery = useQuery<ScenarioTemplate>({
    queryKey: ["workspace", "simulation-template", process.bpmnModelId],
    queryFn: () => fetchScenarioTemplate(process.bpmnModelId, null),
    enabled: bpmnXml !== null,
    staleTime: 60_000,
  });
  const template = templateQuery.data ?? null;
  const templateLoading = templateQuery.isLoading && bpmnXml !== null;

  const draft = React.useMemo(
    () => (template ? seedDraftFromTemplate(storedDraft, template) : storedDraft),
    [storedDraft, template],
  );

  const { provenance, confidence } = useInputConfidence(
    process.bpmnModelId,
    draft,
    template,
    bpmnXml !== null,
  );

  const updateDraft = React.useCallback(
    (next: ScenarioDraft) => {
      setStoredDraft(next);
      saveScenarioDraft(process.bpmnModelId, next);
    },
    [process.bpmnModelId],
  );

  const syncSection = React.useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ["workspace", "simulation-runs", process.bpmnModelId],
    });
    refetchRuns();
  }, [queryClient, process.bpmnModelId, refetchRuns]);

  const pollRun = React.useCallback(
    async (runId: number) => {
      const deadline = Date.now() + POLL_TIMEOUT_MS;
      while (Date.now() < deadline) {
        await delay(POLL_INTERVAL_MS);
        if (!mountedRef.current) return;
        let latest: SimulationRun;
        try {
          latest = await getProsimosSimulationRun(runId);
        } catch (err) {
          if (mountedRef.current) setError(readError(err));
          return;
        }
        if (!mountedRef.current) return;
        setPolledRun(latest);
        if (latest.status !== "pending") {
          syncSection();
          setPickedRunId(latest.id);
          setPolledRun(null);
          if (latest.status === "failed" && latest.error) setError(latest.error);
          return;
        }
      }
      setError(t("simulation.timeout"));
    },
    [t, syncSection],
  );

  const handleRun = React.useCallback(async () => {
    setIsRunning(true);
    setError(null);
    try {
      const run = await runProsimosSimulation(process.bpmnModelId, {
        ...scenarioToInput(draft, bpmnXml),
        idempotencyKey:
          typeof crypto !== "undefined" && "randomUUID" in crypto
            ? crypto.randomUUID()
            : `${process.bpmnModelId}-${Date.now()}`,
      });
      setPolledRun(run);
      syncSection();
      if (run.status === "pending") await pollRun(run.id);
      else setPickedRunId(run.id);
    } catch (err) {
      setError(readError(err));
    } finally {
      if (mountedRef.current) setIsRunning(false);
    }
  }, [process.bpmnModelId, draft, bpmnXml, syncSection, pollRun]);

  return {
    bpmnXml,
    template,
    templateLoading,
    draft,
    updateDraft,
    provenance,
    confidence,
    activeRun,
    isRunning,
    isPending: activeRun?.status === "pending",
    error,
    handleRun,
  };
}

function readError(error: unknown): string {
  if (error instanceof HttpError) {
    const body = error.body;
    if (body && typeof body === "object") {
      if ("detail" in body && typeof body.detail === "string") return body.detail;
      const nested = (body as { error?: { message?: unknown } }).error;
      if (nested && typeof nested.message === "string") return nested.message;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "Simulazione non riuscita.";
}
