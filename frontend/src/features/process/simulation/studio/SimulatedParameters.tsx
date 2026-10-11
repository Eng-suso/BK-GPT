import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ProvenanceChip } from "../ProvenanceChip";
import { fetchScenarioTemplate } from "../simulationApi";
import { provenanceTip, type FieldProvenance } from "../simulationProvenance";
import { formatCurrency } from "../simulationResults";
import type { ScenarioElementProvenance, SimulationRun } from "../simulationTypes";
import { useScenarioProvenance } from "../useInputConfidence";
import { useSimulationSection } from "../useSimulationSection";
import { activityParameters, formatParameterDuration, hasTaskConfig } from "./activityParameters";
import {
  arrivalFromModel,
  elementFromModel,
  prioritiesFromModel,
  type ArrivalView,
  type AssignmentView,
  type BranchView,
  type CalendarView,
  type DurationByView,
  type DurationView,
} from "./modelParameters";
import { useRunModel, type IrRule } from "./runModel";

type Lang = "it" | "en";
type T = ReturnType<typeof useTranslation>["t"];

/** IR distribution kind -> the label key the scenario panel already uses. */
const DIST_KEY: Record<DurationView["kind"], string> = {
  fixed: "fixed",
  exponential: "expon",
  uniform: "uniform",
  normal: "norm",
  lognormal: "lognorm",
  gamma: "gamma",
};
const WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"];

function weekday(day: string, lang: Lang): string {
  const index = WEEKDAYS.indexOf(day);
  // 1 gennaio 2024 e' un lunedi'.
  return index < 0 ? day : new Intl.DateTimeFormat(lang === "it" ? "it-IT" : "en-US", { weekday: "short" }).format(new Date(2024, 0, 1 + index));
}

/**
 * SIM-20a: what the run simulated for the selected element and where each value
 * comes from, on the IR's five-level provenance. The run's own IR is the
 * source; runs from before it was kept fall back, saying so, on the v1 request.
 */
export function SimulatedParameters({ run, elementId, inSummary }: { run: SimulationRun; elementId: string; inSummary: boolean }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang: Lang = i18n.language.startsWith("it") ? "it" : "en";
  const title = t("simulation.activityInspector.title");
  const runModel = useRunModel(run.id);
  const provenance = useScenarioProvenance(run.bpmn_model_id);
  const isGateway = runModel.data?.gateways.some((g) => g.element_id === elementId) ?? false;
  const template = useQuery({
    queryKey: ["workspace", "simulation-template", run.bpmn_model_id],
    queryFn: () => fetchScenarioTemplate(run.bpmn_model_id, null),
    enabled: isGateway,
    staleTime: 60_000,
  });
  const element = provenance.data?.elements.find((el) => el.element_id === elementId);
  const { bpmnXml } = useSimulationSection();
  const isStart = React.useMemo(() => isStartEvent(bpmnXml, elementId), [bpmnXml, elementId]);

  let body: React.ReactNode;
  if (runModel.isLoading && !runModel.data) {
    body = <p className="sim-help" role="status">{t("simulation.activityInspector.loading")}</p>;
  } else if (runModel.data) {
    const view = elementFromModel(runModel.data, elementId, element, template.data);
    const arrival = !view && isStart ? arrivalFromModel(runModel.data) : null;
    body = arrival
      ? <>
          <Arrival arrival={arrival} lang={lang} t={t} provenanceState={provenance} />
          <Priorities priorities={prioritiesFromModel(runModel.data)} t={t} />
        </>
      : !view
      ? <p className="sim-help">{t("simulation.activityInspector.notSimulated")}</p>
      : view.kind === "activity"
        ? <>
            {view.assignments.length > 1 && <p className="sim-help">{t("simulation.activityInspector.sharedActivity")}</p>}
            <FixedCost run={run} elementId={elementId} lang={lang} t={t} />
            {view.durationBy && <DurationBy durationBy={view.durationBy} lang={lang} t={t} />}
            {view.assignments.map((assignment, index) => (
              <Assignment key={index} assignment={assignment} index={index} total={view.assignments.length} lang={lang} t={t} provenanceState={provenance} />
            ))}
          </>
        : <Branches branches={view.branches} provenance={view.provenance} lang={lang} t={t} provenanceState={provenance} />;
  } else {
    // Ripiego dichiarato: run anteriore al modello conservato, o modello non arrivato.
    body = <>
      <p className="sim-help" role={runModel.isError ? "alert" : undefined}>
        {t(runModel.isError ? "simulation.activityInspector.modelError" : "simulation.activityInspector.legacyNote")}
      </p>
      <LegacyParameters run={run} elementId={elementId} isActivity={inSummary || hasTaskConfig(run.request, elementId)} element={element} lang={lang} t={t} provenanceState={provenance} />
      <FixedCost run={run} elementId={elementId} lang={lang} t={t} />
    </>;
  }

  return <section className="sim-activity-params" aria-label={title}>
    <h4>{title}</h4>
    {body}
  </section>;
}

