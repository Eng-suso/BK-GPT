import React from "react";
import { useTranslation } from "react-i18next";
import { PanelLeftClose, Plus, X } from "lucide-react";

import { DetailPanelSection } from "@/components/panel";
import { StatusIndicator, type StatusTone } from "@/components/status";
import { EmptyState } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
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
  type ScenarioDraft,
  type TaskDraft,
} from "./simulationScenario";
import type { InputConfidence } from "./simulationProvenance";
import { ProvenanceChip } from "./ProvenanceChip";

const RUN_TONE: Record<SimulationRun["status"], StatusTone> = {
  pending: "pending",
  completed: "ok",
  failed: "danger",
};

const DISTRIBUTIONS: TaskDraft["distribution"][] = ["norm", "expon", "fixed"];

type SimulationConfigRailProps = {
  template: ScenarioTemplate | null;
  templateLoading: boolean;
  draft: ScenarioDraft;
  onDraftChange: (next: ScenarioDraft) => void;
  isRunning: boolean;
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
  /** Per-field input-confidence badges (phase 5). */
  provenance?: InputConfidence | null;
};

export function SimulationConfigRail({
  template,
  templateLoading,
  draft,
  onDraftChange,
  isRunning,
  error,
  runs,
  activeRunId,
  onRun,
  onSelectRun,
  focusElementId,
  onCollapse,
  embedded = false,
  provenance,
}: SimulationConfigRailProps): React.JSX.Element {
  const { t } = useTranslation("process");
  const scrollRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!focusElementId || !scrollRef.current) return;
    const node = scrollRef.current.querySelector<HTMLElement>(
      `[data-sim-el="${CSS.escape(focusElementId)}"]`,
    );
    node?.scrollIntoView({ block: "center", behavior: "smooth" });
    node?.classList.add("sim-el-flash");
    const timer = window.setTimeout(() => node?.classList.remove("sim-el-flash"), 1200);
    return () => window.clearTimeout(timer);
  }, [focusElementId]);

  const patch = (partial: Partial<ScenarioDraft>) =>
    onDraftChange({ ...draft, ...partial });
  const num = (raw: string) => (raw === "" ? 0 : Number(raw));

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col rounded-lg border border-border bg-card",
        embedded ? "" : "overflow-hidden shadow-sm",
      )}
    >
      <header className="flex min-h-[52px] items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <p className="eyebrow">{t("simulation.scenario.eyebrow")}</p>
          <h3 className="mt-0.5 truncate text-sm font-semibold text-foreground">
            {t("simulation.scenario.title")}
          </h3>
        </div>
        {embedded ? (
          <Button
            type="button"
            size="sm"
            className="shrink-0"
            disabled={isRunning}
            onClick={onRun}
          >
            {isRunning ? t("simulation.running") : t("simulation.run")}
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
      </header>

      <div
        ref={scrollRef}
        className={cn("px-4", embedded ? "" : "min-h-0 flex-1 overflow-auto")}
      >
        <DetailPanelSection title={t("simulation.config.globals")}>
          <div className="grid gap-2.5">
            <label className="grid gap-1.5">
              <Label className="text-xs text-muted-foreground">
                {t("simulation.fields.scenarioName")}
              </Label>
              <Input
                value={draft.scenarioName}
                onChange={(e) => patch({ scenarioName: e.target.value })}
              />
            </label>
            <div className="grid grid-cols-3 gap-2">
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
                      costPerHour: 35,
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
          {provenance && (
            <div className="pb-2">
              <ProvenanceChip field={provenance.resources} />
            </div>
          )}
          <div className="grid grid-cols-[minmax(0,1fr)_76px_60px_32px] items-center gap-1.5 px-0.5 pb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            <span>{t("simulation.config.role")}</span>
            <span>€/h</span>
            <span>{t("simulation.config.qty")}</span>
            <span />
          </div>
          <ul className="grid gap-1.5">
            {draft.resources.map((resource, index) => (
              <li
                key={resource.id}
                className="grid grid-cols-[minmax(0,1fr)_76px_60px_32px] items-center gap-1.5"
              >
                <Input
                  aria-label={t("simulation.config.role")}
                  className="h-8"
                  value={resource.name}
                  onChange={(e) =>
                    patch({
                      resources: draft.resources.map((r, i) =>
                        i === index ? { ...r, name: e.target.value } : r,
                      ),
                    })
                  }
                />
                <Input
                  aria-label={t("simulation.fields.costPerHour")}
                  className="h-8"
                  type="number"
                  min={0}
                  value={resource.costPerHour}
                  onChange={(e) =>
                    patch({
                      resources: draft.resources.map((r, i) =>
                        i === index ? { ...r, costPerHour: num(e.target.value) } : r,
                      ),
                    })
                  }
                />
                <Input
                  aria-label={t("simulation.config.qty")}
                  className="h-8"
                  type="number"
                  min={1}
                  max={1000}
                  value={resource.amount}
                  onChange={(e) =>
                    patch({
                      resources: draft.resources.map((r, i) =>
                        i === index ? { ...r, amount: num(e.target.value) } : r,
                      ),
                    })
                  }
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="size-8 p-0 text-muted-foreground"
                  disabled={draft.resources.length <= 1}
                  onClick={() => {
                    const fallback =
                      draft.resources.find((_, i) => i !== index)?.id ??
                      draft.resources[0].id;
                    patch({
                      resources: draft.resources.filter((_, i) => i !== index),
                      tasks: Object.fromEntries(
                        Object.entries(draft.tasks).map(([id, task]) => [
                          id,
                          task.resourceId === resource.id
                            ? { ...task, resourceId: fallback }
                            : task,
                        ]),
                      ),
                    });
                  }}
                  title={t("simulation.config.removeResource")}
                >
                  <X className="size-3.5" />
                </Button>
              </li>
            ))}
          </ul>
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
                    className="rounded-md border border-border bg-muted/30 p-2.5"
                  >
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                      <p
                        className="truncate text-xs font-medium text-foreground"
                        title={task.name}
                      >
                        {task.name}
                      </p>
                      {provenance?.activities[task.element_id] && (
                        <ProvenanceChip field={provenance.activities[task.element_id]} />
                      )}
                    </div>
                    <div className="grid grid-cols-[68px_minmax(0,1fr)] gap-1.5">
                      <FieldLabel label={t("simulation.config.durationMin")}>
                        <Input
                          className="h-8"
                          type="number"
                          min={1}
                          value={cfg.meanMinutes}
                          onChange={(e) =>
                            patch({
                              tasks: {
                                ...draft.tasks,
                                [task.element_id]: {
                                  ...cfg,
                                  meanMinutes: num(e.target.value),
                                },
                              },
                            })
                          }
                        />
                      </FieldLabel>
                      <FieldLabel label={t("simulation.config.distribution")}>
                        <Select
                          value={cfg.distribution}
                          onValueChange={(value) =>
                            patch({
                              tasks: {
                                ...draft.tasks,
                                [task.element_id]: {
                                  ...cfg,
                                  distribution: value as TaskDraft["distribution"],
                                },
                              },
                            })
                          }
                        >
                          <SelectTrigger size="sm" className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {DISTRIBUTIONS.map((d) => (
                              <SelectItem key={d} value={d}>
                                {t(`simulation.config.dist.${d}`)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </FieldLabel>
                    </div>
                    <div className="mt-1.5">
                      <FieldLabel label={t("simulation.config.role")}>
                        <Select
                          value={cfg.resourceId}
                          onValueChange={(value) =>
                            patch({
                              tasks: {
                                ...draft.tasks,
                                [task.element_id]: { ...cfg, resourceId: value },
                              },
                            })
                          }
                        >
                          <SelectTrigger size="sm" className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {draft.resources.map((r) => (
                              <SelectItem key={r.id} value={r.id}>
                                {r.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </FieldLabel>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </DetailPanelSection>

        {template && template.gateways.length > 0 && (
          <DetailPanelSection title={t("simulation.config.gateways")}>
            <ul className="grid gap-2">
              {template.gateways.map((gateway) => {
                const cfg = draft.gateways[gateway.element_id] ?? {};
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
                      {balanced ? (
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
                    <div className="grid gap-1">
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
                    </div>
                  </li>
                );
              })}
            </ul>
          </DetailPanelSection>
        )}
      </div>

      {(!embedded || error) && (
      <div className="border-t border-border p-3">
        {!embedded && (
          <Button type="button" className="w-full" disabled={isRunning} onClick={onRun}>
            {isRunning ? t("simulation.running") : t("simulation.run")}
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

function ChipRow({
  label,
  field,
}: {
  label: string;
  field: InputConfidence["globals"]["cases"];
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <ProvenanceChip field={field} hideNote />
    </span>
  );
}

function FieldLabel({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
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
