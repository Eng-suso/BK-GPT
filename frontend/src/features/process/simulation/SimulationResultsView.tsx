import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown } from "lucide-react";

import { DetailPanelSection } from "@/components/panel";
import { Meter, StatTile, type MeterTone } from "@/components/data";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/ui/table";
import { cn } from "@/lib/utils";

import {
  formatCount,
  formatCurrency,
  formatDuration,
  formatPercent,
  type SimulationInsights,
  type TaskStat,
} from "./simulationResults";

function loadTone(pct: number): MeterTone {
  if (pct >= 95) return "danger";
  if (pct >= 85) return "warning";
  return "ok";
}

type SortKey = "avgWaitingSec" | "avgProcessingSec" | "avgCycleSec" | "avgCost" | "volume";

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
  const [sortKey, setSortKey] = React.useState<SortKey>("avgWaitingSec");

  const sortedTasks = React.useMemo(
    () => [...insights.tasks].sort((a, b) => b[sortKey] - a[sortKey]),
    [insights.tasks, sortKey],
  );
  const maxWait = Math.max(1, ...insights.tasks.map((task) => task.avgWaitingSec));
  const bottleneckName = insights.bottleneck?.name ?? null;
  const busiest = [...insights.resources].sort(
    (a, b) => b.utilizationPct - a.utilizationPct,
  )[0];

  return (
    <div className="flex flex-col">
      {insights.bottleneck && (
        <button
          type="button"
          onClick={() => onSelectElement?.(insights.bottleneck?.elementId ?? null)}
          disabled={!insights.bottleneck.elementId}
          className={cn(
            "mb-1 flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-left",
            insights.bottleneck.elementId && "cursor-pointer",
          )}
          style={{
            borderColor: "var(--sim-bottleneck-border)",
            background: "var(--sim-bottleneck-surface)",
          }}
        >
          <span
            aria-hidden
            className="mt-1 size-2 shrink-0 rounded-full"
            style={{ background: "var(--color-status-warning)" }}
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

      <DetailPanelSection title={t("simulation.results.summary")}>
        <div className="grid grid-cols-2 gap-2">
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
          {busiest && (
            <StatTile
              label={t("simulation.results.busiestResource")}
              value={`${busiest.utilizationPct}%`}
              hint={busiest.name}
              tone={
                busiest.utilizationPct >= 95
                  ? "danger"
                  : busiest.utilizationPct >= 85
                    ? "warning"
                    : "neutral"
              }
            />
          )}
        </div>
      </DetailPanelSection>

      {insights.resources.length > 0 && (
        <DetailPanelSection title={t("simulation.results.resourceLoad")}>
          <ul className="grid gap-2.5">
            {insights.resources.map((resource) => (
              <li
                key={resource.id}
                className="grid grid-cols-[minmax(0,1fr)_150px] items-center gap-3"
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
                <Meter
                  value={resource.utilizationPct}
                  tone={loadTone(resource.utilizationPct)}
                />
              </li>
            ))}
          </ul>
        </DetailPanelSection>
      )}

      {insights.tasks.length > 0 && (
        <DetailPanelSection
          title={`${t("simulation.results.table.activity")} · ${insights.tasks.length}`}
        >
          <div className="-mx-1 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-1">
                    {t("simulation.results.table.activity")}
                  </TableHead>
                  <SortableHead
                    label={t("simulation.results.table.waiting")}
                    active={sortKey === "avgWaitingSec"}
                    onClick={() => setSortKey("avgWaitingSec")}
                  />
                  <SortableHead
                    label={t("simulation.results.table.processing")}
                    active={sortKey === "avgProcessingSec"}
                    onClick={() => setSortKey("avgProcessingSec")}
                    align="right"
                  />
                  <SortableHead
                    label={t("simulation.results.table.cost")}
                    active={sortKey === "avgCost"}
                    onClick={() => setSortKey("avgCost")}
                    align="right"
                  />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedTasks.map((task, index) => (
                  <TaskRow
                    key={task.elementId ?? `${task.name}-${index}`}
                    task={task}
                    lang={lang}
                    maxWait={maxWait}
                    isBottleneck={task.name === bottleneckName}
                    isSelected={
                      !!task.elementId && task.elementId === selectedElementId
                    }
                    onSelect={() => onSelectElement?.(task.elementId ?? null)}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
        </DetailPanelSection>
      )}

    </div>
  );
}

function SortableHead({
  label,
  active,
  onClick,
  align = "right",
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  align?: "left" | "right";
}) {
  return (
    <TableHead className={cn(align === "right" && "text-right")}>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "inline-flex items-center gap-1 hover:text-foreground",
          active && "text-foreground",
        )}
      >
        {label}
        {active && <ArrowDown className="size-3" aria-hidden />}
      </button>
    </TableHead>
  );
}

function TaskRow({
  task,
  lang,
  maxWait,
  isBottleneck,
  isSelected,
  onSelect,
}: {
  task: TaskStat;
  lang: "it" | "en";
  maxWait: number;
  isBottleneck: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const barPct = Math.max(2, (task.avgWaitingSec / maxWait) * 100);
  return (
    <TableRow
      onClick={onSelect}
      className={cn(
        task.elementId && "cursor-pointer",
        isSelected && "outline outline-1 -outline-offset-1 outline-primary",
      )}
      style={isBottleneck ? { background: "var(--sim-bottleneck-surface)" } : undefined}
    >
      <TableCell className="max-w-[180px] pl-1">
        <span className="block truncate font-medium text-foreground">{task.name}</span>
        <span className="text-[11px] tabular-nums text-muted-foreground">
          {formatCount(task.volume, lang)}×
        </span>
      </TableCell>
      <TableCell className="min-w-[130px]">
        <span className="mb-1 block text-xs tabular-nums text-foreground">
          {formatDuration(task.avgWaitingSec, lang)}
        </span>
        <span className="block h-1.5 overflow-hidden rounded-full bg-muted">
          <span
            className="block h-full rounded-full"
            style={{
              width: `${barPct}%`,
              background: isBottleneck
                ? "var(--color-status-warning)"
                : "var(--primary)",
            }}
          />
        </span>
      </TableCell>
      <TableCell className="text-right tabular-nums text-muted-foreground">
        {formatDuration(task.avgProcessingSec, lang)}
      </TableCell>
      <TableCell className="text-right tabular-nums text-muted-foreground">
        {formatCurrency(task.avgCost, lang)}
      </TableCell>
    </TableRow>
  );
}