type ProvenanceState = { isLoading: boolean; isError: boolean; data?: unknown };

function OriginRow({ field, t, provenanceState }: { field: FieldProvenance; t: T; provenanceState: ProvenanceState }): React.JSX.Element {
  const confidence = t(`simulation.provenance.confidence.${field.confidence}`);
  return <div><dt>{t("simulation.activityInspector.origin")}</dt><dd>
    {provenanceState.isLoading && !provenanceState.data
      ? <span className="sim-param-note" role="status">{t("simulation.activityInspector.provenanceLoading")}</span>
      : provenanceState.isError && !provenanceState.data
        ? "—"
        : <><ProvenanceChip field={field} hideNote /><span className="sim-param-note">{t("simulation.activityInspector.confidence", { level: confidence })}</span></>}
  </dd></div>;
}

function ProvenanceFoot({ field, t, provenanceState }: { field: FieldProvenance; t: T; provenanceState: ProvenanceState }): React.JSX.Element | null {
  if (provenanceState.isError && !provenanceState.data) return <p className="sim-help" role="alert">{t("simulation.activityInspector.provenanceError")}</p>;
  if (provenanceState.isLoading) return null;
  return <p className="sim-help">{provenanceTip(field, t)}</p>;
}

function calendarText(calendar: CalendarView, lang: Lang, t: T): string {
  if (calendar.standard) return t("simulation.activityInspector.standardCalendar");
  const periods = calendar.periods.map((p) => {
    const days = p.fromDay === p.toDay ? weekday(p.fromDay, lang) : `${weekday(p.fromDay, lang)}–${weekday(p.toDay, lang)}`;
    return `${days} ${p.begin}–${p.end}`;
  });
  return periods.length ? `${calendar.name} · ${periods.join(", ")}` : calendar.name;
}

function DurationRows({ duration, lang, t, meanLabel }: { duration: DurationView; lang: Lang; t: T; meanLabel?: string }): React.JSX.Element {
  const distribution = t(`simulation.config.dist.${DIST_KEY[duration.kind]}`);
  const mean = meanLabel ?? t("simulation.activityInspector.duration");
  const f = (seconds: number) => formatParameterDuration(seconds, lang);
  if (duration.kind === "fixed") {
    return <>
      <div><dt>{mean}</dt><dd>{f(duration.valueSeconds)}</dd></div>
      <div><dt>{t("simulation.activityInspector.distribution")}</dt><dd>{distribution}</dd></div>
    </>;
  }
  if (duration.kind === "uniform") {
    return <div><dt>{t("simulation.activityInspector.distribution")}</dt><dd>{distribution}
      <span className="sim-param-note">{t("simulation.activityInspector.bounds", { min: f(duration.minSeconds), max: f(duration.maxSeconds) })}</span>
    </dd></div>;
  }
  return <>
    <div><dt>{mean}</dt><dd>{f(duration.meanSeconds)}</dd></div>
    <div><dt>{t("simulation.activityInspector.distribution")}</dt><dd>{distribution}
      {duration.stdSeconds != null && <span className="sim-param-note">{t("simulation.activityInspector.std", { value: f(duration.stdSeconds) })}</span>}
      <span className="sim-param-note">{t("simulation.activityInspector.bounds", { min: f(duration.minSeconds), max: f(duration.maxSeconds) })}</span>
    </dd></div>
  </>;
}

