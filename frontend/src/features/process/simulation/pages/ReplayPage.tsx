import React from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { Button } from "@/ui/button";
import { Meter } from "@/components/data";
import { cn } from "@/lib/utils";

import { SimulationCanvas, type NodeDecoration } from "../canvas/SimulationCanvas";
import { TokenLayer } from "../canvas/TokenLayer";
import { TransportBar } from "../replay/TransportBar";
import { ReplayGate } from "../replay/ReplayGate";
import { ReplayInsightRail } from "../replay/ReplayInsightRail";
import { CaseTimeline } from "../replay/CaseTimeline";
import { useReplayFrame, useReplayStatus } from "../replay/useReplay";
import type { ReplayEngine } from "../replay/replayEngine";
import type { BpmnViewer } from "../canvas/bpmnViewer";
import type { SimulationRun } from "../simulationTypes";
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

function ReplayStage({ engine, bpmnXml, run }: ReplayStageProps): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const frame = useReplayFrame(engine);
  const status = useReplayStatus(engine);
  const [viewer, setViewer] = React.useState<BpmnViewer | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const bottleneckEl =
    (run.summary?.bottleneck as { el?: string } | null | undefined)?.el ?? null;

  const systemMode = status?.granularity === "system";

  const flowMarkers = React.useMemo<NodeDecoration[]>(() => {
    if (!systemMode) return [];
    const flows = engine.payload.flows ?? {};
    const attributed = Object.entries(flows).filter(([, v]) => v.attributed);
    const max = Math.max(1, ...attributed.map(([, v]) => v.count));
    return attributed
      .filter(([, v]) => v.count > 0)
      .map(([id, v]) => ({
        elementId: id,
        markers: [`sim-flow-${Math.min(4, Math.max(1, Math.ceil((v.count / max) * 4)))}`],
      }));
  }, [systemMode, engine]);

  const decorations = React.useMemo<NodeDecoration[]>(() => {
    if (!frame) return flowMarkers;
    const out: NodeDecoration[] = [...flowMarkers];
    for (const [el, state] of Object.entries(frame.elements)) {
      const markers: string[] = [];
      if (state.pressure !== "none") markers.push(PRESSURE_MARKER[state.pressure]);
      if (el === bottleneckEl) markers.push("sim-node-bottleneck");
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
  }, [frame, bottleneckEl, t, flowMarkers, systemMode]);

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
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="shrink-0 overflow-hidden rounded-lg border border-border bg-card">
        <TransportBar engine={engine} />
      </div>

      <div className="flex min-h-0 flex-1 gap-3">
        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border bg-card">
          <SimulationCanvas
            className="min-h-0 flex-1"
            bpmnXml={bpmnXml}
            decorations={decorations}
            selectedElementId={selectedId}
            onSelectElement={setSelectedId}
            onViewerReady={setViewer}
          />
          <TokenLayer viewer={viewer} engine={engine} />

          {selectedId && (
            <aside
              className="absolute right-3 top-14 z-10 w-[236px] rounded-lg border border-border bg-card p-3 shadow-lg"
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
                    label={t("simulation.results.table.waiting")}
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
        <div className="flex h-[156px] shrink-0 flex-col overflow-hidden rounded-lg border border-border bg-card px-4 py-3">
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
