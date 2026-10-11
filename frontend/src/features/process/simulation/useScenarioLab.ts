import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { HttpError } from "@/lib/http";

import { useBpmnModelQuery } from "../api";
import {
  getProsimosSimulationRun,
  fetchScenarioTemplate,
  fetchSimulationClaims,
  runProsimosSimulation,
} from "./simulationApi";
import type { ScenarioTemplate, SimulationClaims, SimulationRun } from "./simulationTypes";
import {
  loadScenarioDraft,
  parseScenarioDraft,
  saveScenarioDraft,
  scenarioParameterIssues,
  scenarioToInput,
  scenarioResourceIssues,
  seedDraftFromTemplate,
  type ScenarioDraft,
} from "./simulationScenario";
import { diffScenario } from "./scenarioPatch";
import {
  createWorkspaceScenario,
  deleteWorkspaceScenario,
  fetchScenarioWorkspace,
  putScenarioBaseline,
  scenarioDisplayName,
  scenarioRef,
  updateWorkspaceScenario,
  WORKSPACE_SEED_MAX,
  workspaceScenarios,
  type ScenarioWorkspace,
  type WorkspaceScenario,
} from "./scenarioWorkspace";
import { resolveActiveRun, useSimulationSection } from "./useSimulationSection";
import { useInputConfidence } from "./useInputConfidence";
import type { InputConfidence } from "./simulationProvenance";
import type { ScenarioProvenance } from "./simulationTypes";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;
/** Una modifica nel pannello si salva sul workspace dopo questa pausa. */
const SAVE_DELAY_MS = 600;
const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Un AS-IS creato dalla bozza locale una volta sola, anche con piu' pannelli aperti. */
const bootstrapping = new Set<string>();

export type ScenarioLab = {
  bpmnXml: string | null;
  template: ScenarioTemplate | null;
  templateLoading: boolean;
  /** SIM-07: le affermazioni dei file proposte come fonte; null finche' non arrivano. */
  claims: SimulationClaims | null;
  draft: ScenarioDraft;
  updateDraft: (next: ScenarioDraft) => void;
  provenance: ScenarioProvenance | null;
  confidence: InputConfidence;
  activeRun: SimulationRun | null;
  isRunning: boolean;
  isPending: boolean;
  error: string | null;
  handleRun: () => Promise<void>;
  /** SIM-14: il workspace AS-IS | A | B | C e lo scenario che il pannello modifica. */
  workspace: ScenarioWorkspace | null;
  workspaceError: string | null;
  selectedScenario: WorkspaceScenario | null;
  selectScenario: (id: number | null) => void;
  /** L'AS-IS con i default del template: il riferimento delle modifiche di ogni scenario. */
  baselineDraft: ScenarioDraft | null;
  isSaving: boolean;
  createScenario: (name: string, from?: WorkspaceScenario) => Promise<WorkspaceScenario | null>;
  deleteScenario: (scenario: WorkspaceScenario) => Promise<boolean>;
  /** Toglie una modifica dallo scenario: per quel punto torna come l'AS-IS. */
  revertChange: (scenario: WorkspaceScenario, index: number) => Promise<void>;
  newSeed: () => Promise<void>;
  /** Avvia uno scenario del workspace, con il seed comune. */
  runScenario: (scenario: WorkspaceScenario) => Promise<boolean>;
  /** Il motivo per cui uno scenario non puo' partire, o null. */
  scenarioBlocker: (scenario: WorkspaceScenario) => string | null;
};

/**
 * The shared scenario workbench: the workspace scenarios (SIM-14), the draft of
 * the selected one, the element template, the input-confidence roll-up and the
 * run+poll machinery. Panoramica and the scenario builder both drive the same
 * lab so a run launched from either shows up everywhere without a reload.
 */