function Assignment({ assignment, index, total, lang, t, provenanceState }: { assignment: AssignmentView; index: number; total: number; lang: Lang; t: T; provenanceState: ProvenanceState }): React.JSX.Element {
  return <div className="sim-param-group">
    {total > 1 && <h5>{t("simulation.activityInspector.assignment", { n: index + 1, total })}</h5>}
    <dl>
      {assignment.resource && <div><dt>{t("simulation.activityInspector.resource")}</dt><dd>{t("simulation.activityInspector.resourceValue", { name: assignment.resource.name, amount: assignment.resource.amount, cost: formatCurrency(assignment.resource.costPerHour, lang) })}</dd></div>}
      {assignment.resource && <div><dt>{t("simulation.activityInspector.calendar")}</dt><dd>{calendarText(assignment.resource.calendar, lang, t)}</dd></div>}
      <DurationRows duration={assignment.duration} lang={lang} t={t} />
      <OriginRow field={assignment.provenance} t={t} provenanceState={provenanceState} />
    </dl>
    <ProvenanceFoot field={assignment.provenance} t={t} provenanceState={provenanceState} />
  </div>;
}

/** L'evento di inizio: come arrivavano i casi nel run (A2-3). */
function Arrival({ arrival, lang, t, provenanceState }: { arrival: ArrivalView; lang: Lang; t: T; provenanceState: ProvenanceState }): React.JSX.Element {
  return <div className="sim-param-group">
    <h5>{t("simulation.activityInspector.arrivals")}</h5>
    <dl>
      <DurationRows duration={arrival.duration} lang={lang} t={t} meanLabel={t("simulation.activityInspector.interarrival")} />
      <div><dt>{t("simulation.activityInspector.arrivalCalendar")}</dt><dd>{calendarText(arrival.calendar, lang, t)}</dd></div>
      <OriginRow field={arrival.provenance} t={t} provenanceState={provenanceState} />
    </dl>
    <ProvenanceFoot field={arrival.provenance} t={t} provenanceState={provenanceState} />
  </div>;
}

/** SIM-12: le priorita' dei casi che il run ha simulato; niente se non ce n'erano. */
function Priorities({ priorities, t }: { priorities: { level: number; condition: IrRule[][] }[]; t: T }): React.JSX.Element | null {
  if (priorities.length === 0) return null;
  return <div className="sim-param-group">
    <h5>{t("simulation.config.priorities")}</h5>
    <dl>
      {priorities.map((p) => <div key={p.level}><dt>{t("simulation.config.priorityLevel", { level: p.level })}</dt><dd>{conditionText(p.condition, t)}</dd></div>)}
    </dl>
    <p className="sim-help">{t("simulation.activityInspector.prioritiesNote")}</p>
  </div>;
}

/** SIM-32: le durate per categoria che il run ha simulato; gli altri casi usano quelle delle risorse. */
function DurationBy({ durationBy, lang, t }: { durationBy: DurationByView; lang: Lang; t: T }): React.JSX.Element {
  return <div className="sim-param-group">
    <h5>{t("simulation.activityInspector.durationBy", { attribute: durationBy.attribute })}</h5>
    {durationBy.variants.map((variant) => (
      <div key={variant.value}>
        <p className="sim-param-note">{t("simulation.activityInspector.durationByCategory", { attribute: durationBy.attribute, value: variant.value })}</p>
        <dl><DurationRows duration={variant.duration} lang={lang} t={t} /></dl>
      </div>
    ))}
    <p className="sim-help">{t("simulation.activityInspector.durationByOthers")}</p>
  </div>;
}

/** SIM-10: il costo fisso per esecuzione che lo scenario dava all'attivita'. */
function FixedCost({ run, elementId, lang, t }: { run: SimulationRun; elementId: string; lang: Lang; t: T }): React.JSX.Element | null {
  const tasks = Array.isArray(run.request.tasks) ? (run.request.tasks as { element_id?: string; fixed_cost?: number | null }[]) : [];
  const cost = tasks.find((task) => task.element_id === elementId)?.fixed_cost;
  if (!cost) return null;
  return <p className="sim-help">{t("simulation.activityInspector.fixedCost", { value: formatCurrency(cost, lang) })}</p>;
}

