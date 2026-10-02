import React from "react";
import { useTranslation } from "react-i18next";
import { X, ChartNoAxesCombined } from "lucide-react";

import { Button } from "@/ui/button";
import { Meter } from "@/components/data";
import { cn } from "@/lib/utils";

import { SimulationCanvas, type NodeDecoration } from "../canvas/SimulationCanvas";
import { CanvasAnalytics } from "../canvas/CanvasAnalytics";
import { TokenLayer } from "../canvas/TokenLayer";
import { TransportBar } from "../replay/TransportBar";
import { ReplayGate } from "../replay/ReplayGate";
import { ReplayInsightRail } from "../replay/ReplayInsightRail";
import { CaseTimeline } from "../replay/CaseTimeline";
import { useReplayFrame, useReplayStatus } from "../replay/useReplay";
import type { ReplayEngine } from "../replay/replayEngine";
import type { BpmnViewer } from "../canvas/bpmnViewer";
import type { SimulationRun } from "../simulationTypes";
import { useSimulationSection } from "../useSimulationSection";
import { formatDuration } from "../simulationResults";

const PRESSURE_MARKER: Record<string, string> = {
  building: "sim-pressure-building",
  high: "sim-pressure-high",
  saturated: "sim-pressure-saturated",
};

export function ReplayPage(): React.JSX.Element {
  return (
    <ReplayGate>
      {({ engine, run, bpmnXml }) => (
        <ReplayStage engine={engine} run={run} bpmnXml={bpmnXml} />
      )}
    </ReplayGate>
  );
}

type ReplayStageProps = {
  engine: ReplayEngine;
  bpmnXml: string;
  run: SimulationRun;
};

/**
 * Renders the replay stage with simulation controls, BPMN visualization, node details, and contextual insights.
 *
 * @param engine - Replay engine providing simulation state and controls
 * @param bpmnXml - BPMN diagram XML used to render the simulation canvas
 * @param run - Simulation run data used for summaries and replay insights
 * @returns The replay stage element
 */