export function useScenarioLab(): ScenarioLab {
  const { t } = useTranslation("process");
  const queryClient = useQueryClient();
  const { process, runs: sectionRuns, refetchRuns, activeRunId, selectRun } = useSimulationSection();
  const bpmnModelId = process.bpmnModelId;
  const [params, setParams] = useSearchParams();

  const modelQuery = useBpmnModelQuery(bpmnModelId);
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
    if (polledRun && (activeRunId == null || polledRun.id === activeRunId)) return polledRun;
    if (activeRunId == null && pickedRunId != null) {
      return sectionRuns.find((r) => r.id === pickedRunId) ?? null;
    }
    return resolveActiveRun(sectionRuns, activeRunId != null ? String(activeRunId) : undefined);
  }, [polledRun, pickedRunId, sectionRuns, activeRunId]);

  // Finche' il workspace non risponde il pannello lavora sulla bozza del browser.
  const [storedDraft, setStoredDraft] = React.useState<ScenarioDraft>(() =>
    loadScenarioDraft(bpmnModelId),
  );

  const templateQuery = useQuery<ScenarioTemplate>({
    queryKey: ["workspace", "simulation-template", bpmnModelId],
    queryFn: () => fetchScenarioTemplate(bpmnModelId, null),
    enabled: bpmnXml !== null,
    staleTime: 60_000,
  });
  const template = templateQuery.data ?? null;
  // SIM-07: proposte di fonti dai file del cliente. Un errore qui non blocca lo scenario.
  const claimsQuery = useQuery<SimulationClaims>({
    queryKey: ["workspace", "simulation-claims", bpmnModelId],
    queryFn: () => fetchSimulationClaims(bpmnModelId, null),
    enabled: bpmnXml !== null,
    staleTime: 60_000,
  });
  const templateLoading = modelQuery.isLoading || (templateQuery.isLoading && bpmnXml !== null);

  // --- SIM-14: il workspace degli scenari -----------------------------------
  const workspaceKey = React.useMemo(() => ["workspace", "simulation-scenarios", bpmnModelId], [bpmnModelId]);
  const workspaceQuery = useQuery<ScenarioWorkspace>({
    queryKey: workspaceKey,
    queryFn: () => fetchScenarioWorkspace(bpmnModelId),
    enabled: bpmnXml !== null,
    staleTime: 30_000,
  });
  const workspace = workspaceQuery.data ?? null;
  // I salvataggi in coda leggono la revisione piu' recente, anche fra due render.
  const workspaceRef = React.useRef(workspace);
  React.useEffect(() => { workspaceRef.current = workspace; }, [workspace]);
  const setWorkspace = React.useCallback((next: ScenarioWorkspace) => {
    workspaceRef.current = next;
    queryClient.setQueryData(workspaceKey, next);
  }, [queryClient, workspaceKey]);

  const scenarios = workspaceScenarios(workspace);
  const requestedId = Number(params.get("scenario")) || null;
  const selectedScenario = scenarios.find((s) => s.id === requestedId) ?? workspace?.baseline ?? null;
  const selectScenario = React.useCallback((id: number | null) => {
    const next = new URLSearchParams(params);
    if (id == null) next.delete("scenario");
    else next.set("scenario", String(id));
    setParams(next, { replace: true });
  }, [params, setParams]);

  // Modifiche non ancora confermate dal server, per scenario.
  const [pending, setPending] = React.useState<Record<number, ScenarioDraft>>({});
  // Dopo un salvataggio, cio' che e' rimasto in attesa (= non salvato), letto fuori dal render.
  const pendingRef = React.useRef(pending);
  React.useEffect(() => { pendingRef.current = pending; }, [pending]);
  const [isSaving, setIsSaving] = React.useState(false);
  const [workspaceError, setWorkspaceError] = React.useState<string | null>(null);

  const seed = React.useCallback(
    (value: ScenarioDraft) => (template ? seedDraftFromTemplate(value, template) : value),
    [template],
  );
  const baselineDraft = React.useMemo(
    () => (workspace?.baseline ? seed(pending[workspace.baseline.id] ?? parseScenarioDraft(workspace.baseline.draft)) : null),
    [workspace, pending, seed],
  );
  const draftOf = React.useCallback(
    (scenario: WorkspaceScenario): ScenarioDraft => {
      const edited = pending[scenario.id];
      // Il nome e' quello del workspace (o quello appena scritto nel campo del pannello).
      return seed({ ...(edited ?? parseScenarioDraft(scenario.draft)), scenarioName: edited?.scenarioName ?? scenario.name });
    },
    [pending, seed],
  );

  const draft = React.useMemo(
    () => (selectedScenario ? draftOf(selectedScenario) : seed(storedDraft)),
    [selectedScenario, draftOf, seed, storedDraft],
  );

  const { provenance, confidence } = useInputConfidence(
    bpmnModelId,
    draft,
    template,
    bpmnXml !== null,
  );

  const queued = React.useRef<{ id: number; draft: ScenarioDraft } | null>(null);
  const readFailure = React.useCallback(async (err: unknown, scenarioId?: number) => {
    if (err instanceof HttpError && err.status === 409) {
      // Un'altra scheda ha cambiato lo scenario: per quello si riparte dal salvato,
      // le modifiche in attesa sugli altri restano.
      setPending((all) => (scenarioId === undefined ? {} : without(all, scenarioId)));
      if (scenarioId === undefined || queued.current?.id === scenarioId) queued.current = null;
      await workspaceQuery.refetch();
      setWorkspaceError(t("simulation.scenarios.conflict"));
      return;
    }
    setWorkspaceError(readError(err));
  }, [t, workspaceQuery]);

  // L'AS-IS nasce dalla bozza che il consulente aveva gia' nel browser.
  React.useEffect(() => {
    if (!workspace || workspace.baseline || !template || bootstrapping.has(bpmnModelId)) return;
    bootstrapping.add(bpmnModelId);
    const local = seed(loadScenarioDraft(bpmnModelId));
    putScenarioBaseline(bpmnModelId, { name: local.scenarioName.trim() || t("simulation.scenarios.asIsName"), draft: local })
      .then(setWorkspace)
      .catch(readFailure)
      .finally(() => bootstrapping.delete(bpmnModelId));
  }, [workspace, template, bpmnModelId, seed, setWorkspace, readFailure, t]);

  const persist = React.useCallback(async (scenarioId: number, next: ScenarioDraft) => {
    const current = workspaceRef.current;
    const scenario = workspaceScenarios(current).find((s) => s.id === scenarioId);
    if (!current?.baseline || !scenario) return;
    try {
      const name = next.scenarioName.trim();
      let updated: ScenarioWorkspace;
      if (scenario.kind === "baseline") {
        updated = await putScenarioBaseline(bpmnModelId, { name: name || scenario.name, draft: next, revision: scenario.revision });
      } else {
        const reference = seed(parseScenarioDraft(current.baseline.draft));
        // Il nome non e' una differenza dall'AS-IS: si salva a parte.
        const patch = diffScenario(reference, { ...next, scenarioName: reference.scenarioName });
        updated = await updateWorkspaceScenario(bpmnModelId, scenario.id, {
          patch,
          revision: scenario.revision,
          ...(name && name !== scenario.name ? { name } : {}),
        });
      }
      setWorkspace(updated);
      setWorkspaceError(null);
      setPending((all) => (all[scenarioId] === next ? without(all, scenarioId) : all));
    } catch (err) {
      await readFailure(err, scenarioId);
    }
  }, [bpmnModelId, seed, setWorkspace, readFailure]);

  // Un salvataggio alla volta: ognuno parte dalla revisione lasciata dal precedente.
  const saveChain = React.useRef<Promise<void>>(Promise.resolve());
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const flushSave = React.useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    const job = queued.current;
    queued.current = null;
    if (job) {
      setIsSaving(true);
      saveChain.current = saveChain.current
        .then(() => persist(job.id, job.draft))
        .finally(() => { if (mountedRef.current && !queued.current) setIsSaving(false); });
    }
    return saveChain.current;
  }, [persist]);
  React.useEffect(() => () => { void flushSave(); }, [flushSave]);

  const updateDraft = React.useCallback(
    (next: ScenarioDraft) => {
      if (!selectedScenario) {
        setStoredDraft(next);
        saveScenarioDraft(bpmnModelId, next);
        return;
      }
      // La copia nel browser resta quella dell'AS-IS: serve se il workspace non risponde.
      if (selectedScenario.kind === "baseline") saveScenarioDraft(bpmnModelId, next);
      setPending((all) => ({ ...all, [selectedScenario.id]: next }));
      queued.current = { id: selectedScenario.id, draft: next };
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => { void flushSave(); }, SAVE_DELAY_MS);
    },
    [bpmnModelId, selectedScenario, flushSave],
  );

  const mutate = React.useCallback(async (action: () => Promise<ScenarioWorkspace>): Promise<ScenarioWorkspace | null> => {
    await flushSave();
    try {
      const updated = await action();
      setWorkspace(updated);
      setWorkspaceError(null);
      return updated;
    } catch (err) {
      await readFailure(err);
      return null;
    }
  }, [flushSave, setWorkspace, readFailure]);

  const createScenario = React.useCallback(async (name: string, from?: WorkspaceScenario) => {
    const before = new Set(workspaceScenarios(workspaceRef.current).map((s) => s.id));
    const updated = await mutate(() => createWorkspaceScenario(bpmnModelId, { name, patch: from?.kind === "alternative" ? from.patch : [] }));
    const created = updated?.alternatives.find((s) => !before.has(s.id)) ?? null;
    if (created) selectScenario(created.id);
    return created;
  }, [bpmnModelId, mutate, selectScenario]);

  const deleteScenario = React.useCallback(async (scenario: WorkspaceScenario) => {
    const updated = await mutate(() => deleteWorkspaceScenario(bpmnModelId, scenario.id));
    if (updated && requestedId === scenario.id) selectScenario(null);
    return updated !== null;
  }, [bpmnModelId, mutate, requestedId, selectScenario]);

  const revertChange = React.useCallback(async (scenario: WorkspaceScenario, index: number) => {
    // La riga mostrata, non la sua posizione: un salvataggio in coda puo' rigenerare la patch.
    const target = scenario.patch[index];
    if (!target) return;
    await flushSave();
    const latest = workspaceScenarios(workspaceRef.current).find((s) => s.id === scenario.id);
    if (!latest || latest.kind !== "alternative") return;
    const key = JSON.stringify(target);
    const found = latest.patch.findIndex((op) => JSON.stringify(op) === key);
    if (found < 0) return;
    const patch = latest.patch.filter((_, i) => i !== found);
    setPending((all) => without(all, scenario.id));
    await mutate(() => updateWorkspaceScenario(bpmnModelId, latest.id, { patch, revision: latest.revision }));
  }, [bpmnModelId, flushSave, mutate]);

  const newSeed = React.useCallback(async () => {
    // Prima le modifiche in attesa: poi si rimanda l'AS-IS cosi' com'e' salvato, alla sua revisione.
    await flushSave();
    const seedValue = Math.floor(Math.random() * (WORKSPACE_SEED_MAX + 1));
    await mutate(() => {
      const baseline = workspaceRef.current?.baseline;
      if (!baseline) return Promise.reject(new Error(t("simulation.scenarios.unavailable")));
      return putScenarioBaseline(bpmnModelId, { name: baseline.name, draft: baseline.draft, revision: baseline.revision, seed: seedValue });
    });
  }, [bpmnModelId, mutate, flushSave, t]);

  const syncSection = React.useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ["workspace", "simulation-runs", bpmnModelId],
    });
    refetchRuns();
  }, [queryClient, bpmnModelId, refetchRuns]);

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

  const scenarioBlocker = React.useCallback((scenario: WorkspaceScenario) => {
    const value = draftOf(scenario);
    if (!scenarioResourceIssues(value).ready) return t("simulation.config.resourceSetupRequired");
    if (!scenarioParameterIssues(value).ready) return t("simulation.scenarios.fixParameters");
    return null;
  }, [draftOf, t]);

  /** Il run di una bozza: dentro il workspace porta lo scenario, le revisioni e il seed comune. */
  const submit = React.useCallback(async (value: ScenarioDraft, scenario: WorkspaceScenario | null) => {
    const current = workspaceRef.current;
    const latest = scenario ? workspaceScenarios(current).find((s) => s.id === scenario.id) ?? scenario : null;
    const ref = current && latest ? scenarioRef(current, latest) : null;
    return runProsimosSimulation(bpmnModelId, {
      ...scenarioToInput(latest ? { ...value, scenarioName: scenarioDisplayName(latest) } : value, bpmnXml),
      ...(ref ? { workspaceScenario: ref, seed: current?.seed ?? undefined } : {}),
      idempotencyKey:
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `${bpmnModelId}-${Date.now()}`,
    });
  }, [bpmnModelId, bpmnXml]);

  const handleRun = React.useCallback(async () => {
    if (!template || templateLoading || !bpmnXml || !scenarioResourceIssues(draft).ready) {
      setError(t("simulation.config.resourceSetupRequired"));
      return;
    }
    setIsRunning(true);
    setError(null);
    try {
      // Il run parte dallo scenario salvato: prima le modifiche in attesa.
      await flushSave();
      // Un run cita solo cio' che e' salvato: se il salvataggio non e' riuscito, prima quello.
      if (selectedScenario && pendingRef.current[selectedScenario.id]) throw new Error(t("simulation.scenarios.notSaved"));
      const run = await submit(draft, selectedScenario);
      setPolledRun(run);
      selectRun?.(run.id);
      syncSection();
      if (run.status === "pending") await pollRun(run.id);
      else { setPickedRunId(run.id); selectRun?.(run.id); }
    } catch (err) {
      setError(readError(err));
    } finally {
      if (mountedRef.current) setIsRunning(false);
    }
  }, [draft, bpmnXml, template, templateLoading, t, syncSection, pollRun, selectRun, flushSave, submit, selectedScenario]);

  const runScenario = React.useCallback(async (scenario: WorkspaceScenario) => {
    if (!template || !bpmnXml) return false;
    const blocker = scenarioBlocker(scenario);
    if (blocker) {
      setWorkspaceError(`${scenarioDisplayName(scenario)}: ${blocker}`);
      return false;
    }
    try {
      await flushSave();
      if (pendingRef.current[scenario.id]) throw new Error(t("simulation.scenarios.notSaved"));
      await submit(draftOf(scenario), scenario);
      syncSection();
      return true;
    } catch (err) {
      setWorkspaceError(`${scenarioDisplayName(scenario)}: ${readError(err)}`);
      return false;
    }
  }, [template, bpmnXml, scenarioBlocker, flushSave, submit, draftOf, syncSection, t]);

  return {
    bpmnXml,
    template,
    templateLoading,
    claims: claimsQuery.data ?? null,
    draft,
    updateDraft,
    provenance,
    confidence,
    activeRun,
    isRunning,
    isPending: activeRun?.status === "pending",
    error,
    handleRun,
    workspace,
    // Senza workspace il pannello resta utilizzabile sulla bozza del browser: lo si dice in chiaro.
    workspaceError: workspaceError ?? (workspaceQuery.error ? t("simulation.scenarios.unavailable") : null),
    selectedScenario,
    selectScenario,
    baselineDraft,
    isSaving,
    createScenario,
    deleteScenario,
    revertChange,
    newSeed,
    runScenario,
    scenarioBlocker,
  };
}

function without<T>(all: Record<number, T>, id: number): Record<number, T> {
  return Object.fromEntries(Object.entries(all).filter(([key]) => Number(key) !== id));
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
