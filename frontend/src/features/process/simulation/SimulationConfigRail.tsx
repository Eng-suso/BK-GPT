import React from "react";
import { useTranslation } from "react-i18next";
import { PanelLeftClose, Plus, X } from "lucide-react";

import { DetailPanelSection } from "@/components/panel";
import { StatusIndicator, type StatusTone } from "@/components/status";
import { EmptyState } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";
import { cn } from "@/lib/utils";

import type { ScenarioTemplate, SimulationRun } from "./simulationTypes";
import {
  newResourceId,
  resourceParametersValid,
  scenarioParameterIssues,
  roleLabel,
  scenarioResourceIssues,
  taskResourceIds,
  withValidOtherAssignments,
  type ScenarioDraft,
} from "./simulationScenario";
import type { InputConfidence } from "./simulationProvenance";
import { ProvenanceChip } from "./ProvenanceChip";
import { TaskDurationFields } from "./TaskDurationFields";
import { OtherAssignments } from "./OtherAssignments";
import { CalendarsSection } from "./CalendarsSection";
import { CaseAttributesSection } from "./CaseAttributesSection";
import { GatewayModeToggle, GatewayRulesEditor } from "./GatewayRulesEditor";
import { caseRuleIssues, type GatewayRulesDraft } from "./caseRules";

const RUN_TONE: Record<SimulationRun["status"], StatusTone> = {
  pending: "pending",
  completed: "ok",
  failed: "danger",
};

type SimulationConfigRailProps = {
  template: ScenarioTemplate | null;
  templateLoading: boolean;
  draft: ScenarioDraft;
  onDraftChange: (next: ScenarioDraft) => void;
  isRunning: boolean;
  /** Cosa dice il pulsante mentre il run aspetta: in coda o in corso (P0.3). */
  runningLabel?: string;
  error: string | null;
  onRun: () => void;
  focusElementId: string | null;
  /** Past-runs picker in the footer — hidden when the section has its own switcher. */
  runs?: SimulationRun[];
  activeRunId?: number | null;
  onSelectRun?: (run: SimulationRun) => void;
  /** Collapse affordance — only shown in the resizable-rail layout. */
  onCollapse?: () => void;
  /** Drop the card border / internal scroll when the parent page already scrolls. */
  embedded?: boolean;
  workspace?: boolean;
  /** Per-field input-confidence badges (phase 5). */
  provenance?: InputConfidence | null;
};

/**
 * Renders an editable simulation configuration panel for scenario settings, resources, activities, and gateways.
 *
 * @param template - The scenario template that defines available activities and gateways.
 * @param templateLoading - Whether the scenario template is still loading.
 * @param draft - The current editable simulation configuration.
 * @param onDraftChange - Called when the configuration changes.
 * @param isRunning - Whether a simulation run is in progress.
 * @param error - An error message to display.
 * @param runs - Previously completed or attempted simulation runs.
 * @param activeRunId - The identifier of the selected previous run.
 * @param onRun - Called to start a simulation run.
 * @param onSelectRun - Called when a previous run is selected.
 * @param focusElementId - The identifier of an activity or gateway to scroll into view and highlight.
 * @param onCollapse - Called when the panel collapse control is activated.
 * @param embedded - Whether to render the panel in an embedded layout.
 * @param workspace - Whether to render workspace navigation and layout.
 * @param provenance - Optional metadata describing the source of configuration values.
 * @returns The simulation configuration panel.
 */