function ReplayStage({ engine, bpmnXml, run }: ReplayStageProps): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const { projectId, processId } = useSimulationSection();
  const frame = useReplayFrame(engine);
  const status = useReplayStatus(engine);
  const [viewer, setViewer] = React.useState<BpmnViewer | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const [chartsVisible, setChartsVisible] = React.useState(true);

  const systemMode = status?.granularity === "system";

  const decorations = React.useMemo<NodeDecoration[]>(() => {
    if (!frame) return [];
    const out: NodeDecoration[] = [];
    for (const [el, state] of Object.entries(frame.elements)) {
      const markers: string[] = [];
      if (state.pressure !== "none") markers.push(PRESSURE_MARKER[state.pressure]);
      // system mode: chip every active node; otherwise only queued / pressured ones
      const chip = systemMode
        ? state.active > 0 || state.queued > 0
        : state.queued > 0;
      if (markers.length === 0 && !chip) continue;
      out.push({
        elementId: el,
        markers,
        badge: systemMode
          ? chip
            ? t("simulation.replay.systemChip", {
                active: state.active,
                queued: state.queued,
              })
            : undefined
          : state.queued > 0
            ? t("simulation.replay.inQueue", { n: state.queued })
            : undefined,
        badgeTone:
          state.pressure === "saturated" || state.pressure === "high"
            ? "warning"
            : "neutral",
      });
    }
    return out;
  }, [frame, t, systemMode]);

  const activity =
    selectedId && Array.isArray(run.summary?.byActivity)
      ? (run.summary.byActivity as Array<Record<string, unknown>>).find(
          (a) => a.el === selectedId,
        )
      : undefined;
  const nodeState = selectedId && frame ? frame.elements[selectedId] : undefined;
  const pool = selectedId ? engine.poolForElement(selectedId) : null;
  const poolBusy = pool && frame ? frame.resources[pool]?.busy ?? 0 : 0;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto">
      <div className="shrink-0 overflow-hidden ui-surface ui-surface-panel">
        <TransportBar engine={engine} />
      </div>

      <div className="flex min-h-[500px] shrink-0 flex-1 gap-3">
        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden ui-surface ui-surface-panel">
          <SimulationCanvas
            className="min-h-0 flex-1"
            bpmnXml={bpmnXml}
            decorations={decorations}
            selectedElementId={selectedId}
            onSelectElement={setSelectedId}
            onViewerReady={setViewer}
            toolbarStart={<div className="flex flex-wrap items-center gap-2"><label className="sim-filter"><span className="sr-only">{t("simulation.studio.activityFilter")}</span><select aria-label={t("simulation.studio.activityFilter")} value={selectedId ?? ""} onChange={(event) => setSelectedId(event.target.value || null)}><option value="">{t("simulation.studio.chooseActivity")}</option>{Object.entries(engine.payload.elements).map(([id, element]) => <option key={id} value={id}>{element.name}</option>)}</select></label><Button size="sm" variant="ghost" aria-pressed={chartsVisible} onClick={() => setChartsVisible((current) => !current)}><ChartNoAxesCombined aria-hidden className="size-4" />{t("simulation.studio.charts")}</Button></div>}
          />
          <TokenLayer viewer={viewer} engine={engine} />
          {frame && <CanvasAnalytics key={`${projectId}:${processId}`} viewer={viewer} engine={engine} frame={frame} selectedId={selectedId} visible={chartsVisible} onVisibilityChange={setChartsVisible} />}

          {selectedId && (
            <aside
              className="absolute right-3 top-14 z-10 max-h-[calc(100%-4.25rem)] w-[280px] max-w-[calc(100%-1.5rem)] overflow-y-auto ui-surface ui-surface-panel p-4 shadow-lg"
              aria-label={t("simulation.replay.nodeInspector")}
            >
              <div className="mb-2 flex items-start justify-between gap-2 border-b border-border pb-2">
                <strong className="min-w-0 truncate text-[13px] text-foreground">
                  {(activity?.name as string) ?? selectedId}
                </strong>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="size-6 shrink-0 p-0 text-muted-foreground"
                  onClick={() => setSelectedId(null)}
                  aria-label={t("simulation.replay.closeInspector")}
                >
                  <X className="size-3.5" />
                </Button>
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                <Row label={t("simulation.replay.active")} value={nodeState?.active ?? 0} />
                <Row label={t("simulation.replay.queued")} value={nodeState?.queued ?? 0} />
                <Row
                  label={t("simulation.replay.completed")}
                  value={nodeState?.done ?? 0}
                />
                {activity && (
                  <Row
                    label={t("simulation.studio.finalWaiting")}
                    value={formatDuration(
                      Number((activity.wait as { avg?: number })?.avg ?? 0),
                      lang,
                    )}
                  />
                )}
              </dl>
              {pool && (
                <div className="mt-2 border-t border-border pt-2">
                  <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
                    <span className="text-muted-foreground">
                      {t("simulation.replay.servedBy")}
                    </span>
                    <span className="min-w-0 truncate font-medium text-foreground" title={pool}>
                      {pool}
                    </span>
                  </div>
                  <Meter
                    label={pool}
                    value={Math.round(poolBusy * 100)}
                    tone={poolBusy >= 0.95 ? "danger" : poolBusy >= 0.8 ? "warning" : "ok"}
                    height={5}
                  />
                </div>
              )}
            </aside>
          )}
        </div>

        <div className="hidden xl:block">
          <ReplayInsightRail engine={engine} run={run} />
        </div>
      </div>

      {status?.granularity === "case" && (
        <div className="flex h-[156px] shrink-0 flex-col overflow-hidden ui-surface ui-surface-panel px-4 py-3">
          <CaseTimeline engine={engine} />
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-2")}>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="m-0 font-medium tabular-nums text-foreground">{value}</dd>
    </div>
  );
}
