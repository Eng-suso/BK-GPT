import React from "react";
import { useTranslation } from "react-i18next";
import { SlidersHorizontal, ListChecks, GitCompareArrows, Layers, Lightbulb, X, Workflow } from "lucide-react";
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
  const { runs, activeRunId, bpmnXml, panel, openPanel, selectedElementId, selectElement, inspectedWidgetId } = useSimulationSection();
  const { engine, isLoading, noArtifact, error } = useReplaySession();
  const run = resolveActiveRun(runs, activeRunId != null ? String(activeRunId) : undefined);
  const ready = engine && run?.status === "completed";
  const [decorations, setDecorations] = React.useState<NodeDecoration[]>([]);
  const [host, setHost] = React.useState<HTMLDivElement | null>(null);
  const triggerRef = React.useRef<HTMLElement | null>(null);
  const dockRef = React.useRef<HTMLElement>(null);
  const aggregate = panel === "heatmap" || panel === "compare";
  React.useEffect(() => { if (aggregate) engine?.pause(); }, [aggregate, engine]);
  React.useEffect(() => {
    if (panel && !dockRef.current?.contains(document.activeElement)) {
      if (panel === "widget" && inspectedWidgetId) triggerRef.current = document.getElementById(inspectedWidgetId.startsWith("pin:") ? `configure-pin-${inspectedWidgetId.slice(4)}` : `configure-${inspectedWidgetId}`);
      else if (panel === "activity") triggerRef.current = document.activeElement as HTMLElement;
      if (panel !== "widget") dockRef.current?.querySelector<HTMLElement>("[data-dock-title]")?.focus({ preventScroll: true });
      if (window.matchMedia("(max-width: 800px)").matches) dockRef.current?.scrollIntoView({ block: "start" });
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
  return <div className="sim-studio" data-simulation-studio>
    <div className="sim-studio-tools" role="group" aria-label={t("simulation.unified.tools")}>
      <div className="sim-studio-identity"><Workflow aria-hidden className="size-4" /><h2>{t("simulation.unified.title")}</h2></div>
      <div className="sim-studio-tool-actions">{TOOLS.map(([name, Icon]) => <Button key={name} size="sm" variant={panel === name ? "secondary" : "ghost"} aria-pressed={panel === name} onClick={(event) => show(panel === name ? null : name, event.currentTarget)}><Icon aria-hidden className="size-4" />{t(`simulation.unified.tool.${name}`)}</Button>)}</div>
    </div>
    {ready && <div className="sim-studio-transport"><TransportBar engine={engine} /></div>}
    <div className={`sim-studio-body ${panel ? "has-dock" : ""}`}>
      <section className="sim-studio-board" aria-label={t("simulation.unified.canvas")}>
        {ready ? <DashboardWorkspace engine={engine} run={run} integrated inspectorHost={host}
          process={<ProcessSurface engine={engine} aggregate={aggregate} inspectorHost={host} decorations={aggregate ? decorations : undefined} />}
          processScope={aggregate ? t("simulation.unified.aggregateScope") : t("simulation.studio.currentTime")} />
          : <div className="sim-studio-start"><div className="sim-studio-empty-process"><SimulationCanvas bpmnXml={bpmnXml} selectedElementId={selectedElementId} onSelectElement={selectElement} /></div>
            <EmptyState title={t(isLoading ? "simulation.loading" : noArtifact ? "simulation.replay.noArtifact" : run?.status === "pending" ? "simulation.running" : run?.status === "failed" ? "simulation.status.failed" : "simulation.replay.noRun")} description={error ?? run?.error ?? t("simulation.unified.startHint")}
              action={<Button onClick={() => show("scenario")}>{t("simulation.unified.tool.scenario")}</Button>} />
          </div>}
      </section>
      <aside ref={dockRef} className="sim-studio-dock" hidden={!panel} aria-label={t("simulation.unified.details")} onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); close(); } }}>
        <header className="sim-studio-dock-header"><div><p className="sim-eyebrow">{t(aggregate || panel === "overview" || panel === "insights" ? "simulation.unified.aggregateScope" : "simulation.unified.context")}</p><h3 data-dock-title tabIndex={-1}>{title}</h3></div><Button size="icon" variant="ghost" onClick={close} aria-label={t("simulation.unified.closePanel")}><X aria-hidden className="size-4" /></Button></header>
        <div className="sim-studio-dock-body">
          {panel === "scenario" && <ScenarioBuilderPage embedded />}
          {panel === "overview" && <SimulationWorkspace embedded />}
          {panel === "heatmap" && <HeatmapPage embedded onDecorations={setDecorations} />}
          {panel === "compare" && <ComparePage embedded onDecorations={setDecorations} />}
          {panel === "insights" && <div>{ready && <details className="sim-current-insights"><summary>{t("simulation.unified.currentDetails")}</summary><ReplayInsightRail engine={engine} run={run} embedded /></details>}<InsightsPage /></div>}
          {panel === "activity" && ready && <ActivityDetails engine={engine} run={run} />}
          <div ref={setHost} className="sim-studio-widget-host" />
        </div>
      </aside>
    </div>
  </div>;
}