export function SimulationConfigRail({
  template,
  templateLoading,
  draft,
  onDraftChange,
  isRunning,
  runningLabel,
  error,
  runs,
  activeRunId,
  onRun,
  onSelectRun,
  focusElementId,
  onCollapse,
  embedded = false,
  workspace = false,
  provenance,
}: SimulationConfigRailProps): React.JSX.Element {
  const { t } = useTranslation("process");
  const scrollRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!focusElementId || !scrollRef.current) return;
    const node = scrollRef.current.querySelector<HTMLElement>(
      `[data-sim-el="${CSS.escape(focusElementId)}"]`,
    );
    node?.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
    node?.classList.add("sim-el-flash");
    const timer = window.setTimeout(() => node?.classList.remove("sim-el-flash"), 1200);
    return () => window.clearTimeout(timer);
  }, [focusElementId]);

  const patch = (partial: Partial<ScenarioDraft>) =>
    onDraftChange({ ...draft, ...partial });
  const num = (raw: string) => (raw === "" ? 0 : Number(raw));
  const resourceIssues = scenarioResourceIssues(draft);
  const parameterIssues = scenarioParameterIssues(draft);
  const calendars = draft.calendars ?? [];
  const attributes = draft.caseAttributes ?? [];
  const gatewayRules = draft.gatewayRules ?? {};
  const ruleIssues = caseRuleIssues(attributes, gatewayRules);
  const attributeUse = Object.fromEntries(attributes.map((a) => [a.id,
    Object.values(gatewayRules).filter((branches) => Object.values(branches).flat(2).some((r) => r.attributeId === a.id)).length]));
  const canRun = Boolean(template) && !templateLoading && resourceIssues.ready && parameterIssues.ready && ruleIssues.ready;
  const updateResource = (id: string, fields: Partial<ScenarioDraft["resources"][number]>) =>
    patch({ resources: draft.resources.map((r) => r.id === id ? { ...r, ...fields } : r) });

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col ui-surface ui-surface-panel",
        workspace && "sim-config-workspace",
        embedded ? "" : "overflow-hidden shadow-sm",
      )}
    >
      <header className={cn("flex min-h-[52px] items-center justify-between gap-3 border-b border-border bg-card px-4 py-3", workspace && "sticky top-0 z-10 flex-wrap")}>
        <div className="min-w-0">
          {!workspace && <p className="eyebrow">{t("simulation.scenario.eyebrow")}</p>}
          {workspace ? <nav aria-label={t("simulation.workspace.sections")} className="flex flex-wrap gap-1">
            {["globals", "resources", "calendars", "activities", "attributes", ...(template?.gateways.length ? ["gateways"] : [])].map((key) => <button type="button" key={key} className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring" onClick={() => {
              const sections = scrollRef.current?.querySelectorAll("section");
              const target = Array.from(sections ?? []).find((section) => section.querySelector("h4")?.textContent?.startsWith(t(`simulation.config.${key}`)));
              target?.scrollIntoView({ block: "start" });
            }}>{t(`simulation.config.${key}`)}</button>)}
          </nav> :
          <h3 className="mt-0.5 truncate text-sm font-semibold text-foreground">
            {t("simulation.scenario.title")}
          </h3>}
        </div>
        {embedded ? (
          <Button
            type="button"
            size="sm"
            className="shrink-0"
            disabled={isRunning || !canRun}
            onClick={onRun}
          >
            {isRunning ? runningLabel ?? t("simulation.running") : t("simulation.run")}
          </Button>
        ) : (
          onCollapse && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="size-8 shrink-0 p-0 text-muted-foreground"
              onClick={onCollapse}
              title={t("simulation.config.collapse")}
            >
              <PanelLeftClose className="size-4" />
            </Button>
          )
        )}
        {workspace && error && <p role="alert" className="basis-full text-sm text-destructive">{error}</p>}
      </header>

      <div
        ref={scrollRef}
        className={cn("px-4", workspace && "sim-config-body", embedded ? "" : "min-h-0 flex-1 overflow-auto")}
      >
        <DetailPanelSection title={t("simulation.config.globals")}>
          <div className="sim-general-fields grid gap-2.5">
            <label className="grid gap-1.5">
              <span className="text-xs text-muted-foreground">
                {t("simulation.fields.scenarioName")}
              </span>
              <Input
                value={draft.scenarioName}
                onChange={(e) => patch({ scenarioName: e.target.value })}
              />
            </label>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <NumberField
                label={t("simulation.fields.cases")}
                value={draft.totalCases}
                min={1}
                max={100000}
                onChange={(v) => patch({ totalCases: v })}
              />
              <NumberField
                label={t("simulation.fields.arrivalMin")}
                value={draft.arrivalIntervalMinutes}
                min={1}
                onChange={(v) => patch({ arrivalIntervalMinutes: v })}
              />
              <NumberField
                label={t("simulation.config.defaultDurationMin")}
                value={draft.defaultTaskMinutes}
                min={1}
                onChange={(v) => patch({ defaultTaskMinutes: v })}
              />
            </div>
            {provenance && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-0.5">
                <ChipRow
                  label={t("simulation.fields.cases")}
                  field={provenance.globals.cases}
                />
                <ChipRow
                  label={t("simulation.fields.arrivalMin")}
                  field={provenance.globals.arrival}
                />
              </div>
            )}
          </div>
        </DetailPanelSection>

        <DetailPanelSection
          title={t("simulation.config.resources")}
          action={
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 gap-1 px-2 text-xs"
              onClick={() =>
                patch({
                  resources: [
                    ...draft.resources,
                    {
                      id: newResourceId(draft.resources),
                      name: `${t("simulation.fields.resourcePool")} ${draft.resources.length + 1}`,
                      costPerHour: 0,
                      parametersConfirmed: false,
                      amount: 1,
                    },
                  ],
                })
              }
            >
              <Plus className="size-3.5" />
              {t("simulation.config.addResource")}
            </Button>
          }
        >
          <div className="mb-3 grid gap-2">
            <p className="text-sm leading-relaxed text-muted-foreground">{t("simulation.config.resourceOriginHint")}</p>
            {provenance && <ProvenanceChip field={provenance.resources} />}
          </div>
          {draft.resources.length === 0 && (
            <EmptyState variant="inline" title={t(templateLoading ? "simulation.loading" : "simulation.config.noResources")} description={template ? t("simulation.config.noResourcesHint") : undefined} />
          )}
          <ul className="grid gap-3">
            {draft.resources.map((resource) => {
              const assigned = Object.values(draft.tasks).filter((task) => taskResourceIds(task).includes(resource.id)).length;
              const confirmed = resource.parametersConfirmed !== false && resourceParametersValid(resource);
              const context = [resource.source?.pool_name, resource.source?.parent_name].filter(Boolean).join(" / ");
              return (
                <li key={resource.id} data-resource-id={resource.id} className="min-w-0 rounded-lg border border-border bg-card p-3">
                  <div className="mb-3 flex items-start justify-between gap-2">
                    <div className="min-w-0 grid gap-1">
                      <p className="text-xs font-medium text-muted-foreground">{t(`simulation.config.resourceSource.${resource.source?.kind ?? "manual"}`)}</p>
                      {context && <p className="break-words text-xs text-muted-foreground">{context}</p>}
                      <StatusIndicator tone={confirmed ? "ok" : "pending"} label={t(confirmed ? "simulation.config.resourceConfirmed" : "simulation.config.resourcePending")} />
                    </div>
                    <Button type="button" size="icon" variant="ghost" aria-label={`${t("simulation.config.removeResource")} ${resource.name}`} onClick={() => {
                      const remaining = draft.resources.filter((r) => r.id !== resource.id);
                      const remainingIds = new Set(remaining.map((r) => r.id));
                      patch({
                        resources: remaining,
                        excludedResourceIds: resource.source ? [...(draft.excludedResourceIds ?? []), resource.id] : draft.excludedResourceIds,
                        // Il ruolo tolto sparisce anche dagli altri ruoli delle attività.
                        tasks: Object.fromEntries(Object.entries(draft.tasks).map(([id, task]) => [id, withValidOtherAssignments(
                          task.resourceId === resource.id ? { ...task, resourceId: "", assignmentSource: "manual" as const } : task, remainingIds)])),
                      });
                    }}><X aria-hidden className="size-4" /></Button>
                  </div>
                  <FieldLabel label={t("simulation.config.role")}>
                    <Input value={resource.name} onChange={(e) => updateResource(resource.id, { name: e.target.value, parametersConfirmed: false })} />
                  </FieldLabel>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <NumberField label={`${t("simulation.fields.costPerHour")} (€/h)`} value={resource.costPerHour} min={0} onChange={(value) => updateResource(resource.id, { costPerHour: value, parametersConfirmed: false })} />
                    <NumberField label={t("simulation.config.capacity")} value={resource.amount} min={1} max={1000} onChange={(value) => updateResource(resource.id, { amount: value, parametersConfirmed: false })} />
                  </div>
                  <label className="mt-3 grid gap-1">
                    <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.resourceCalendar")}</span>
                    <select
                      className="h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm"
                      aria-label={`${t("simulation.config.resourceCalendar")} · ${resource.name}`}
                      value={calendars.some((c) => c.id === resource.calendarId) ? resource.calendarId : ""}
                      onChange={(e) => updateResource(resource.id, { calendarId: e.target.value || undefined })}
                    >
                      <option value="">{t("simulation.config.standardCalendar")}</option>
                      {calendars.map((c) => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}
                    </select>
                  </label>
                  <p className="mt-3 text-xs text-muted-foreground">{t("simulation.config.assignedActivities", { count: assigned })}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {!confirmed && <Button type="button" size="sm" variant="outline" disabled={!resourceParametersValid(resource)} onClick={() => updateResource(resource.id, { parametersConfirmed: true })}>{t("simulation.config.confirmResource")}</Button>}
                    {resourceIssues.unassigned > 0 && <Button type="button" size="sm" variant="ghost" className="h-auto min-h-9 max-w-full whitespace-normal text-left" onClick={() => patch({ tasks: assignUnassignedTasks(draft, resource.id) })}>{t("simulation.config.assignUnassigned", { count: resourceIssues.unassigned })}</Button>}
                  </div>
                </li>
              );
            })}
          </ul>
          {!canRun && <div role="status" className="mt-3 grid gap-1 text-sm text-muted-foreground">
            <p>{t("simulation.config.resourceSetupRequired")}</p>
            {resourceIssues.pending > 0 && <p>{t("simulation.config.pendingResources", { count: resourceIssues.pending })}</p>}
            {resourceIssues.unassigned > 0 && <p>{t("simulation.config.unassignedActivities", { count: resourceIssues.unassigned })}</p>}
            {parameterIssues.durations > 0 && <p>{t("simulation.config.invalidDurations", { count: parameterIssues.durations })}</p>}
            {parameterIssues.calendars > 0 && <p>{t("simulation.config.invalidCalendars", { count: parameterIssues.calendars })}</p>}
            {ruleIssues.attributes > 0 && <p>{t("simulation.config.invalidAttributes", { count: ruleIssues.attributes })}</p>}
            {ruleIssues.gateways > 0 && <p>{t("simulation.config.invalidRules", { count: ruleIssues.gateways })}</p>}
          </div>}
        </DetailPanelSection>

        <DetailPanelSection title={t("simulation.config.calendars")}>
          <CalendarsSection
            standard={template?.standard_calendar}
            calendars={calendars}
            onChange={(next) => patch({
              calendars: next,
              // Una risorsa sul calendario rimosso torna su quello standard.
              resources: draft.resources.map((r) => r.calendarId && !next.some((c) => c.id === r.calendarId) ? { ...r, calendarId: undefined } : r),
            })}
          />
        </DetailPanelSection>

        <DetailPanelSection
          title={`${t("simulation.config.activities")}${
            template ? ` · ${template.tasks.length}` : ""
          }`}
        >
          {templateLoading ? (
            <EmptyState variant="inline" title={t("simulation.loading")} />
          ) : !template || template.tasks.length === 0 ? (
            <EmptyState variant="inline" title={t("simulation.config.noElements")} />
          ) : (
            <ul className="grid gap-2">
              {template.tasks.map((task) => {
                const cfg = draft.tasks[task.element_id];
                if (!cfg) return null;
                return (
                  <li
                    key={task.element_id}
                    data-sim-el={task.element_id}
                    className="sim-task-row rounded-md border border-border bg-muted/30 p-2.5"
                  >
                    <div className="sim-task-name mb-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                      <p
                        className="break-words text-sm font-medium text-foreground"
                        title={task.name}
                      >
                        {task.name}
                      </p>
                      {provenance?.activities[task.element_id] && (
                        <ProvenanceChip field={provenance.activities[task.element_id]} />
                      )}
                    </div>
                    <TaskDurationFields
                      elementId={task.element_id}
                      taskName={task.name}
                      task={cfg}
                      onChange={(next) => patch({ tasks: { ...draft.tasks, [task.element_id]: next } })}
                    />
                    <div className="sim-task-role mt-1.5">
                      <FieldLabel label={t("simulation.config.role")}>
                        <Select
                          value={cfg.resourceId}
                          onValueChange={(value) =>
                            patch({
                              tasks: {
                                ...draft.tasks,
                                // Se il nuovo principale era fra gli altri ruoli, lì non serve più.
                                [task.element_id]: withValidOtherAssignments(
                                  { ...cfg, resourceId: value, assignmentSource: "manual" },
                                  new Set(draft.resources.map((r) => r.id)),
                                ),
                              },
                            })
                          }
                        >
                          <SelectTrigger size="sm" className="w-full">
                            <SelectValue placeholder={t("simulation.config.selectResource")} />
                          </SelectTrigger>
                          <SelectContent>
                            {draft.resources.map((r) => (
                              <SelectItem key={r.id} value={r.id}>
                                {roleLabel(r)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </FieldLabel>
                    </div>
                    <OtherAssignments
                      elementId={task.element_id}
                      taskName={task.name}
                      task={cfg}
                      resources={draft.resources}
                      onChange={(next) => patch({ tasks: { ...draft.tasks, [task.element_id]: next } })}
                    />
                  </li>
                );
              })}
            </ul>
          )}
        </DetailPanelSection>

        <DetailPanelSection title={t("simulation.config.attributes")}>
          <CaseAttributesSection attributes={attributes} usedBy={attributeUse} onChange={(next) => patch({ caseAttributes: next })} />
        </DetailPanelSection>

        {template && template.gateways.length > 0 && (
          <DetailPanelSection title={t("simulation.config.gateways")}>
            <ul className="grid gap-2">
              {template.gateways.map((gateway) => {
                const cfg = draft.gateways[gateway.element_id] ?? {};
                const rules = gatewayRules[gateway.element_id];
                const setRules = (next: GatewayRulesDraft | undefined) => {
                  const others = Object.fromEntries(Object.entries(gatewayRules).filter(([id]) => id !== gateway.element_id));
                  patch({ gatewayRules: next ? { ...others, [gateway.element_id]: next } : others });
                };
                const sum = Object.values(cfg).reduce((a, b) => a + b, 0);
                const balanced = Math.abs(sum - 100) < 0.5;
                return (
                  <li
                    key={gateway.element_id}
                    data-sim-el={gateway.element_id}
                    className="rounded-md border border-border bg-muted/30 p-2.5"
                  >
                    <div className="mb-2 flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <span
                          className="block truncate text-xs font-medium text-foreground"
                          title={gateway.name}
                        >
                          {gateway.name}
                        </span>
                        {provenance?.gateways[gateway.element_id] && (
                          <ProvenanceChip
                            className="mt-1"
                            field={provenance.gateways[gateway.element_id]}
                          />
                        )}
                      </div>
                      {rules ? null : balanced ? (
                        <StatusIndicator tone="ok" label="100%" />
                      ) : (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[var(--amber-700)] hover:underline"
                          onClick={() => {
                            const flows = gateway.branches.map((b) => b.flow_id);
                            const total = flows.reduce((acc, f) => acc + (cfg[f] ?? 0), 0);
                            const next =
                              total > 0
                                ? Object.fromEntries(
                                    flows.map((f) => [
                                      f,
                                      Math.round(((cfg[f] ?? 0) / total) * 1000) / 10,
                                    ]),
                                  )
                                : Object.fromEntries(
                                    flows.map((f) => [f, Math.round(1000 / flows.length) / 10]),
                                  );
                            patch({
                              gateways: { ...draft.gateways, [gateway.element_id]: next },
                            });
                          }}
                        >
                          {Math.round(sum)}% · {t("simulation.config.normalize")}
                        </button>
                      )}
                    </div>
                    <div className="mb-2">
                      <GatewayModeToggle gateway={gateway} rules={rules} attributes={attributes} onChange={setRules} />
                    </div>
                    {rules ? <GatewayRulesEditor gateway={gateway} rules={rules} attributes={attributes} onChange={setRules} /> : <div className="grid gap-1">
                      {gateway.branches.map((branch) => (
                        <div
                          key={branch.flow_id}
                          className="grid grid-cols-[minmax(0,1fr)_72px] items-center gap-1.5"
                        >
                          <span
                            className="truncate text-[11px] text-muted-foreground"
                            title={branch.target_name || branch.flow_name}
                          >
                            {branch.target_name || branch.flow_name || branch.flow_id}
                          </span>
                          <div className="relative">
                            <Input
                              aria-label={branch.target_name || branch.flow_id}
                              className="h-8 pr-6"
                              type="number"
                              min={0}
                              max={100}
                              value={cfg[branch.flow_id] ?? 0}
                              onChange={(e) =>
                                patch({
                                  gateways: {
                                    ...draft.gateways,
                                    [gateway.element_id]: {
                                      ...cfg,
                                      [branch.flow_id]: num(e.target.value),
                                    },
                                  },
                                })
                              }
                            />
                            <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">
                              %
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>}
                  </li>
                );
              })}
            </ul>
          </DetailPanelSection>
        )}
      </div>

      {(!embedded || (error && !workspace)) && (
      <div className="border-t border-border p-3">
        {!embedded && (
          <Button type="button" className="w-full" disabled={isRunning || !canRun} onClick={onRun}>
            {isRunning ? runningLabel ?? t("simulation.running") : t("simulation.run")}
          </Button>
        )}
        {!embedded && runs && runs.length > 0 && onSelectRun && (
          <Select
            value={activeRunId ? String(activeRunId) : undefined}
            onValueChange={(value) => {
              const run = runs.find((r) => r.id === Number(value));
              if (run) onSelectRun(run);
            }}
          >
            <SelectTrigger className="mt-2 w-full">
              <SelectValue placeholder={t("simulation.output.title")} />
            </SelectTrigger>
            <SelectContent>
              {runs.map((run) => (
                <SelectItem key={run.id} value={String(run.id)}>
                  <span className="flex items-center gap-2">
                    <StatusIndicator
                      tone={RUN_TONE[run.status]}
                      label={run.scenario_name}
                    />
                    <span className="text-[11px] text-muted-foreground">
                      {formatDate(run.created_at)}
                    </span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {error && (
          <p
            role="alert"
            className={cn(
              "rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs font-medium leading-relaxed text-destructive",
              !embedded && "mt-2",
            )}
          >
            {error}
          </p>
        )}
      </div>
      )}
    </div>
  );
}

/** Le attività senza un ruolo valido passano a ``resourceId``, che sparisce dai loro altri ruoli. */
function assignUnassignedTasks(draft: ScenarioDraft, resourceId: string): ScenarioDraft["tasks"] {
  const ids = new Set(draft.resources.map((r) => r.id));
  return Object.fromEntries(Object.entries(draft.tasks).map(([id, task]) => [id, ids.has(task.resourceId)
    ? task
    : withValidOtherAssignments({ ...task, resourceId, assignmentSource: "manual" as const }, ids)]));
}

function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  onChange: (value: number) => void;
}) {
  return (
    <FieldLabel label={label}>
      <Input
        className="h-8"
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
      />
    </FieldLabel>
  );
}

/**
 * Renders a label with its associated input-confidence provenance chip.
 *
 * @param label - The text displayed alongside the provenance chip
 * @param field - The global input-confidence data represented by the chip
 */
function ChipRow({
  label,
  field,
}: {
  label: string;
  field: InputConfidence["globals"]["cases"];
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">
        {label}
      </span>
      <ProvenanceChip field={field} hideNote />
    </span>
  );
}

/**
 * Wraps a form control with a styled label.
 *
 * @param label - The text displayed above the control
 * @param children - The form control or content associated with the label
 */
function FieldLabel({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-xs font-medium text-muted-foreground">
        {label}
      </span>
      {children}
    </label>
  );
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
