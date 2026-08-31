import React from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";

import { SimulationCanvas, type NodeDecoration } from "../canvas/SimulationCanvas";
import { TokenLayer } from "../canvas/TokenLayer";
import { TransportBar } from "../replay/TransportBar";
import { ReplayGate } from "../replay/ReplayGate";
import { useReplayFrame } from "../replay/useReplay";
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
  const [viewer, setViewer] = React.useState<BpmnViewer | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const bottleneckEl =
    (run.summary?.bottleneck as { el?: string } | null | undefined)?.el ?? null;

  const decorations = React.useMemo<NodeDecoration[]>(() => {
    if (!frame) return [];
    const out: NodeDecoration[] = [];
    for (const [el, state] of Object.entries(frame.elements)) {
      const markers: string[] = [];
      if (state.pressure !== "none") markers.push(PRESSURE_MARKER[state.pressure]);
      if (el === bottleneckEl) markers.push("sim-node-bottleneck");
      if (markers.length === 0 && state.queued === 0) continue;
      out.push({
        elementId: el,
        markers,
        badge:
          state.queued > 0
            ? t("simulation.replay.inQueue", { n: state.queued })
            : undefined,
        badgeTone:
          state.pressure === "saturated" || state.pressure === "high"
            ? "warning"
            : "neutral",
      });
    }
    return out;
  }, [frame, bottleneckEl, t]);

  const activity =
    selectedId && Array.isArray(run.summary?.byActivity)
      ? (run.summary.byActivity as Array<Record<string, unknown>>).find(
          (a) => a.el === selectedId,
        )
      : undefined;
  const nodeState = selectedId && frame ? frame.elements[selectedId] : undefined;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TransportBar engine={engine} />
      <div className="relative flex min-h-0 flex-1">
        <SimulationCanvas
          className="h-full flex-1"
          bpmnXml={bpmnXml}
          decorations={decorations}
          selectedElementId={selectedId}
          onSelectElement={setSelectedId}
          onViewerReady={setViewer}
        />
        <TokenLayer viewer={viewer} engine={engine} />

        {selectedId && (
          <aside
            className="absolute right-3 top-3 z-10 w-[248px] rounded-lg border border-border bg-card p-3 shadow-lg"
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
          </aside>
        )}
      </div>
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
