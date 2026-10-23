import type { DurationDraft, ScenarioDraft, TaskDraft } from "./simulationScenario";
import type { Experiment } from "./simulationTypes";

/**
 * SIM-22: un esperimento dell'advisor applicato alla bozza dello scenario.
 * La bozza cambia solo dove l'esperimento dice; il risultato vero viene dal
 * run, non dalla stima dell'advisor.
 */

/** Il ruolo del pannello che corrisponde a un pool del motore: stesso nome, o chi fa l'attivita'. */
function resourceFor(draft: ScenarioDraft, poolName: string | null | undefined, fallbackId?: string): string | undefined {
  const byName = poolName ? draft.resources.find((r) => r.name.toLowerCase() === poolName.toLowerCase())?.id : undefined;
  return byName ?? fallbackId;
}

function scaled<T extends DurationDraft>(duration: T, factor: number): T {
  const times = (v: number | undefined) => (v === undefined ? undefined : v * factor);
  return {
    ...duration,
    meanMinutes: duration.meanMinutes * factor,
    stdMinutes: times(duration.stdMinutes),
    minMinutes: times(duration.minMinutes),
    maxMinutes: times(duration.maxMinutes),
  };
}

/** Tutte le durate dell'attivita': base, altri ruoli, per categoria e per soglia. */
function automated(task: TaskDraft, factor: number): TaskDraft {
  return {
    ...scaled(task, factor),
    ...(task.otherAssignments ? { otherAssignments: task.otherAssignments.map((a) => scaled(a, factor)) } : {}),
    ...(task.durationBy ? { durationBy: {
      ...task.durationBy,
      variants: Object.fromEntries(Object.entries(task.durationBy.variants).map(([k, v]) => [k, scaled(v, factor)])),
      ...(task.durationBy.thresholds ? { thresholds: task.durationBy.thresholds.map((th) => ({ ...th, duration: scaled(th.duration, factor) })) } : {}),
    } } : {}),
  };
}

export function experimentDraft(draft: ScenarioDraft, exp: Experiment, scenarioName: string): ScenarioDraft {
  const serving = exp.target_el ? draft.tasks[exp.target_el]?.resourceId : undefined;
  if (exp.kind === "remove_step") {
    // SIM-22b: tolta a tutti i casi, come un salto al 100%: il motore la scavalca davvero.
    const task = exp.target_el ? draft.tasks[exp.target_el] : undefined;
    if (!task || !exp.target_el) return draft;
    return { ...draft, scenarioName, tasks: { ...draft.tasks, [exp.target_el]: { ...task, skip: { percent: 100 } } } };
  }
  if (exp.kind === "automate") {
    const task = exp.target_el ? draft.tasks[exp.target_el] : undefined;
    if (!task || !exp.target_el) return draft;
    return { ...draft, scenarioName, tasks: { ...draft.tasks, [exp.target_el]: automated(task, 1 - (exp.share ?? 0.5)) } };
  }
  const target = resourceFor(draft, exp.pool_name, serving);
  const donor = exp.kind === "reallocate" ? resourceFor(draft, exp.donor_pool_name) : undefined;
  // Un ruolo da cui spostare che non si ritrova, o che e' lo stesso: niente da fare.
  if (exp.kind === "reallocate" && (!donor || donor === target)) return draft;
  return {
    ...draft,
    scenarioName,
    resources: draft.resources.map((r) => {
      if (r.id === target) return { ...r, amount: r.amount + 1, parametersConfirmed: false };
      if (r.id === donor) return { ...r, amount: Math.max(1, r.amount - 1), parametersConfirmed: false };
      return r;
    }),
  };
}
