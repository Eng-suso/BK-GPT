import React from "react";
import { useTranslation } from "react-i18next";
import { ChartNoAxesCombined, Plus, Settings2, GripVertical, Check, RotateCcw, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/ui/dialog";
import { StatTile } from "@/components/data";
import { useSimulationSection } from "../useSimulationSection";
import { useReplayFrame } from "../replay/useReplay";
import { TransportBar } from "../replay/TransportBar";
import type { ReplayEngine } from "../replay/replayEngine";
import type { SimulationRun } from "../simulationTypes";
import { formatDuration, formatCurrency } from "../simulationResults";
import { KINDS, createWidget, defaultLayout, layoutSchema, moveWidget, widgetData, type DashboardLayout, type DashboardWidget, type WidgetKind } from "./dashboardModel";
import { WidgetView } from "./WidgetView";
import { formatMetric } from "./dashboardFormatting";
import { WidgetInspector } from "./WidgetInspector";

const DRAG_TYPE = "application/delir-widget";
type Persisted = { layout: DashboardLayout; error: boolean; stored: boolean };

function readLayout(key: string): Persisted {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return { layout: defaultLayout(), error: false, stored: false };
    const parsed = layoutSchema.safeParse(JSON.parse(raw));
    return { layout: parsed.success ? parsed.data : defaultLayout(), error: !parsed.success, stored: parsed.success };
  } catch { return { layout: defaultLayout(), error: true, stored: false }; }
}

export function DashboardWorkspace({ engine, run }: { engine: ReplayEngine; run: SimulationRun }): React.JSX.Element {
  const { projectId, processId } = useSimulationSection();
  return <DashboardBody key={`${projectId}:${processId}`} storageKey={`delir:simulation:dashboard:${projectId}:${processId}`} engine={engine} run={run} />;
}

