import React from "react";
import { useSearchParams } from "react-router-dom";
import type { HeatMetric } from "./simulationResults";
import { useReplayEngine } from "./replay/useReplay";
import { useTranslation } from "react-i18next";
import { SlidersHorizontal, ListChecks, GitCompareArrows, Layers, Lightbulb } from "lucide-react";
import { CanvasWorkspaceShell, WorkspaceCommandBar, WorkspaceInspector } from "@/components/layout";
import { Button } from "@/ui/button";
import { EmptyState } from "@/components/feedback";
import { DashboardWorkspace } from "./dashboard/DashboardWorkspace";
import { ReplayInsightRail } from "./replay/ReplayInsightRail";
import { TransportBar } from "./replay/TransportBar";
import { useReplaySession } from "./replay/useReplaySession";
import { useSimulationSection, resolveActiveRun, type SimulationPanel } from "./useSimulationSection";
import { ScenarioBuilderPage } from "./pages/ScenarioBuilderPage";
import { SimulationWorkspace } from "./SimulationWorkspace";
import { ComparePage } from "./pages/ComparePage";
import { HeatmapPage } from "./pages/HeatmapPage";
import { InsightsPage } from "./pages/InsightsPage";
import { ProcessSurface } from "./studio/ProcessSurface";
import { ActivityDetails } from "./studio/ActivityDetails";
import { SimulationCanvas, type NodeDecoration } from "./canvas/SimulationCanvas";
import "./studio/studio.css";

const TOOLS = [["scenario", SlidersHorizontal], ["overview", ListChecks], ["heatmap", Layers], ["compare", GitCompareArrows], ["insights", Lightbulb]] as const;

