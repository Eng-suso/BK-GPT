import React from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp, ArrowRight, Minus } from "lucide-react";

import { EmptyState } from "@/components/feedback";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/ui/table";
import { formatMetric } from "../dashboard/dashboardFormatting";
import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";

import { SimulationCanvas, type NodeDecoration } from "../canvas/SimulationCanvas";
import { formatRunOption, useSimulationSection } from "../useSimulationSection";
import type { SimulationRun, SimulationSummary } from "../simulationTypes";
import {
  elementWaitDeltas,
  kpiDeltas,
  type DeltaDirection,
  type KpiDelta,
} from "../compareDeltas";
import {
  formatCurrency,
  formatDuration,
  formatPercent,
  heatBucket,
} from "../simulationResults";

import { ScenarioMatrix } from "./ScenarioMatrix";

export type CompareMode = "a" | "b" | "delta";

export function ComparePage({ embedded = false, compact = false, onDecorations }: { embedded?: boolean; compact?: boolean; onDecorations?: (items: NodeDecoration[]) => void } = {}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const { runs, activeRunId } = useSimulationSection();
  const [params, setParams] = useSearchParams();

  const candidates = React.useMemo(
    () => runs.filter((r) => r.status === "completed" && r.summary),
    [runs],
  );

  const aId = params.get("a");
  const bId = params.get("b");
  const runB = candidates.find(r => String(r.id) === bId) ?? candidates.find(r => r.id === activeRunId) ?? candidates[0] ?? null;
  const runA = candidates.find(r => String(r.id) === aId && r.id !== runB?.id) ?? candidates.find(r => r.id !== runB?.id) ?? null;
  const mode: CompareMode = params.get("compareMode") === "a" ? "a" : params.get("compareMode") === "b" ? "b" : "delta";
  const setMode = (value: CompareMode) => { const next = new URLSearchParams(params); next.set("compareMode", value); setParams(next, { replace: true }); };

  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const sameModel = runA?.bpmn_model_id === runB?.bpmn_model_id;
  const decorations = React.useMemo(() => runA && runB && sameModel ? comparisonDecorations(runA, runB, mode, lang) : [], [runA, runB, mode, lang, sameModel]);
  React.useEffect(() => { onDecorations?.(decorations); }, [decorations, onDecorations]);
  if (candidates.length < 2) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          title={t("simulation.compare.needTwo")}
          description={t("simulation.compare.needTwoHint")}
        />
      </div>
    );
  }
  if (!runA || !runB) return <div />;

  const setRun = (side: "a" | "b", id: string) => {
    const next = new URLSearchParams(params);
    next.set(side, id);
    const other = side === "a" ? runB : runA;
    next.set(side === "a" ? "b" : "a", String(String(other.id) === id ? (side === "a" ? runA.id : runB.id) : other.id));
    setParams(next, { replace: true });
  };

  return (
    <div className={compact ? "sim-comparison-bar ui-surface ui-surface-panel" : "flex h-full min-h-0 flex-col gap-3"}>
      {compact && <header className="sim-compare-context"><div><h3>{t("simulation.decision.title")}</h3><p>{t("simulation.decision.pairHint")}</p></div><span className="sim-eyebrow">{t("simulation.scene.finalScope")}</span></header>}
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <RunPicker
          label={t("simulation.compare.runA")}
          runs={candidates}
          value={String(runA.id)}
          onChange={(v) => setRun("a", v)}
        />
        <ArrowRight aria-hidden className="size-4 text-muted-foreground" />
        <RunPicker
          label={t("simulation.compare.runB")}
          runs={candidates}
          value={String(runB.id)}
          onChange={(v) => setRun("b", v)}
        />
        <div
          className="ml-auto flex items-center gap-1 ui-surface ui-surface-inset p-1"
          role="group"
          aria-label={t("simulation.compare.modeLabel")}
        >
          {(["a", "b", "delta"] as CompareMode[]).map((m) => (
            <Button
              key={m}
              size="sm"
              variant={mode === m ? "secondary" : "ghost"}
              aria-pressed={mode === m}
              onClick={() => setMode(m)}
            >
              {m === "a" ? "A" : m === "b" ? "B" : "Δ"}
            </Button>
          ))}
        </div>
      </div>

      <Verdict runA={runA} runB={runB} />
      {!sameModel && <p className="sim-comparison-compatibility" role="status">{t("simulation.decision.modelMismatch")}</p>}
      {compact && <ScenarioMatrix baseline={runA} alternative={runB} candidates={candidates} />}

      {compact ? <details className="sim-comparison-details"><summary>{t("simulation.scene.summaryDetails")}</summary><KpiDeltaTable runA={runA} runB={runB} /></details> : <div className={embedded ? "min-h-0 flex-1" : "grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(340px,0.82fr)_minmax(0,1.18fr)]"}>
        <section className="flex min-h-0 flex-col overflow-hidden ui-surface ui-surface-panel">
          <header className="border-b border-border px-4 py-2.5">
            <p className="eyebrow">{t("simulation.compare.kpiHeader")}</p>
          </header>
          <div className="min-h-0 flex-1 overflow-auto">
            <KpiDeltaTable runA={runA} runB={runB} />
          </div>
        </section>

        {!embedded && <section className="flex min-h-0 flex-col overflow-hidden ui-surface ui-surface-panel">
          <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
            <p className="eyebrow">{t("simulation.diagram.title")}</p>
            {mode === "delta" ? (
              <span className="flex items-center gap-3 text-[11px] text-muted-foreground">
                <Legend color="var(--color-status-success)" label={t("simulation.compare.better")} />
                <Legend color="var(--color-status-danger)" label={t("simulation.compare.worse")} />
              </span>
            ) : (
              <span className="text-[11px] text-muted-foreground">
                {t("simulation.diagram.legendWait")}
              </span>
            )}
          </header>
          <CompareCanvas runA={runA} runB={runB} mode={mode} />
        </section>}
      </div>}
    </div>
  );
}

