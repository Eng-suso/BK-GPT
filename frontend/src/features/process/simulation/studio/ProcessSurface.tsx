import React from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import { SimulationCanvas, type NodeDecoration } from "../canvas/SimulationCanvas";
import { CanvasAnalytics } from "../canvas/CanvasAnalytics";
import { TokenLayer } from "../canvas/TokenLayer";
import type { BpmnViewer } from "../canvas/bpmnViewer";
import type { SimulationSummary } from "../simulationTypes";
import type { ReplayEngine } from "../replay/replayEngine";
import { useReplayFrame } from "../replay/useReplay";
import { CaseTimeline } from "../replay/CaseTimeline";
import { useReplayStatus } from "../replay/useReplay";
import { useSimulationSection } from "../useSimulationSection";

export function ProcessSurface({ engine, decorations, aggregate, inspectorHost, unavailable = false, summary, legend }: {
  engine: ReplayEngine; decorations?: NodeDecoration[]; aggregate: boolean; unavailable?: boolean; summary?: SimulationSummary | null; legend?: { label: string; delta?: boolean }; inspectorHost?: HTMLElement | null;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const { bpmnXml, selectedElementId, selectElement, openPanel } = useSimulationSection();
  const frame = useReplayFrame(engine);
  const status = useReplayStatus(engine);
  const [viewer, setViewer] = React.useState<BpmnViewer | null>(null);
  const [visible, setVisible] = React.useState(true);
  const pressure = React.useMemo<NodeDecoration[]>(() => Object.entries(frame?.elements ?? {}).map(([elementId, state]) => ({
    elementId,
    markers: state.pressure === "none" ? [] : [`sim-pressure-${state.pressure}`],
    badge: state.queued > 0 ? t("simulation.replay.inQueue", { n: state.queued }) : status?.granularity === "system" && state.active > 0 ? t("simulation.replay.systemChip", { active: state.active, queued: state.queued }) : undefined,
    badgeTone: state.pressure === "high" || state.pressure === "saturated" ? "warning" : "neutral",
  })), [frame, status?.granularity, t]);
  return <div className="sim-process-surface">
    <div className="sim-process-diagram">
      <SimulationCanvas sharedCanvas bpmnXml={bpmnXml} decorations={decorations ?? pressure} selectedElementId={selectedElementId} onViewerReady={setViewer}
        onSelectElement={(id) => { selectElement?.(id); if (id && engine.payload.elements[id]) openPanel?.("activity"); }}
        toolbarStart={<><Button size="sm" variant="ghost" aria-pressed={visible} onClick={() => setVisible((current) => !current)}>{t("simulation.studio.charts")}</Button>{legend && <div className="sim-process-legend"><span>{legend.label}</span>{legend.delta ? <><span><i aria-hidden style={{ background: "var(--color-status-success)" }} />{t("simulation.compare.better")}</span><span><i aria-hidden style={{ background: "var(--color-status-danger)" }} />{t("simulation.compare.worse")}</span></> : <><span>{t("simulation.heatmap.legendLow")}</span><span className="sim-heat-legend" aria-hidden>{[0,1,2,3,4].map(level => <i key={level} style={{ background: `var(--sim-heat-${level})` }} />)}</span><span>{t("simulation.heatmap.legendHigh")}</span></>}</div>}</>} />
      {!aggregate && <TokenLayer viewer={viewer} engine={engine} />}
      {frame && !unavailable && <CanvasAnalytics viewer={viewer} engine={engine} frame={frame} summary={summary} selectedId={selectedElementId ?? null} visible={visible} inspectorHost={inspectorHost} onVisibilityChange={setVisible} />}
    </div>
    {status?.granularity === "case" && !aggregate && <div className="sim-studio-case"><CaseTimeline engine={engine} /></div>}
  </div>;
}