export function SimulationStudio(): React.JSX.Element {
  const { t } = useTranslation("process");
  const { runs, activeRunId, bpmnXml, panel, openPanel, selectedElementId, selectElement, inspectedWidgetId, analysisView, setAnalysisView } = useSimulationSection();
  const { engine, isLoading, noArtifact, error } = useReplaySession();
  const run = resolveActiveRun(runs, activeRunId != null ? String(activeRunId) : undefined);
  const ready = engine && run?.status === "completed";
  const [heatMetric, setHeatMetric] = React.useState<HeatMetric>("wait");
  const [decorations, setDecorations] = React.useState<NodeDecoration[]>([]);
  const [actionsHost, setActionsHost] = React.useState<HTMLDivElement | null>(null);
  const [commandsHost, setCommandsHost] = React.useState<HTMLDivElement | null>(null);
  const [host, setHost] = React.useState<HTMLDivElement | null>(null);
  const triggerRef = React.useRef<HTMLElement | null>(null);
  const dockRef = React.useRef<HTMLElement>(null);
  const view = analysisView ?? (panel === "compare" ? "compare" : panel === "heatmap" ? "heatmap" : panel === "overview" || panel === "insights" ? "final" : "replay");
  const aggregate = view !== "replay";
  const [query] = useSearchParams();
  const completed = runs.filter(item => item.status === "completed" && item.summary);
  const comparedRun = completed.find(item => String(item.id) === query.get("b")) ?? completed.find(item => item.id === activeRunId) ?? completed[0];
  const comparedA = completed.find(item => String(item.id) === query.get("a") && item.id !== comparedRun?.id) ?? completed.find(item => item.id !== comparedRun?.id);
  const analysisRun = view === "compare" && completed.length >= 2 ? query.get("compareMode") === "a" ? comparedA : comparedRun : run;
  const finalReplay = useReplayEngine(aggregate ? analysisRun?.id ?? null : null, aggregate, true);
  const displayedEngine = aggregate ? finalReplay.engine ?? engine : engine;
  const unavailable = aggregate && !finalReplay.engine;
  const dockOpen = Boolean(panel);
  const scope = aggregate ? `${t("simulation.scene.finalScope")} · #${analysisRun?.id ?? "—"}` : t("simulation.studio.currentTime");
  React.useEffect(() => { if (aggregate) engine?.pause(); }, [aggregate, engine]);
  React.useEffect(() => {
    if (panel && !dockRef.current?.contains(document.activeElement)) {
      if (panel === "widget" && inspectedWidgetId) triggerRef.current = document.getElementById(inspectedWidgetId.startsWith("pin:") ? `configure-pin-${inspectedWidgetId.slice(4)}` : `configure-${inspectedWidgetId}`);
      else if (panel === "activity") triggerRef.current = document.activeElement as HTMLElement;
      if (panel !== "widget") dockRef.current?.querySelector<HTMLElement>("[data-dock-title]")?.focus({ preventScroll: true });

    }
  }, [panel, inspectedWidgetId]);
  const show = (next: SimulationPanel | null, opener?: HTMLElement) => {
    if (next) triggerRef.current = opener ?? document.activeElement as HTMLElement;
    openPanel?.(next);
  };
  const close = () => {
    openPanel?.(null);
    if (triggerRef.current?.isConnected) triggerRef.current.focus({ preventScroll: true });
  };
  const title = panel === "widget" ? t("simulation.studio.inspector") : panel === "activity" ? t("simulation.replay.nodeInspector") : t(`simulation.unified.tool.${panel}`);
  return <CanvasWorkspaceShell label={t("simulation.unified.title")} className="sim-studio" bodyClassName={`sim-studio-body ${dockOpen ? "has-dock" : ""}`} stageClassName="sim-studio-board"
    commands={<WorkspaceCommandBar className="sim-studio-tools" label={t("simulation.unified.tools")}>
      <div className="sim-studio-tool-actions"><Button size="sm" variant={view === "replay" ? "secondary" : "ghost"} aria-pressed={view === "replay"} onClick={() => setAnalysisView?.("replay")}>{t("simulation.scene.replay")}</Button><Button size="sm" variant={aggregate ? "secondary" : "ghost"} aria-pressed={aggregate} onClick={() => setAnalysisView?.("final")}>{t("simulation.workspaceHierarchy.final")}</Button>{TOOLS.map(([name, Icon]) => <Button key={name} size="sm" variant={panel === name || view === name ? "secondary" : "ghost"} aria-pressed={panel === name || view === name} onClick={(event) => show(panel === name ? null : name, event.currentTarget)}><Icon aria-hidden className="size-4" />{t(`simulation.unified.tool.${name}`)}</Button>)}</div>
      <div className="sim-studio-dashboard-commands" ref={setCommandsHost} />
    </WorkspaceCommandBar>}
    inspector={<WorkspaceInspector bodyClassName="sim-studio-dock-body" ref={dockRef} className={`sim-studio-dock ${panel === "compare" ? "is-comparison" : ""}`} hidden={!dockOpen} label={t("simulation.unified.details")} title={title} scope={t(aggregate || panel === "overview" || panel === "insights" || panel === "compare" ? "simulation.unified.aggregateScope" : "simulation.unified.context")} closeLabel={t("simulation.unified.closePanel")} onClose={close}>
      {panel === "compare" && <ComparePage compact embedded onDecorations={setDecorations} />}
      {panel === "scenario" && <ScenarioBuilderPage embedded />}
      {panel === "overview" && <SimulationWorkspace embedded />}
      {panel === "heatmap" && <>{!aggregate && <Button size="sm" variant="outline" onClick={() => setAnalysisView?.("final")}>{t("simulation.workspaceHierarchy.applyFinalHeatmap")}</Button>}<HeatmapPage embedded onDecorations={setDecorations} onMetric={setHeatMetric} /></>}
      {panel === "insights" && <div>{ready && <details className="sim-current-insights"><summary>{t("simulation.unified.currentDetails")}</summary><ReplayInsightRail engine={engine} run={run} embedded /></details>}<InsightsPage embedded /></div>}
      {panel === "activity" && ready && <ActivityDetails engine={displayedEngine ?? engine} run={analysisRun ?? run} unavailable={unavailable} />}
      <div ref={setHost} className="sim-studio-widget-host" />
    </WorkspaceInspector>}
    playback={ready && <div className="sim-studio-transport">{aggregate ? <div className="sim-final-transport"><strong>{t(view === "compare" ? "simulation.scene.comparisonScope" : "simulation.scene.finalScope")}</strong><Button variant="outline" size="sm" onClick={() => setAnalysisView?.("replay")}>{t("simulation.scene.resume")}</Button></div> : <TransportBar engine={engine} />}</div>}
  >
      <section className="contents" aria-label={t("simulation.unified.canvas")}>
        {ready && displayedEngine && analysisRun ? <DashboardWorkspace engine={displayedEngine} run={analysisRun} final={aggregate} unavailable={unavailable} artifactLoading={finalReplay.isLoading} integrated commandsHost={commandsHost} inspectorHost={host} onProcessActionsHost={setActionsHost}
          process={<ProcessSurface engine={displayedEngine} aggregate={aggregate} unavailable={unavailable} summary={aggregate ? analysisRun.summary : undefined} legend={view === "compare" ? { label: t("simulation.diagram.legendWait"), delta: !["a", "b"].includes(query.get("compareMode") ?? "") } : (view === "heatmap" || (aggregate && panel === "heatmap")) ? { label: t(`simulation.heatmap.metric.${heatMetric}`) } : undefined} inspectorHost={host} actionsHost={actionsHost} decorations={view === "compare" || view === "heatmap" || (aggregate && panel === "heatmap") ? decorations : aggregate ? [] : undefined} />}
          processScope={scope} />
          : <div className="sim-studio-start"><div className="sim-studio-empty-process"><SimulationCanvas bpmnXml={bpmnXml} selectedElementId={selectedElementId} onSelectElement={selectElement} /></div>
            <EmptyState title={t(isLoading ? "simulation.loading" : noArtifact ? "simulation.replay.noArtifact" : run?.status === "pending" ? "simulation.running" : run?.status === "failed" ? "simulation.status.failed" : "simulation.replay.noRun")} description={error ?? run?.error ?? t("simulation.unified.startHint")}
              action={<Button onClick={() => show("scenario")}>{t("simulation.unified.tool.scenario")}</Button>} />
          </div>}
      </section>
  </CanvasWorkspaceShell>;
}