function RunPicker({
  label,
  runs,
  value,
  onChange,
}: {
  label: string;
  runs: SimulationRun[];
  value: string;
  onChange: (id: string) => void;
}) {
  const { i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      {label}
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger size="sm" className="w-[220px]" aria-label={label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {runs.map((run) => (
            <SelectItem key={run.id} value={String(run.id)}>
              {formatRunOption(run, lang)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}

function Verdict({ runA, runB }: { runA: SimulationRun; runB: SimulationRun }) {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const rows = kpiDeltas(
    runA.summary as SimulationSummary,
    runB.summary as SimulationSummary,
  );
  const cycle = rows.find((r) => r.key === "cycleAvg");
  const cost = rows.find((r) => r.key === "costPerCase");
  if (!cycle) return null;

  const pct = (r: KpiDelta) =>
    r.deltaPct != null
      ? `${r.deltaPct > 0 ? "+" : r.deltaPct < 0 ? "−" : ""}${formatPercent(Math.abs(r.deltaPct))}`
      : "—";

  return (
    <p className="shrink-0 ui-surface ui-surface-panel px-4 py-2.5 text-[13px] leading-relaxed text-foreground">
      <strong className="font-semibold">{runB.scenario_name}</strong>
      {": "}
      {t("simulation.compare.verdict", {
        cyclePct: pct(cycle),
        cycleFrom: formatDuration(cycle.a, lang),
        cycleTo: formatDuration(cycle.b, lang),
        costPct: cost ? pct(cost) : "—",
      })}
    </p>
  );
}

function KpiDeltaTable({ runA, runB }: { runA: SimulationRun; runB: SimulationRun }) {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const rows = React.useMemo(
    () =>
      kpiDeltas(runA.summary as SimulationSummary, runB.summary as SimulationSummary),
    [runA, runB],
  );

  const fmt = (value: number, kind: string) => {
    if (!Number.isFinite(value)) return "—";
    if (kind === "duration") return formatDuration(value, lang);
    if (kind === "currency") return formatCurrency(value, lang);
    if (kind === "percent") return `${Math.round(value)}%`;
    if (kind === "rate")
      return formatMetric(value, "rate", lang);
    return String(Math.round(value));
  };

  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>{t("simulation.compare.metric")}</TableHead>
          <TableHead className="text-right">A</TableHead>
          <TableHead className="text-right">B</TableHead>
          <TableHead className="text-right">Δ</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.key} className="hover:bg-transparent">
            <TableCell className="text-xs text-foreground">
              {t(`simulation.compare.kpi.${row.labelKey}`)}
            </TableCell>
            <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
              {fmt(row.a, row.format)}
            </TableCell>
            <TableCell className="text-right text-xs tabular-nums text-foreground">
              {fmt(row.b, row.format)}
            </TableCell>
            <TableCell className="py-2 text-right text-xs tabular-nums">
              <DeltaCell
                direction={row.direction}
                rising={row.delta > 0}
                value={
                  (row.delta > 0 ? "+" : row.delta < 0 ? "−" : "") +
                  fmt(Math.abs(row.delta), row.format)
                }
                pct={
                  row.deltaPct != null
                    ? `${row.deltaPct > 0 ? "+" : row.deltaPct < 0 ? "−" : ""}${formatPercent(
                        Math.abs(row.deltaPct),
                      )}`
                    : null
                }
              />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function DeltaCell({
  direction,
  rising,
  value,
  pct,
}: {
  direction: DeltaDirection;
  rising: boolean;
  value: string;
  pct: string | null;
}) {
  const Icon = direction === "same" ? Minus : rising ? ArrowUp : ArrowDown;
  return (
    <span
      className={cn(
        "inline-flex flex-col items-end font-medium leading-tight",
        direction === "better" && "text-[var(--color-status-success)]",
        direction === "worse" && "text-[var(--color-status-danger)]",
        direction === "same" && "text-muted-foreground",
      )}
    >
      <span className="inline-flex items-center gap-1">
        <Icon aria-hidden className="size-3" />
        {value}
      </span>
      {pct && direction !== "same" && (
        <span className="text-[10px] opacity-80">{pct}</span>
      )}
    </span>
  );
}

function CompareCanvas({
  runA,
  runB,
  mode,
}: {
  runA: SimulationRun;
  runB: SimulationRun;
  mode: CompareMode;
}) {
  const { i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const { bpmnXml } = useSimulationSection();

  const decorations = React.useMemo(() => comparisonDecorations(runA, runB, mode, lang), [mode, runA, runB, lang]);

  return (
    <SimulationCanvas
      className="min-h-0 flex-1"
      bpmnXml={bpmnXml}
      decorations={decorations}
    />
  );
}

function comparisonDecorations(runA: SimulationRun, runB: SimulationRun, mode: CompareMode, lang: "it" | "en"): NodeDecoration[] {
    if (runA.bpmn_model_id !== runB.bpmn_model_id) return [];
    if (mode === "delta") {
      const deltas = elementWaitDeltas(
        runA.summary as SimulationSummary,
        runB.summary as SimulationSummary,
      );
      const worst = Math.max(1, ...deltas.filter(d => Number.isFinite(d.deltaWait)).map((d) => Math.abs(d.deltaWait)));
      return deltas
        .filter((d) => d.el)
        .map((d) => ({
          elementId: d.el,
          markers: [
            d.direction === "better"
              ? "sim-delta-better"
              : d.direction === "worse"
                ? "sim-delta-worse"
                : "sim-delta-neutral",
          ],
          badge: !Number.isFinite(d.deltaWait) ? "—" :
            Math.abs(d.deltaWait) / worst > 0.15
              ? `${d.deltaWait > 0 ? "+" : "−"}${formatDuration(Math.abs(d.deltaWait), lang)}`
              : undefined,
          badgeTone: d.direction === "worse" ? "danger" : "neutral",
        }));
    }

    const run = mode === "a" ? runA : runB;
    const acts = ((run.summary?.byActivity as Array<Record<string, unknown>>) ?? [])
      .filter((r) => r.el)
      .map((r) => ({
        el: String(r.el),
        wait: Number((r.wait as { avg?: number })?.avg ?? Number.NaN),
      })).filter(a => Number.isFinite(a.wait));
    const maxWait = Math.max(1, ...acts.map((a) => a.wait));
    return acts.map((a, i) => ({
      elementId: a.el,
      markers: [`sim-heat-${heatBucket(a.wait, maxWait)}`],
      badge: i < 4 && a.wait > 0 ? formatDuration(a.wait, lang) : undefined,
    }));
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="size-2 rounded-full" style={{ background: color }} aria-hidden />
      {label}
    </span>
  );
}
