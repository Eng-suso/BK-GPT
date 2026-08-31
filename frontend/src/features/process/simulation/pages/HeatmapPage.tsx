import React from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Flame, X } from "lucide-react";

import { EmptyState } from "@/components/feedback";
import { StatusIndicator } from "@/components/status";
import { Meter } from "@/components/data";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";
import { cn } from "@/lib/utils";

import { SimulationCanvas, type NodeDecoration } from "../canvas/SimulationCanvas";
import { resolveActiveRun, useSimulationSection } from "../useSimulationSection";
import type { SimulationSummary } from "../simulationTypes";
import {
  formatCurrency,
  formatDuration,
  HEAT_METRICS,
  HEAT_METRIC_ORDER,
  metricBucket,
  readActivityStats,
  type HeatMetric,
} from "../simulationResults";

const HEAT_SWATCH = [
  "var(--sim-heat-0)",
  "var(--sim-heat-1)",
  "var(--sim-heat-2)",
  "var(--sim-heat-3)",
  "var(--sim-heat-4)",
];

const FACTOR_ORDER = [
  "waitingContribution",
  "cycleContribution",
  "utilization",
  "queueGrowth",
  "casesAffected",
  "persistence",
] as const;

export function HeatmapPage(): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const { runs, bpmnXml } = useSimulationSection();
  const { runId } = useParams();
  const activeRun = resolveActiveRun(runs, runId);

  const [metric, setMetric] = React.useState<HeatMetric>("wait");
  const [selectedEl, setSelectedEl] = React.useState<string | null>(null);

  const summary = (activeRun?.summary as SimulationSummary | null) ?? null;
  const stats = React.useMemo(() => readActivityStats(summary), [summary]);

  const bottleneckEl =
    (summary?.bottleneck as { el?: string } | null | undefined)?.el ?? null;
  const bottleneckFactors =
    (summary?.bottleneck as { factors?: Record<string, number> } | null | undefined)
      ?.factors ?? null;

  const cfg = HEAT_METRICS[metric];
  const ranked = React.useMemo(
    () =>
      [...stats]
        .filter((s) => s.el)
        .sort((a, b) => cfg.value(b) - cfg.value(a)),
    [stats, cfg],
  );
  const maxValue = Math.max(1, ...ranked.map((s) => cfg.value(s)));

  const decorations = React.useMemo<NodeDecoration[]>(
    () =>
      ranked.map((s, i) => {
        const value = cfg.value(s);
        const isBottleneck = s.el === bottleneckEl;
        return {
          elementId: s.el as string,
          markers: [
            `sim-heat-${metricBucket(value, maxValue)}`,
            ...(isBottleneck ? ["sim-node-bottleneck"] : []),
          ],
          badge:
            (i < 4 && value > 0) || isBottleneck
              ? cfg.format(value, lang)
              : undefined,
          badgeTone: isBottleneck ? "warning" : "neutral",
        };
      }),
    [ranked, cfg, maxValue, bottleneckEl, lang],
  );

  const selected =
    stats.find((s) => s.el === selectedEl) ??
    stats.find((s) => s.el === bottleneckEl) ??
    ranked[0] ??
    null;

  if (!activeRun) {
    return (
      <Gate
        icon={Flame}
        title={t("simulation.heatmap.noRun")}
        description={t("simulation.heatmap.noRunHint")}
      />
    );
  }
  if (activeRun.status === "pending") {
    return <Gate icon={Flame} title={t("simulation.running")} />;
  }
  if (activeRun.status === "failed") {
    return (
      <Gate icon={X} title={t("simulation.status.failed")} description={activeRun.error ?? undefined} />
    );
  }
  if (!summary || stats.length === 0) {
    return <Gate icon={Flame} title={t("simulation.heatmap.noData")} />;
  }

  const metricName = t(`simulation.heatmap.metric.${metric}`);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 lg:flex-row">
      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border bg-card">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            {t("simulation.heatmap.metricLabel")}
            <Select value={metric} onValueChange={(v) => setMetric(v as HeatMetric)}>
              <SelectTrigger size="sm" className="w-[190px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {HEAT_METRIC_ORDER.map((m) => (
                  <SelectItem key={m} value={m}>
                    {t(`simulation.heatmap.metric.${m}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span>{t("simulation.heatmap.legendLow")}</span>
            {HEAT_SWATCH.map((c, i) => (
              <span
                key={i}
                aria-hidden
                className="size-3 rounded-[3px] border border-border/60"
                style={{ background: c }}
              />
            ))}
            <span>{t("simulation.heatmap.legendHigh")}</span>
          </div>
        </header>
        <SimulationCanvas
          className="min-h-0 flex-1"
          bpmnXml={bpmnXml}
          decorations={decorations}
          selectedElementId={selectedEl}
          onSelectElement={setSelectedEl}
        />
      </section>

      <aside className="flex min-h-0 w-full shrink-0 flex-col overflow-hidden rounded-lg border border-border bg-card lg:w-[336px]">
        {selected && (
          <div className="border-b border-border px-4 py-3">
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-[15px] font-semibold leading-tight text-foreground">
                {selected.name}
              </h3>
              {selected.el === bottleneckEl && (
                <StatusIndicator
                  tone="warning"
                  label={t("simulation.heatmap.bottleneckTag")}
                  className="shrink-0"
                />
              )}
            </div>
            {selected.el === bottleneckEl && (
              <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                {t("simulation.heatmap.diagnostic")}
              </p>
            )}
            <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2">
              <Kv label={t("simulation.heatmap.fields.wait")} value={formatDuration(selected.wait.avg, lang)} />
              <Kv label={t("simulation.heatmap.fields.waitP95")} value={formatDuration(selected.wait.p95, lang)} />
              <Kv label={t("simulation.heatmap.fields.work")} value={formatDuration(selected.processing.avg, lang)} />
              <Kv label={t("simulation.heatmap.fields.utilization")} value={`${Math.round(selected.utilizationPct)}%`} />
              <Kv label={t("simulation.heatmap.fields.queue")} value={selected.queue.avg.toFixed(1)} />
              <Kv label={t("simulation.heatmap.fields.queueMax")} value={String(selected.queue.max)} />
              <Kv label={t("simulation.heatmap.fields.cost")} value={formatCurrency(selected.avgCost, lang)} />
              <Kv label={t("simulation.heatmap.fields.volume")} value={String(selected.count)} />
              <Kv
                label={t("simulation.heatmap.fields.cycleShare")}
                value={`${Math.round(selected.cycleContributionPct * 100)}%`}
              />
              <Kv
                label={t("simulation.heatmap.fields.casesAffected")}
                value={`${Math.round(selected.casesAffectedPct * 100)}%`}
              />
            </dl>

            {selected.el === bottleneckEl && bottleneckFactors && (
              <div className="mt-3 border-t border-border/70 pt-3">
                <p className="eyebrow mb-2">{t("simulation.heatmap.factors")}</p>
                <ul className="grid gap-1.5">
                  {FACTOR_ORDER.filter((k) => k in bottleneckFactors).map((k) => (
                    <li key={k} className="grid gap-1">
                      <span className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                        {t(`simulation.heatmap.factor.${k}`)}
                        <span className="tabular-nums">
                          {Math.round((bottleneckFactors[k] ?? 0) * 100)}%
                        </span>
                      </span>
                      <Meter
                        value={Math.round((bottleneckFactors[k] ?? 0) * 100)}
                        tone="warning"
                        showValue={false}
                        height={4}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-auto px-2 py-2">
          <p className="eyebrow px-2 pb-1.5">
            {t("simulation.heatmap.ranking", { metric: metricName })}
          </p>
          <ul className="grid gap-0.5">
            {ranked.map((s) => (
              <li key={s.el}>
                <button
                  type="button"
                  onClick={() => setSelectedEl(s.el)}
                  className={cn(
                    "grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                    "hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--sim-info)]",
                    selected?.el === s.el && "bg-muted",
                  )}
                >
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5">
                      <span
                        aria-hidden
                        className="size-2 shrink-0 rounded-[2px]"
                        style={{ background: HEAT_SWATCH[metricBucket(cfg.value(s), maxValue)] }}
                      />
                      <span className="truncate text-xs text-foreground" title={s.name}>
                        {s.name}
                      </span>
                      {s.el === bottleneckEl && (
                        <Flame aria-hidden className="size-3 shrink-0 text-[var(--amber-700)]" />
                      )}
                    </span>
                    <span className="mt-1 block pr-2">
                      <Meter
                        value={(cfg.value(s) / maxValue) * 100}
                        tone={s.el === bottleneckEl ? "warning" : "ok"}
                        showValue={false}
                        height={3}
                      />
                    </span>
                  </span>
                  <span className="shrink-0 text-xs font-medium tabular-nums text-foreground">
                    {cfg.format(cfg.value(s), lang)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}

function Gate({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof Flame;
  title: string;
  description?: string;
}) {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <EmptyState icon={Icon} title={title} description={description} />
    </div>
  );
}

function Kv({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="m-0 text-xs font-medium tabular-nums text-foreground">{value}</dd>
    </div>
  );
}
