import React from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/feedback";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/ui/table";
import { cn } from "@/lib/utils";

import {
  formatCount,
  formatCurrency,
  formatDuration,
  formatPercent,
  type SimulationInsights,
} from "./simulationResults";

type MeterTone = "ok" | "warning" | "danger";

const METER_FILL: Record<MeterTone, string> = {
  ok: "bg-primary",
  warning: "bg-[var(--color-status-warning)]",
  danger: "bg-[var(--color-status-danger)]",
};

function meterTone(pct: number): MeterTone {
  if (pct >= 95) return "danger";
  if (pct >= 85) return "warning";
  return "ok";
}

type SimulationResultsViewProps = {
  insights: SimulationInsights;
  selectedElementId?: string | null;
  onSelectElement?: (elementId: string | null) => void;
};

export function SimulationResults({
  insights,
  selectedElementId,
  onSelectElement,
}: SimulationResultsViewProps): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";

  if (!insights.hasData) {
    return <EmptyState variant="inline" title={t("simulation.results.noData")} />;
  }

  const tasksByWait = [...insights.tasks].sort(
    (a, b) => b.avgWaitingSec - a.avgWaitingSec,
  );
  const maxWait = tasksByWait[0]?.avgWaitingSec ?? 0;
  const bottleneckName = insights.bottleneck?.name ?? null;

  return (
    <div className="grid content-start gap-3">
      {insights.bottleneck && (
        <button
          type="button"
          onClick={() =>
            onSelectElement?.(insights.bottleneck?.elementId ?? null)
          }
          disabled={!insights.bottleneck.elementId}
          className={cn(
            "flex items-start gap-2.5 rounded-md border border-[color-mix(in_oklab,var(--color-status-warning)_35%,transparent)] bg-[color-mix(in_oklab,var(--color-status-warning)_12%,transparent)] px-3 py-2.5 text-left",
            insights.bottleneck.elementId && "cursor-pointer hover:bg-[color-mix(in_oklab,var(--color-status-warning)_18%,transparent)]",
          )}
        >
          <span
            aria-hidden
            className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[var(--color-status-warning)]"
          />
          <span className="text-xs leading-relaxed text-foreground">
            <strong className="font-semibold">
              {t("simulation.results.bottleneck")}: {insights.bottleneck.name}
            </strong>
            {" — "}
            {t("simulation.results.bottleneckDetail", {
              wait: formatDuration(insights.bottleneck.avgWaitingSec, lang),
              share: formatPercent(insights.bottleneck.waitingShare),
            })}
          </span>
        </button>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <StatTile
          label={t("simulation.results.cases")}
          value={formatCount(insights.casesCompleted, lang)}
        />
        <StatTile
          label={t("simulation.results.cycleTime")}
          value={formatDuration(insights.avgCycleSec, lang)}
          hint={t("simulation.results.waitingShare", {
            share: formatPercent(insights.waitingShare),
          })}
        />
        <StatTile
          label={t("simulation.results.waitingTime")}
          value={formatDuration(insights.avgWaitingSec, lang)}
        />
        <StatTile
          label={t("simulation.results.processingTime")}
          value={formatDuration(insights.avgProcessingSec, lang)}
        />
        <StatTile
          label={t("simulation.results.costPerCase")}
          value={formatCurrency(insights.avgCostPerCase, lang)}
          hint={t("simulation.results.totalCost", {
            total: formatCurrency(insights.totalCost, lang),
          })}
        />
      </div>

      {insights.resources.length > 0 && (
        <section className="rounded-md border border-border bg-muted/30 p-3">
          <h4 className="mb-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            {t("simulation.results.resourceLoad")}
          </h4>
          <ul className="grid gap-2.5">
            {insights.resources.map((resource) => {
              const tone = meterTone(resource.utilizationPct);
              return (
                <li
                  key={resource.id}
                  className="grid grid-cols-[minmax(0,1fr)_140px] items-center gap-3"
                >
                  <div className="min-w-0">
                    <span className="block truncate text-xs font-medium text-foreground">
                      {resource.name}
                    </span>
                    {resource.pool && (
                      <span className="block truncate text-[11px] text-muted-foreground">
                        {resource.pool}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-[6px] flex-1 overflow-hidden rounded-full bg-[var(--slate-200)]">
                      <span
                        className={cn("block h-full rounded-full", METER_FILL[tone])}
                        style={{ width: `${Math.min(100, resource.utilizationPct)}%` }}
                      />
                    </span>
                    <b className="min-w-[34px] text-right text-xs font-semibold tabular-nums text-foreground">
                      {resource.utilizationPct}%
                    </b>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {insights.tasks.length > 0 && (
        <section className="overflow-hidden rounded-md border border-border">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("simulation.results.table.activity")}</TableHead>
                  <TableHead className="text-right">{t("simulation.results.table.volume")}</TableHead>
                  <TableHead>{t("simulation.results.table.waiting")}</TableHead>
                  <TableHead className="text-right">{t("simulation.results.table.processing")}</TableHead>
                  <TableHead className="text-right">{t("simulation.results.table.cycle")}</TableHead>
                  <TableHead className="text-right">{t("simulation.results.table.cost")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasksByWait.map((task, index) => {
                  const isBottleneck = task.name === bottleneckName;
                  const isSelected =
                    !!task.elementId && task.elementId === selectedElementId;
                  const barPct = maxWait > 0 ? (task.avgWaitingSec / maxWait) * 100 : 0;
                  return (
                    <TableRow
                      key={task.elementId ?? `${task.name}-${index}`}
                      onClick={() => onSelectElement?.(task.elementId ?? null)}
                      className={cn(
                        task.elementId && "cursor-pointer",
                        isBottleneck &&
                          "bg-[color-mix(in_oklab,var(--color-status-warning)_10%,transparent)]",
                        isSelected && "outline outline-1 -outline-offset-1 outline-primary",
                      )}
                    >
                      <TableCell className="font-medium text-foreground">{task.name}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {formatCount(task.volume, lang)}
                      </TableCell>
                      <TableCell className="min-w-[150px]">
                        <span className="mb-1 block text-xs tabular-nums text-foreground">
                          {formatDuration(task.avgWaitingSec, lang)}
                        </span>
                        <span className="block h-1.5 overflow-hidden rounded-full bg-[var(--slate-200)]">
                          <span
                            className={cn(
                              "block h-full rounded-full",
                              isBottleneck
                                ? "bg-[var(--color-status-warning)]"
                                : "bg-primary",
                            )}
                            style={{ width: `${Math.max(2, barPct)}%` }}
                          />
                        </span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {formatDuration(task.avgProcessingSec, lang)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {formatDuration(task.avgCycleSec, lang)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {formatCurrency(task.avgCost, lang)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </section>
      )}
    </div>
  );
}

function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-muted/40 p-2.5">
      <span className="block text-[10px] font-semibold uppercase leading-tight tracking-wide text-muted-foreground">
        {label}
      </span>
      <strong className="mt-1 block text-[15px] font-semibold tabular-nums text-foreground">
        {value}
      </strong>
      {hint && (
        <span className="mt-0.5 block text-[11px] leading-tight text-muted-foreground">
          {hint}
        </span>
      )}
    </div>
  );
}