/** L'elemento e' un evento di inizio del BPMN del processo? */
function isStartEvent(bpmnXml: string | null | undefined, elementId: string): boolean {
  if (!bpmnXml) return false;
  const document = new DOMParser().parseFromString(bpmnXml, "application/xml");
  return Array.from(document.getElementsByTagNameNS("*", "startEvent")).some((node) => node.getAttribute("id") === elementId);
}

/** Una condizione dell'IR come frase: condizioni in "e", gruppi in "oppure". */
function conditionText(groups: IrRule[][], t: T): string {
  return groups
    .map((group) => group.map((rule) => `${rule.attribute} ${rule.operator} ${rule.value}`).join(` ${t("simulation.activityInspector.and")} `))
    .join(` ${t("simulation.activityInspector.or")} `);
}

function Branches({ branches, provenance, lang, t, provenanceState }: { branches: BranchView[]; provenance: FieldProvenance; lang: Lang; t: T; provenanceState: ProvenanceState }): React.JSX.Element {
  const percent = new Intl.NumberFormat(lang === "it" ? "it-IT" : "en-US", { style: "percent", maximumFractionDigits: 1 });
  return <div className="sim-param-group">
    <dl>
      {branches.map((branch) => (
        <div key={branch.flowId}><dt>{branch.label}</dt><dd>
          {branch.condition ? conditionText(branch.condition, t) : percent.format(branch.probability)}
          {branch.condition && <span className="sim-param-note">{t("simulation.activityInspector.byRule")}</span>}
        </dd></div>
      ))}
      <OriginRow field={provenance} t={t} provenanceState={provenanceState} />
    </dl>
    <ProvenanceFoot field={provenance} t={t} provenanceState={provenanceState} />
  </div>;
}

/** Runs from before the model was kept: read the v1 request, as before. */
function LegacyParameters({ run, elementId, isActivity, element, lang, t, provenanceState }: { run: SimulationRun; elementId: string; isActivity: boolean; element?: ScenarioElementProvenance; lang: Lang; t: T; provenanceState: ProvenanceState }): React.JSX.Element {
  const params = isActivity ? activityParameters(run.request, elementId, element?.kind === "activity" ? element : undefined) : null;
  if (!params) return <p className="sim-help">{t("simulation.activityInspector.notActivity")}</p>;
  const f = (seconds: number) => formatParameterDuration(seconds, lang);
  return <div className="sim-param-group">
    <dl>
      <div><dt>{t("simulation.activityInspector.duration")}</dt><dd>{f(params.meanSeconds)}{params.usesDefault && <span className="sim-param-note">{t("simulation.activityInspector.defaultDuration")}</span>}</dd></div>
      <div><dt>{t("simulation.activityInspector.distribution")}</dt><dd>{t(`simulation.config.dist.${params.distribution}`)}
        {params.std && <span className="sim-param-note">{t(params.std.assumed ? "simulation.activityInspector.stdAssumed" : "simulation.activityInspector.std", { value: f(params.std.seconds) })}</span>}
        {params.bounds && <span className="sim-param-note">{t("simulation.activityInspector.bounds", { min: f(params.bounds.minSeconds), max: f(params.bounds.maxSeconds) })}</span>}
      </dd></div>
      {params.resource && <div><dt>{t("simulation.activityInspector.resource")}</dt><dd>{t("simulation.activityInspector.resourceValue", { name: params.resource.name, amount: params.resource.amount, cost: formatCurrency(params.resource.costPerHour, lang) })}</dd></div>}
      {params.resource && <div><dt>{t("simulation.activityInspector.calendar")}</dt><dd>{params.resource.calendar ?? t("simulation.activityInspector.standardCalendar")}</dd></div>}
      <OriginRow field={params.provenance} t={t} provenanceState={provenanceState} />
    </dl>
    <ProvenanceFoot field={params.provenance} t={t} provenanceState={provenanceState} />
  </div>;
}