function DashboardBody({ engine, run, storageKey }: { engine: ReplayEngine; run: SimulationRun; storageKey: string }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language.startsWith("it") ? "it" : "en";
  const frame = useReplayFrame(engine);
  const [saved, setSaved] = React.useState(() => readLayout(storageKey));
  const [layout, setLayout] = React.useState(saved.layout);
  const [editing, setEditing] = React.useState(false);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [library, setLibrary] = React.useState(false);
  const [activityId, setActivityId] = React.useState("all");
  const [saveError, setSaveError] = React.useState(false);
  const selectedWidget = layout.groups.flatMap((group) => group.widgets).find((widget) => widget.id === selected);
  const editorRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (selected) editorRef.current?.querySelector<HTMLInputElement>("input")?.focus();
  }, [selected]);

  const closeInspector = () => {
    const button = document.getElementById(`configure-${selected}`);
    setSelected(null);
    button?.focus();
  };
  const save = () => {
    try {
      const validated = layoutSchema.parse(layout);
      localStorage.setItem(storageKey, JSON.stringify(validated));
      setSaved({ layout: validated, error: false, stored: true }); setEditing(false); setSelected(null); setSaveError(false);
    } catch { setSaveError(true); }
  };
  const patchWidget = (patch: Partial<DashboardWidget>) => setLayout((current) => ({ ...current, groups: current.groups.map((group) => ({ ...group, widgets: group.widgets.map((widget) => widget.id === selected ? { ...widget, ...patch } : widget) })) }));
  const addWidget = (kind: WidgetKind) => {
    const widget = createWidget(kind);
    const group = layout.groups.find((group) => group.widgets.length < 24);
    if (!group) return;
    setEditing(true); setLibrary(false); setSelected(widget.id);
    setLayout((current) => ({ ...current, groups: current.groups.map((item) => item.id === group.id ? { ...item, widgets: [...item.widgets, widget] } : item) }));
  };
  const move = (direction: -1 | 1) => {
    const group = layout.groups.find((group) => group.widgets.some((widget) => widget.id === selected));
    if (!group || !selected) return;
    const index = group.widgets.findIndex((widget) => widget.id === selected);
    const beforeId = direction === -1 ? group.widgets[index - 1]?.id : group.widgets[index + 2]?.id;
    setLayout((current) => moveWidget(current, selected, group.id, beforeId));
  };
  const duplicate = () => {
    if (!selectedWidget) return;
    const copy = { ...selectedWidget, id: crypto.randomUUID(), title: `${selectedWidget.title || t(`simulation.studio.metric.${selectedWidget.metric}`)} · ${t("simulation.studio.copy")}`.slice(0, 120) };
    setLayout((current) => ({ ...current, groups: current.groups.map((group) => group.widgets.some((widget) => widget.id === selected) ? { ...group, widgets: [...group.widgets, copy] } : group) }));
    setSelected(copy.id);
  };
  const remove = () => {
    setLayout((current) => ({ ...current, groups: current.groups.map((group) => ({ ...group, widgets: group.widgets.filter((widget) => widget.id !== selected) })) }));
    setSelected(null);
  };
  if (!frame) return <div />;

  const kpis = ["active", "queued", "completed", "throughput", "cycle", "cost"] as const;
  return <div className="sim-dashboard-workspace">
    <header className="sim-dashboard-header"><div><p className="sim-eyebrow">{run.scenario_name}</p><h2>{t("simulation.studio.dashboardTitle")}</h2><p className="sim-help">{t("simulation.studio.dashboardHint")}</p></div>
      <div className="sim-dashboard-actions">
        {editing ? <><Button size="sm" variant="ghost" onClick={() => { setLayout(saved.layout); setEditing(false); setSelected(null); setSaveError(false); }}>{t("simulation.studio.cancel")}</Button><Button size="sm" onClick={save}><Check aria-hidden className="size-4" />{t("simulation.studio.save")}</Button></>
          : <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Settings2 aria-hidden className="size-4" />{t("simulation.studio.edit")}</Button>}
        <Button size="sm" variant="outline" onClick={() => setLibrary(true)} disabled={layout.groups.every((group) => group.widgets.length >= 24)}><Plus aria-hidden className="size-4" />{t("simulation.studio.addWidget")}</Button>
      </div>
    </header>
    <div className="sim-transport-surface"><TransportBar engine={engine} /></div>
    <div className="sim-dashboard-toolbar"><span className="sim-scope-badge"><span aria-hidden />{t("simulation.studio.currentTime")}</span>
      <label className="sim-filter"><span>{t("simulation.studio.activityFilter")}</span><select aria-label={t("simulation.studio.activityFilter")} value={activityId} onChange={(event) => setActivityId(event.target.value)}><option value="all">{t("simulation.studio.allActivities")}</option>{Object.entries(engine.payload.elements).map(([id, element]) => <option key={id} value={id}>{element.name}</option>)}</select></label>
      {activityId !== "all" && <Button variant="ghost" size="sm" onClick={() => setActivityId("all")}><X aria-hidden className="size-3" />{t("simulation.studio.clearFilter")}</Button>}
      <span className="sim-help sim-storage-status" role="status">{t(editing ? "simulation.studio.unsaved" : saved.stored ? "simulation.studio.savedDevice" : "simulation.studio.defaultLayout")}</span>
    </div>
    {(saved.error || saveError) && <p role="alert" className="sim-save-error">{t(saveError ? "simulation.studio.saveError" : "simulation.studio.restoreError")}</p>}
    <section className="sim-kpi-strip" aria-label={t("simulation.studio.currentMetrics")}>{kpis.map((metric) => {
      const data = widgetData(engine, frame, metric);
      return <StatTile key={metric} className="sim-kpi" label={t(`simulation.studio.metric.${metric}`)} value={formatMetric(data.value, data.unit, lang)} hint={t(metric === "cycle" ? "simulation.studio.closedCases" : "simulation.studio.globalScope")} tone={metric === "queued" && (data.value ?? 0) > 0 ? "warning" : "neutral"} />;
    })}</section>
    <div className={`sim-dashboard-body ${editing && selectedWidget ? "has-inspector" : ""}`}>
      <div className="sim-dashboard-sections">
        {layout.groups.map((group, index) => <section key={group.id} className="sim-widget-section" aria-label={group.title || t("simulation.studio.sectionNumber", { n: index + 1 })}>
          <header className="sim-section-header">
            {editing ? <label className="sim-section-title"><span className="sr-only">{t("simulation.studio.sectionTitle")}</span><input maxLength={120} value={group.title} placeholder={t("simulation.studio.sectionNumber", { n: index + 1 })} onChange={(event) => setLayout((current) => ({ ...current, groups: current.groups.map((item) => item.id === group.id ? { ...item, title: event.target.value } : item) }))} /></label> : <h3>{group.title || t("simulation.studio.sectionNumber", { n: index + 1 })}</h3>}
            {editing && group.widgets.length === 0 && layout.groups.length > 1 && <Button variant="ghost" size="sm" onClick={() => setLayout((current) => ({ ...current, groups: current.groups.filter((item) => item.id !== group.id) }))}>{t("simulation.studio.removeSection")}</Button>}
          </header>
          <div className="sim-widget-grid">
            {group.widgets.map((widget) => {
              const data = widgetData(engine, frame, widget.metric, widget.followFilter ? activityId : "all");
              const title = widget.title || t(`simulation.studio.metric.${widget.metric}`);
              return <article key={widget.id} className={`sim-widget ${widget.width === "full" ? "is-full" : ""} ${editing ? "is-editing" : ""} ${selected === widget.id ? "is-selected" : ""}`} data-widget-id={widget.id}
                onDragOver={(event) => { if (editing && event.dataTransfer.types.includes(DRAG_TYPE)) event.preventDefault(); }}
                onDrop={(event) => { if (!editing || !event.dataTransfer.types.includes(DRAG_TYPE)) return; event.preventDefault(); const id = event.dataTransfer.getData(DRAG_TYPE); setLayout((current) => moveWidget(current, id, group.id, widget.id)); }}>
                <header className="sim-widget-heading">
                  {editing && <button type="button" className="sim-drag-handle" draggable aria-label={t("simulation.studio.drag", { title })} onDragStart={(event) => { event.dataTransfer.setData(DRAG_TYPE, widget.id); event.dataTransfer.effectAllowed = "move"; }} onClick={() => setSelected(widget.id)}><GripVertical aria-hidden className="size-4" /></button>}
                  <div className="min-w-0"><h4>{title}</h4><p>{t(`simulation.studio.kind.${widget.kind}`)} · {t(data.filtered ? "simulation.studio.filteredScope" : "simulation.studio.globalScope")}</p></div>
                  {editing && <Button id={`configure-${widget.id}`} size="icon" variant="ghost" onClick={() => setSelected(widget.id)} aria-label={t("simulation.studio.configure", { title })}><Settings2 aria-hidden className="size-4" /></Button>}
                </header>
                <WidgetView widget={widget} engine={engine} frame={frame} activityId={activityId} />
              </article>;
            })}
            {group.widgets.length === 0 && <p className="sim-empty-section">{t("simulation.studio.emptySection")}</p>}
          </div>
        </section>)}
        {editing && <div className="sim-layout-actions"><Button variant="outline" size="sm" disabled={layout.groups.length >= 12} onClick={() => setLayout((current) => ({ ...current, groups: [...current.groups, { id: crypto.randomUUID(), title: "", widgets: [] }] }))}><Plus aria-hidden className="size-4" />{t("simulation.studio.addSection")}</Button><Button variant="ghost" size="sm" onClick={() => { setLayout(defaultLayout()); setSelected(null); }}><RotateCcw aria-hidden className="size-4" />{t("simulation.studio.reset")}</Button></div>}
        <details className="sim-final-results"><summary>{t("simulation.studio.finalResults")}</summary><p className="sim-help">{t("simulation.studio.finalHint")}</p><div className="sim-final-grid"><StatTile label={t("simulation.results.cycleTime")} value={run.summary ? formatDuration(run.summary.cycle.avg, lang) : "—"} /><StatTile label={t("simulation.results.costPerCase")} value={run.summary ? formatCurrency(run.summary.cost.perCase, lang) : "—"} /><StatTile label={t("simulation.dashboard.peakQueue")} value={engine.payload.series.global.queued?.length ? String(Math.max(...engine.payload.series.global.queued)) : "—"} /></div></details>
      </div>
      {editing && selectedWidget && <div className="sim-inspector-slot" ref={editorRef}><WidgetInspector widget={selectedWidget} layout={layout} engine={engine} activityId={activityId} onChange={patchWidget} onClose={closeInspector} onDelete={remove} onDuplicate={duplicate} onMove={move} onGroup={(id) => setLayout((current) => moveWidget(current, selectedWidget.id, id))} /></div>}
    </div>
    <Dialog open={library} onOpenChange={setLibrary}><DialogContent onCloseAutoFocus={(event) => { if (selected) { event.preventDefault(); editorRef.current?.querySelector<HTMLInputElement>("input")?.focus(); } }} className="max-h-[85vh] overflow-y-auto sm:max-w-xl"><DialogTitle>{t("simulation.studio.libraryTitle")}</DialogTitle><DialogDescription>{t("simulation.studio.libraryHint")}</DialogDescription><div className="sim-widget-library">{KINDS.map((kind) => <button type="button" key={kind} onClick={() => addWidget(kind)}><ChartNoAxesCombined aria-hidden className="size-5" /><strong>{t(`simulation.studio.kind.${kind}`)}</strong><span>{t(`simulation.studio.kindHint.${kind}`)}</span></button>)}</div></DialogContent></Dialog>
  </div>;
}
