/**
 * What the inspector shows for one element of a run's Simulation IR (SIM-20a):
 * every assignment of an activity (resource, calendar, duration with all its
 * parameters) and every branch of a gateway (probability or rule), each with
 * its provenance on the IR's five-level scale.
 *
 * The IR is the truth of the run: a parameter without provenance is an
 * assumption nobody stated, never a value the consultant chose.
 *
 * Pure: no IO, no React.
 */

import {
  activityProvenance,
  gatewayProvenance,
  type FieldProvenance,
} from "../simulationProvenance";
import type { ParameterProvenance, ScenarioElementProvenance, ScenarioTemplate } from "../simulationTypes";
import type { IrDistribution, IrRule, RunModel } from "./runModel";

/** The calendar `ir/from_request.py` gives every resource without one. */
export const STANDARD_CALENDAR_ID = "delir-calendar-standard";

export type DurationView =
  | { kind: "fixed"; valueSeconds: number }
  | { kind: "uniform"; minSeconds: number; maxSeconds: number }
  | {
      kind: "exponential" | "normal" | "lognormal" | "gamma";
      meanSeconds: number;
      /** Spread; the exponential has none of its own. */
      stdSeconds: number | null;
      minSeconds: number;
      maxSeconds: number;
    };

export type CalendarView =
  | { standard: true }
  | { standard: false; name: string; periods: { fromDay: string; toDay: string; begin: string; end: string }[] };

export type AssignmentView = {
  resource: { name: string; amount: number; costPerHour: number; calendar: CalendarView } | null;
  duration: DurationView;
  provenance: FieldProvenance;
};

export type BranchView = {
  flowId: string;
  /** Flow name, else target name, else the flow id. */
  label: string;
  probability: number;
  /** OR of AND groups; null = the branch is chosen by probability. */
  condition: IrRule[][] | null;
  provenance: FieldProvenance;
};

export type ArrivalView = { duration: DurationView; calendar: CalendarView; provenance: FieldProvenance };

export type ElementView =
  | { kind: "activity"; assignments: AssignmentView[] }
  | { kind: "gateway"; branches: BranchView[]; provenance: FieldProvenance };

/** Come arrivavano i casi nel run (A2-3): lo mostra l'evento di inizio. */
export function arrivalFromModel(model: RunModel): ArrivalView | null {
  if (!model.arrival) return null;
  return {
    duration: durationView(model.arrival.interarrival),
    calendar: calendarView(model, model.arrival.calendar_id),
    provenance: parameterProvenance(model.arrival.provenance, activityProvenance(false, undefined), activityProvenance(true, undefined)),
  };
}

export function durationView(distribution: IrDistribution): DurationView {
  switch (distribution.kind) {
    case "fixed":
      return { kind: "fixed", valueSeconds: distribution.value };
    case "uniform":
      return { kind: "uniform", minSeconds: distribution.minimum, maxSeconds: distribution.maximum };
    case "exponential":
      return { kind: "exponential", meanSeconds: distribution.mean, stdSeconds: null, minSeconds: distribution.minimum, maxSeconds: distribution.maximum };
    case "normal":
      return { kind: "normal", meanSeconds: distribution.mean, stdSeconds: distribution.std, minSeconds: distribution.minimum, maxSeconds: distribution.maximum };
    case "lognormal":
    case "gamma":
      return {
        kind: distribution.kind,
        meanSeconds: distribution.mean,
        stdSeconds: Math.sqrt(distribution.variance),
        minSeconds: distribution.minimum,
        maxSeconds: distribution.maximum,
      };
  }
}

/** The IR's own provenance, with the structural one (discovery) as context. */
function parameterProvenance(
  own: ParameterProvenance | null | undefined,
  structural: FieldProvenance,
  manual: FieldProvenance,
): FieldProvenance {
  if (!own) return structural;
  const sources = [...own.sources, ...(structural.sources ?? [])];
  const base: FieldProvenance =
    own.origin === "manual"
      ? manual
      : { origin: own.origin, confidence: own.confidence ?? structural.confidence, evidence: structural.evidence, hintRef: structural.hintRef };
  return { ...base, confidence: own.confidence ?? base.confidence, sources: sources.length ? sources : undefined };
}

function calendarView(model: RunModel, calendarId: string): CalendarView {
  if (calendarId === STANDARD_CALENDAR_ID) return { standard: true };
  const calendar = model.calendars.find((c) => c.id === calendarId);
  if (!calendar) return { standard: false, name: calendarId, periods: [] };
  return {
    standard: false,
    name: calendar.name,
    periods: calendar.periods.map((p) => ({ fromDay: p.from_day, toDay: p.to_day, begin: p.begin.slice(0, 5), end: p.end.slice(0, 5) })),
  };
}

export function elementFromModel(
  model: RunModel,
  elementId: string,
  element?: ScenarioElementProvenance,
  template?: ScenarioTemplate | null,
): ElementView | null {
  const activity = model.activities.find((a) => a.element_id === elementId);
  if (activity) {
    const resources = new Map(model.pools.flatMap((pool) => pool.resources).map((r) => [r.id, r]));
    const structural = activityProvenance(false, element);
    return {
      kind: "activity",
      assignments: activity.assignments.map((assignment) => {
        const resource = resources.get(assignment.resource_id);
        return {
          resource: resource
            ? { name: resource.name, amount: resource.amount, costPerHour: resource.cost_per_hour, calendar: calendarView(model, resource.calendar_id) }
            : null,
          duration: durationView(assignment.duration),
          provenance: parameterProvenance(assignment.provenance, structural, activityProvenance(true, element)),
        };
      }),
    };
  }

  const gateway = model.gateways.find((g) => g.element_id === elementId);
  if (!gateway) return null;
  const flows = new Map(
    (template?.gateways.find((g) => g.element_id === elementId)?.branches ?? []).map((b) => [b.flow_id, b.flow_name || b.target_name]),
  );
  const touched = gateway.branches.some((b) => b.provenance != null || b.condition != null);
  const structural = gatewayProvenance(touched, element);
  return {
    kind: "gateway",
    provenance: structural,
    branches: gateway.branches.map((branch) => ({
      flowId: branch.flow_id,
      label: flows.get(branch.flow_id) || branch.flow_id,
      probability: branch.probability,
      condition: branch.condition?.any_of ?? null,
      provenance: parameterProvenance(branch.provenance, gatewayProvenance(false, element), gatewayProvenance(true, element)),
    })),
  };
}
