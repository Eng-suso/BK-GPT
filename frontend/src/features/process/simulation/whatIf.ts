import { scaleTaskDurations } from "./experiments";
import type { ScenarioDraft } from "./simulationScenario";
import type { WhatIfChange } from "./simulationTypes";

/**
 * SIM-23: le modifiche tradotte da una frase, applicate alla bozza.
 *
 * Il modello traduce e basta (gate G4): qui ogni modifica diventa una bozza in
 * modo deterministico, come gli esperimenti dell'advisor. Il consulente vede
 * la differenza come una patch prima di tenerla, e il run lo lancia lui.
 */

export type WhatIfOutcome = {
  draft: ScenarioDraft;
  /** Le modifiche il cui ruolo o attivita' non c'e' piu' nella bozza: nessun effetto. */
  skipped: WhatIfChange[];
};

// Gli stessi limiti di `backend/simulation/whatif.py`: un processo piu' grande manda i primi, non fallisce.
const MAX_ACTIVITIES = 200;
const MAX_RESOURCES = 100;
const MAX_NAME_CHARS = 200;

/** Le attivita' e i ruoli da mostrare al modello, con i nomi del processo. */
export function whatIfContext(draft: ScenarioDraft, taskNames: Record<string, string>) {
  const name = (value: string) => value.slice(0, MAX_NAME_CHARS);
  return {
    activities: Object.keys(draft.tasks).slice(0, MAX_ACTIVITIES).map((id) => ({ id, name: name(taskNames[id] || id) })),
    resources: draft.resources.slice(0, MAX_RESOURCES).map((r) => ({ id: r.id, name: name(r.name || r.id), units: r.amount })),
  };
}

function applyOne(draft: ScenarioDraft, change: WhatIfChange): ScenarioDraft | null {
  switch (change.kind) {
    case "resource_units":
    case "resource_cost": {
      if (!draft.resources.some((r) => r.id === change.resource_id)) return null;
      const fields = change.kind === "resource_units" ? { amount: change.units } : { costPerHour: change.cost_per_hour };
      return {
        ...draft,
        resources: draft.resources.map((r) => (r.id === change.resource_id ? { ...r, ...fields, parametersConfirmed: false } : r)),
      };
    }
    case "activity_duration": {
      const task = draft.tasks[change.element_id];
      if (!task) return null;
      // Una nuova media scala tutte le durate dell'attivita' nella stessa proporzione:
      // altri ruoli, categorie e soglie restano coerenti con la principale.
      const factor = change.factor ?? (change.mean_minutes && task.meanMinutes > 0 ? change.mean_minutes / task.meanMinutes : null);
      if (!factor || !Number.isFinite(factor)) return null;
      return { ...draft, tasks: { ...draft.tasks, [change.element_id]: scaleTaskDurations(task, factor) } };
    }
    case "skip_activity": {
      const task = draft.tasks[change.element_id];
      if (!task) return null;
      // La frase non pone condizioni: la quota vale per tutti i casi, senza regola.
      return { ...draft, tasks: { ...draft.tasks, [change.element_id]: { ...task, skip: { percent: change.percent } } } };
    }
    case "demand": {
      // Piu' casi = meno tempo fra due arrivi, anche nelle fasce orarie.
      const shorter = (v: number | undefined) => (v === undefined ? undefined : v / change.factor);
      const arrival = draft.arrival
        ? {
            ...draft.arrival,
            stdMinutes: shorter(draft.arrival.stdMinutes),
            minMinutes: shorter(draft.arrival.minMinutes),
            maxMinutes: shorter(draft.arrival.maxMinutes),
            ...(draft.arrival.bands ? { bands: draft.arrival.bands.map((b) => ({ ...b, meanMinutes: b.meanMinutes / change.factor })) } : {}),
          }
        : undefined;
      return {
        ...draft,
        arrivalIntervalMinutes: draft.arrivalIntervalMinutes / change.factor,
        ...(arrival ? { arrival } : {}),
      };
    }
  }
}

export function applyWhatIf(draft: ScenarioDraft, changes: WhatIfChange[]): WhatIfOutcome {
  const skipped: WhatIfChange[] = [];
  let next = draft;
  for (const change of changes) {
    const applied = applyOne(next, change);
    if (applied) next = applied;
    else skipped.push(change);
  }
  return { draft: next, skipped };
}
