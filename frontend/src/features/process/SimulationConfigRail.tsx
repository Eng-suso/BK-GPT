import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, Plus, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";
import { StatusIndicator, type StatusTone } from "@/components/status";
import { EmptyState } from "@/components/feedback";
import { cn } from "@/lib/utils";

import type { ScenarioTemplate, SimulationRun } from "./simulationTypes";
import {
  newResourceId,
  type ScenarioDraft,
  type TaskDraft,
} from "./simulationScenario";

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
  runs: SimulationRun[];
  activeRunId: number | null;
  onRun: () => void;
  onSelectRun: (run: SimulationRun) => void;
  focusElementId: string | null;
  collapsed: boolean;
  onToggleCollapsed: () => void;
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
  collapsed,
  onToggleCollapsed,
}: SimulationConfigRailProps): React.JSX.Element {
  const { t } = useTranslation("process");
  const scrollRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (collapsed || !focusElementId || !scrollRef.current) return;
    const node = scrollRef.current.querySelector<HTMLElement>(
      `[data-sim-el="${CSS.escape(focusElementId)}"]`,
    );
    node?.scrollIntoView({ block: "center", behavior: "smooth" });
    node?.classList.add("sim-el-flash");
    const timer = window.setTimeout(() => node?.classList.remove("sim-el-flash"), 1200);
    return () => window.clearTimeout(timer);
  }, [focusElementId, collapsed]);

  const patch = (partial: Partial<ScenarioDraft>) =>
    onDraftChange({ ...draft, ...partial });
  const num = (raw: string) => (raw === "" ? 0 : Number(raw));

  if (collapsed) {
    return (
      <div className="flex w-10 flex-col items-center gap-2 rounded-lg border border-border bg-card py-2 shadow-sm">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-8 w-8 p-0"
          onClick={onToggleCollapsed}
          title={t("simulation.config.expand")}
        >
          <ChevronRight className="size-4" />
        </Button>
        <span className="[writing-mode:vertical-rl] rotate-180 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t("simulation.scenario.title")}
        </span>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-card shadow-sm">
      <header className="flex min-h-[52px] items-center justify-between gap-2 border-b border-border px-3.5 py-2.5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            {t("simulation.scenario.eyebrow")}
          </p>
          <h3 className="mt-0.5 text-sm font-semibold text-foreground">
            {t("simulation.scenario.title")}
          </h3>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-8 w-8 p-0 text-muted-foreground"
          onClick={onToggleCollapsed}
          title={t("simulation.config.collapse")}
        >
          <ChevronLeft className="size-4" />
        </Button>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-auto p-3.5">
        {/* --- globals --- */}
        <Section title={t("simulation.config.globals")}>
          <Field label={t("simulation.fields.scenarioName")}>
            <Input
              className="h-8"
              value={draft.scenarioName}
              onChange={(e) => patch({ scenarioName: e.target.value })}
            />
          </Field>
          <div className="grid grid-cols-3 gap-2">
            <Field label={t("simulation.fields.cases")}>
              <Input
                className="h-8"
                type="number"
                min={1}
                max={100000}
                value={draft.totalCases}
                onChange={(e) => patch({ totalCases: num(e.target.value) })}
              />
            </Field>
            <Field label={t("simulation.fields.arrival")}>
              <Input
                className="h-8"
                type="number"
                min={1}
                value={draft.arrivalIntervalMinutes}
                onChange={(e) =>
                  patch({ arrivalIntervalMinutes: num(e.target.value) })
                }
              />
            </Field>
            <Field label={t("simulation.config.defaultDuration")}>
              <Input
                className="h-8"
                type="number"
                min={1}
                value={draft.defaultTaskMinutes}
                onChange={(e) => patch({ defaultTaskMinutes: num(e.target.value) })}
              />
            </Field>
          </div>
        </Section>

        {/* --- resources --- */}
        <Section
          title={t("simulation.config.resources")}
          action={
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-xs text-muted-foreground"
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
              <Plus className="size-3.5" /> {t("simulation.config.addResource")}
            </Button>
          }
        >
          <ul className="space-y-2">
            {draft.resources.map((resource, index) => (
              <li
                key={resource.id}
                className="grid grid-cols-[minmax(0,1fr)_64px_52px_auto] items-center gap-1.5 rounded-md border border-border bg-muted/30 p-1.5"
              >
                <Input
                  aria-label={t("simulation.fields.resourcePool")}
                  className="h-7"
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
                  className="h-7"
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
                  aria-label={t("simulation.fields.resources")}
                  className="h-7"
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
                  className="h-7 w-7 p-0 text-muted-foreground"
                  disabled={draft.resources.length <= 1}
                  onClick={() => {
                    const fallbackResourceId =
                      draft.resources.find((_, i) => i !== index)?.id ?? draft.resources[0].id;
                    patch({
                      resources: draft.resources.filter((_, i) => i !== index),
                      tasks: Object.fromEntries(
                        Object.entries(draft.tasks).map(([id, task]) => [
                          id,
                          task.resourceId === resource.id
                            ? { ...task, resourceId: fallbackResourceId }
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
          <p className="mt-1 grid grid-cols-[minmax(0,1fr)_64px_52px_auto] gap-1.5 px-1.5 text-[10px] font-medium text-muted-foreground">
            <span>{t("simulation.fields.resourcePool")}</span>
            <span>€/h</span>
            <span>n°</span>
            <span />
          </p>
        </Section>

        {/* --- per-task --- */}
        <Section title={t("simulation.config.activities")}>
          {templateLoading ? (
            <EmptyState variant="inline" title={t("simulation.loading")} />
          ) : !template || template.tasks.length === 0 ? (
            <EmptyState variant="inline" title={t("simulation.config.noElements")} />
          ) : (
            <ul className="space-y-1.5">
              {template.tasks.map((task) => {
                const cfg = draft.tasks[task.element_id];
                if (!cfg) return null;
                return (
                  <li
                    key={task.element_id}
                    data-sim-el={task.element_id}
                    className="rounded-md border border-border bg-muted/30 p-2"
                  >
                    <p className="mb-1.5 truncate text-xs font-medium text-foreground">
                      {task.name}
                    </p>
                    <div className="grid grid-cols-[64px_minmax(0,1fr)_minmax(0,1fr)] items-center gap-1.5">
                      <Input
                        aria-label={t("simulation.config.durationMin")}
                        className="h-7"
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
                        <SelectTrigger className="h-7">
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
                        <SelectTrigger className="h-7">
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
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Section>

        {/* --- per-gateway --- */}
        {template && template.gateways.length > 0 && (
          <Section title={t("simulation.config.gateways")}>
            <ul className="space-y-1.5">
              {template.gateways.map((gateway) => {
                const cfg = draft.gateways[gateway.element_id] ?? {};
                const sum = Object.values(cfg).reduce((a, b) => a + b, 0);
                return (
                  <li
                    key={gateway.element_id}
                    data-sim-el={gateway.element_id}
                    className="rounded-md border border-border bg-muted/30 p-2"
                  >
                    <p className="mb-1.5 flex items-center justify-between text-xs font-medium text-foreground">
                      <span className="truncate">{gateway.name}</span>
                      <span
                        className={cn(
                          "shrink-0 text-[11px] tabular-nums",
                          Math.abs(sum - 100) > 0.5
                            ? "text-[var(--color-status-warning)]"
                            : "text-muted-foreground",
                        )}
                      >
                        {Math.round(sum)}%
                      </span>
                    </p>
                    <div className="space-y-1">
                      {gateway.branches.map((branch) => (
                        <div
                          key={branch.flow_id}
                          className="grid grid-cols-[minmax(0,1fr)_56px] items-center gap-1.5"
                        >
                          <span className="truncate text-[11px] text-muted-foreground">
                            {branch.target_name || branch.flow_name || branch.flow_id}
                          </span>
                          <Input
                            aria-label={branch.target_name || branch.flow_id}
                            className="h-7"
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
                        </div>
                      ))}
                    </div>
                  </li>
                );
              })}
            </ul>
          </Section>
        )}
      </div>

      <div className="border-t border-border p-3">
        <Button
          type="button"
          className="w-full"
          disabled={isRunning}
          onClick={onRun}
        >
          {isRunning ? t("simulation.running") : t("simulation.run")}
        </Button>
        {runs.length > 0 && (
          <Select
            value={activeRunId ? String(activeRunId) : undefined}
            onValueChange={(value) => {
              const run = runs.find((r) => r.id === Number(value));
              if (run) onSelectRun(run);
            }}
          >
            <SelectTrigger className="mt-2 h-8">
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
            className="mt-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs font-medium leading-relaxed text-destructive"
          >
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h4>
        {action}
      </div>
      {children}
    </section>
  );
}

function Field({
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
