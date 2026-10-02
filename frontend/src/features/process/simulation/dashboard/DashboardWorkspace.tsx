import React from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { ChartNoAxesCombined, Plus, Settings2, GripVertical, Check, RotateCcw, X, Workflow, ArrowUp, ArrowDown, Expand, Shrink, Undo2, Redo2 } from "lucide-react";

import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/ui/dialog";
import { StatTile } from "@/components/data";
import { useSimulationSection } from "../useSimulationSection";
import { useReplayFrame } from "../replay/useReplay";
import { TransportBar } from "../replay/TransportBar";
import type { ReplayEngine } from "../replay/replayEngine";
import type { SimulationRun } from "../simulationTypes";
import { formatDuration, formatCurrency } from "../simulationResults";
import { KINDS, createWidget, defaultLayout, layoutSchema, moveWidget, widgetData, type DashboardLayout, type DashboardWidget, type WidgetKind, type CanvasRect } from "./dashboardModel";
import { WidgetView } from "./WidgetView";
import { formatMetric } from "./dashboardFormatting";
import { AnalyticalCanvas, type SceneObject } from "../studio/AnalyticalCanvas";
import { sceneRects, PROCESS_ID } from "../studio/canvasGeometry";
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

type WorkspaceProps = { engine: ReplayEngine; run: SimulationRun; integrated?: boolean; process?: React.ReactNode; processScope?: string; inspectorHost?: HTMLElement | null; final?: boolean; unavailable?: boolean; artifactLoading?: boolean };

export function DashboardWorkspace(props: WorkspaceProps): React.JSX.Element {
  const { projectId, processId } = useSimulationSection();
  return <DashboardBody key={`${projectId}:${processId}`} storageKey={`delir:simulation:dashboard:${projectId}:${processId}`} {...props} />;
}

function DashboardBody({ engine, run, storageKey, integrated = false, process, processScope, inspectorHost, final = false, unavailable = false, artifactLoading = false }: WorkspaceProps & { storageKey: string }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language.startsWith("it") ? "it" : "en";
  const frame = useReplayFrame(engine);
  const [saved, setSaved] = React.useState(() => readLayout(storageKey));
  const [layout, setLayout] = React.useState(saved.layout);
  const [editing, setEditing] = React.useState(false);
  const [selected, setSelectedState] = React.useState<string | null>(null);
  const { selectedElementId, selectElement, panel, openPanel, inspectedWidgetId, inspectWidget } = useSimulationSection();
  const setSelected = (id: string | null) => {
    setSelectedState(id);
    if (integrated && (id || panel === "widget")) {
      if (inspectWidget) inspectWidget(id); else openPanel?.(id ? "widget" : null);
    }
  };
  const previousPanel = React.useRef(panel);
  React.useEffect(() => {
    if (previousPanel.current === "widget" && panel !== "widget") setSelectedState(null);
    previousPanel.current = panel;
  }, [panel]);
  const history = React.useRef<{ past: DashboardLayout[]; future: DashboardLayout[] }>({ past: [], future: [] });
  const [historyCounts, setHistoryCounts] = React.useState({ past: 0, future: 0 });
  const refreshHistory = () => setHistoryCounts({ past: history.current.past.length, future: history.current.future.length });
  const changeLayout = (update: React.SetStateAction<DashboardLayout>) => {
    history.current.past.push(layout);
    history.current.past = history.current.past.slice(-30);
    history.current.future = [];
    setLayout(update); refreshHistory();
  };
  const undo = (redo = false) => {
    const source = redo ? history.current.future : history.current.past;
    const next = source.pop();
    if (!next) return;
    (redo ? history.current.past : history.current.future).push(layout);
    setLayout(next); refreshHistory();
  };
  const [library, setLibrary] = React.useState(false);
  const [localActivityId, setLocalActivityId] = React.useState("all");
  const activityId = integrated ? selectedElementId ?? "all" : localActivityId;
  const setActivityId = (id: string) => integrated ? selectElement?.(id === "all" ? null : id) : setLocalActivityId(id);
  const [saveError, setSaveError] = React.useState(false);
  const selectedWidget = layout.groups.flatMap((group) => group.widgets).find((widget) => widget.id === selected);
  const editorRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (selected && (!integrated || panel === "widget")) editorRef.current?.querySelector<HTMLInputElement>("input")?.focus({ preventScroll: true });
  }, [selected, inspectorHost, panel, integrated]);

  const closeInspector = () => {
    const button = document.getElementById(`configure-${selected}`);
    setSelected(null);
    button?.focus({ preventScroll: true });
  };
  const resetHistory = () => { history.current = { past: [], future: [] }; refreshHistory(); };
  const save = () => {
    try {
      const validated = layoutSchema.parse(layout);
      localStorage.setItem(storageKey, JSON.stringify(validated));
      resetHistory(); setSaved({ layout: validated, error: false, stored: true }); setEditing(false); setSelected(null); setSaveError(false);
    } catch { setSaveError(true); }
  };
  const patchWidget = (patch: Partial<DashboardWidget>) => changeLayout((current) => ({ ...current, groups: current.groups.map((group) => ({ ...group, widgets: group.widgets.map((widget) => widget.id === selected ? { ...widget, ...patch, canvas: integrated && patch.width ? { ...sceneRects(current)[widget.id], width: patch.width === "full" ? 1284 : 416 } : widget.canvas } : widget) })) }));
  const addWidget = (kind: WidgetKind) => {
    const widget = createWidget(kind);
    const group = layout.groups.find((group) => group.widgets.length < 24);
    if (!group) return;
    setEditing(true); setLibrary(false); setSelected(widget.id);
    changeLayout((current) => ({ ...current, groups: current.groups.map((item) => item.id === group.id ? { ...item, widgets: [...item.widgets, widget] } : item) }));
  };
  const move = (direction: -1 | 1) => {
    const group = layout.groups.find((group) => group.widgets.some((widget) => widget.id === selected));
    if (!group || !selected) return;
    const index = group.widgets.findIndex((widget) => widget.id === selected);
    const beforeId = direction === -1 ? group.widgets[index - 1]?.id : group.widgets[index + 2]?.id;
    changeLayout((current) => moveWidget(current, selected, group.id, beforeId));
  };
  const duplicate = () => {
    if (!selectedWidget) return;
    const copy = { ...selectedWidget, canvas: selectedWidget.canvas ? { ...selectedWidget.canvas, x: selectedWidget.canvas.x + 24, y: selectedWidget.canvas.y + 24 } : undefined, id: crypto.randomUUID(), title: `${selectedWidget.title || t(`simulation.studio.metric.${selectedWidget.metric}`)} · ${t("simulation.studio.copy")}`.slice(0, 120) };
    changeLayout((current) => ({ ...current, groups: current.groups.map((group) => group.widgets.some((widget) => widget.id === selected) ? { ...group, widgets: [...group.widgets, copy] } : group) }));
    setSelected(copy.id);
  };
  const remove = () => {
    changeLayout((current) => ({ ...current, groups: current.groups.map((group) => ({ ...group, widgets: group.widgets.filter((widget) => widget.id !== selected) })) }));
    setSelected(null);
  };
  const processGroupId = layout.groups.some((group) => group.id === layout.process.groupId) ? layout.process.groupId : layout.groups[0].id;
  const processBeforeId = layout.process.beforeId === "__first__" ? layout.groups.find((group) => group.id === processGroupId)?.widgets[0]?.id ?? null : layout.process.beforeId;
  const updateProcess = (patch: Partial<DashboardLayout["process"]>) => changeLayout((current) => ({ ...current, process: { ...current.process, ...patch } }));
  const moveProcess = (direction: -1 | 1) => {
    const group = layout.groups.find((item) => item.id === processGroupId)!;
    const current = group.widgets.findIndex((item) => item.id === processBeforeId);
    const index = current < 0 ? group.widgets.length : current;
    const next = Math.max(0, Math.min(group.widgets.length, index + direction));
    updateProcess({ groupId: group.id, beforeId: group.widgets[next]?.id ?? null });
  };
  const processTile = process && <article className={`sim-process-tile ${layout.process.width === "full" ? "is-full" : ""}`} data-process-tile
    style={{ "--process-height": `${layout.process.height}px` } as React.CSSProperties}
    onDragOver={(event) => { if (editing && event.dataTransfer.types.includes(DRAG_TYPE)) event.preventDefault(); }}
    onDrop={(event) => { if (!editing) return; const id = event.dataTransfer.getData(DRAG_TYPE); if (!id || id === "__process__") return; event.preventDefault(); changeLayout((current) => moveWidget(current, id, processGroupId, current.process.beforeId ?? undefined)); }}>
    <header className="sim-process-tile-header"><div className="sim-process-caption">
      {editing && !integrated && <button type="button" className="sim-drag-handle" draggable aria-label={t("simulation.unified.moveProcess")} onDragStart={(event) => { event.dataTransfer.setData(DRAG_TYPE, "__process__"); event.dataTransfer.effectAllowed = "move"; }}><GripVertical aria-hidden className="size-4" /></button>}
      <Workflow aria-hidden className="size-4" /><h3>{t("simulation.unified.process")}</h3><span>{processScope}</span>
    </div><div className="sim-process-size-controls">
      {editing && !integrated && <><Button size="icon" variant="ghost" onClick={() => moveProcess(-1)} aria-label={t("simulation.unified.processEarlier")}><ArrowUp aria-hidden className="size-4" /></Button><Button size="icon" variant="ghost" onClick={() => moveProcess(1)} aria-label={t("simulation.unified.processLater")}><ArrowDown aria-hidden className="size-4" /></Button>
        <label><span className="sr-only">{t("simulation.unified.processSection")}</span><select aria-label={t("simulation.unified.processSection")} value={processGroupId} onChange={(event) => updateProcess({ groupId: event.target.value, beforeId: null })}>{layout.groups.map((group, i) => <option key={group.id} value={group.id}>{group.title || t("simulation.studio.sectionNumber", { n: i + 1 })}</option>)}</select></label>
        <label><span className="sr-only">{t("simulation.unified.processHeight")}</span><select aria-label={t("simulation.unified.processHeight")} value={layout.process.height} onChange={(event) => updateProcess({ height: Number(event.target.value) })}>{[340, 440, 560, 720].map((height) => <option value={height} key={height}>{height}px</option>)}</select></label></>}
      {!integrated && <Button size="icon" variant="ghost" onClick={() => { if (!editing) setEditing(true); updateProcess({ width: layout.process.width === "full" ? "half" : "full" }); }} aria-label={t(layout.process.width === "full" ? "simulation.unified.reduceProcess" : "simulation.unified.expandProcess")}>
        {layout.process.width === "full" ? <Shrink aria-hidden className="size-4" /> : <Expand aria-hidden className="size-4" />}
      </Button>}</div></header>{process}
  </article>;
  const inspector = editing && selectedWidget && (!integrated || inspectedWidgetId === selected) && <div className="sim-inspector-slot" ref={editorRef}><WidgetInspector widget={selectedWidget} layout={layout} engine={engine} activityId={activityId} summary={final ? run.summary : undefined} onChange={patchWidget} onClose={closeInspector} onDelete={remove} onDuplicate={duplicate} onMove={move} onGroup={(id) => changeLayout((current) => moveWidget(current, selectedWidget.id, id))} /></div>;
  if (!frame) return <div />;

  const rects = sceneRects(layout);
  const place = (id: string, rect: CanvasRect) => changeLayout(current => id === PROCESS_ID
    ? { ...current, process: { ...current.process, canvas: rect } }
    : { ...current, groups: current.groups.map(group => ({ ...group, widgets: group.widgets.map(widget => widget.id === id ? { ...widget, canvas: rect } : widget) })) });
  const sceneObjects: SceneObject[] = [
    ...(processTile ? [{ id: PROCESS_ID, title: t("simulation.unified.process"), rect: rects[PROCESS_ID], content: processTile }] : []),
    ...layout.groups.flatMap(group => group.widgets.map(widget => {
      const title = widget.title || t(`simulation.studio.metric.${widget.metric}`);
      const data = widgetData(engine, frame, widget.metric, widget.activityId || (widget.followFilter ? activityId : "all"));
      return { id: widget.id, title, rect: rects[widget.id], content: <article className={`sim-widget ${widget.width === "full" ? "is-full" : ""} ${editing ? "is-editing" : ""} ${selected === widget.id ? "is-selected" : ""}`} data-widget-id={widget.id}>
        <header className="sim-widget-heading"><div><h4>{title}</h4><p>{t(data.filtered ? "simulation.studio.filteredScope" : "simulation.studio.globalScope")}</p></div>
          {editing && <Button id={`configure-${widget.id}`} size="icon" variant="ghost" onClick={() => setSelected(widget.id)} aria-label={t("simulation.studio.configure", { title })}><Settings2 aria-hidden className="size-4" /></Button>}
        </header><WidgetView widget={widget} engine={engine} frame={frame} activityId={activityId} unavailable={unavailable} loading={artifactLoading} summary={final ? run.summary : undefined} /></article> };
    })),
  ];
  const kpis = ["active", "queued", "completed", "throughput", "cycle", "cost"] as const;
  return <div className={`sim-dashboard-workspace ${integrated ? "is-integrated" : ""}`} data-history-revision={historyCounts.past + historyCounts.future}>
    <header className="sim-dashboard-header"><div hidden={integrated}><p className="sim-eyebrow">{run.scenario_name}</p><h2>{t("simulation.studio.dashboardTitle")}</h2><p className="sim-help">{t("simulation.studio.dashboardHint")}</p></div>
      <div className="sim-dashboard-actions">
        {editing && <><Button size="icon" variant="ghost" disabled={!historyCounts.past} onClick={() => undo()} aria-label={t("simulation.unified.undo")}><Undo2 aria-hidden className="size-4" /></Button><Button size="icon" variant="ghost" disabled={!historyCounts.future} onClick={() => undo(true)} aria-label={t("simulation.unified.redo")}><Redo2 aria-hidden className="size-4" /></Button></>}
        {editing ? <><Button size="sm" variant="ghost" onClick={() => { resetHistory(); setLayout(saved.layout); setEditing(false); setSelected(null); setSaveError(false); }}>{t("simulation.studio.cancel")}</Button><Button size="sm" onClick={save}><Check aria-hidden className="size-4" />{t("simulation.studio.save")}</Button></>
          : <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Settings2 aria-hidden className="size-4" />{t("simulation.studio.edit")}</Button>}
        <Button size="sm" variant="outline" onClick={() => setLibrary(true)} disabled={layout.groups.every((group) => group.widgets.length >= 24)}><Plus aria-hidden className="size-4" />{t("simulation.studio.addWidget")}</Button>
      </div>
    </header>
    {!integrated && <div className="sim-transport-surface"><TransportBar engine={engine} /></div>}
    <div className="sim-dashboard-toolbar"><span className="sim-scope-badge"><span aria-hidden />{processScope ?? t("simulation.studio.currentTime")}</span>
      <label className="sim-filter"><span>{t("simulation.studio.activityFilter")}</span><select aria-label={t("simulation.studio.activityFilter")} value={activityId} onChange={(event) => setActivityId(event.target.value)}><option value="all">{t("simulation.studio.allActivities")}</option>{Object.entries(engine.payload.elements).map(([id, element]) => <option key={id} value={id}>{element.name}</option>)}</select></label>
      {activityId !== "all" && <Button variant="ghost" size="sm" onClick={() => setActivityId("all")}><X aria-hidden className="size-3" />{t("simulation.studio.clearFilter")}</Button>}
      <span className="sim-help sim-storage-status" role="status">{t(editing ? "simulation.studio.unsaved" : saved.stored ? "simulation.studio.savedDevice" : "simulation.studio.defaultLayout")}</span>
    </div>
    {(saved.error || saveError) && <p role="alert" className="sim-save-error">{t(saveError ? "simulation.studio.saveError" : "simulation.studio.restoreError")}</p>}
    <section className="sim-kpi-strip" aria-label={t(final ? "simulation.scene.finalScope" : "simulation.studio.currentMetrics")}>{kpis.map((metric) => {
      const data = widgetData(engine, frame, metric, "all", final ? run.summary : undefined);
      if (unavailable && !["cycle", "cost", "completed", "throughput"].includes(metric)) data.value = null;
      return <StatTile key={metric} className="sim-kpi" label={t(`simulation.studio.metric.${metric}`)} value={formatMetric(data.value, data.unit, lang)} hint={final ? t("simulation.scene.finalScope") : t(metric === "cycle" ? "simulation.studio.closedCases" : "simulation.studio.globalScope")} tone={metric === "queued" && (data.value ?? 0) > 0 ? "warning" : "neutral"} />;
    })}</section>
    {integrated ? <><AnalyticalCanvas objects={sceneObjects} editing={editing} onPlace={place} /><div className="sim-scene-sections" aria-label={t("simulation.scene.groups")}>{layout.groups.map((group, index) => <section key={group.id} className="sim-widget-section"><header className="sim-section-header">{editing ? <label className="sim-section-title"><span className="sr-only">{t("simulation.studio.sectionTitle")}</span><input value={group.title} maxLength={120} placeholder={t("simulation.studio.sectionNumber", { n: index + 1 })} onChange={event => changeLayout(current => ({ ...current, groups: current.groups.map(item => item.id === group.id ? { ...item, title: event.target.value } : item) }))} /></label> : <h3>{group.title || t("simulation.studio.sectionNumber", { n: index + 1 })}</h3>}{editing && !group.widgets.length && layout.groups.length > 1 && <Button size="sm" variant="ghost" onClick={() => changeLayout(current => ({ ...current, groups: current.groups.filter(item => item.id !== group.id) }))}>{t("simulation.studio.removeSection")}</Button>}</header></section>)}{editing && <div className="sim-layout-actions"><Button size="sm" variant="outline" disabled={layout.groups.length >= 12} onClick={() => changeLayout(current => ({ ...current, groups: [...current.groups, { id: crypto.randomUUID(), title: "", widgets: [] }] }))}><Plus aria-hidden className="size-4" />{t("simulation.studio.addSection")}</Button><Button size="sm" variant="ghost" onClick={() => { changeLayout(defaultLayout()); setSelected(null); }}><RotateCcw aria-hidden className="size-4" />{t("simulation.studio.reset")}</Button></div>}<details className="sim-final-results"><summary>{t("simulation.studio.finalResults")}</summary><p className="sim-help">{t("simulation.studio.finalHint")}</p><div className="sim-final-grid"><StatTile label={t("simulation.results.cycleTime")} value={run.summary ? formatDuration(run.summary.cycle.avg, lang) : "—"} /><StatTile label={t("simulation.results.costPerCase")} value={run.summary ? formatCurrency(run.summary.cost.perCase, lang) : "—"} /><StatTile label={t("simulation.dashboard.peakQueue")} value={engine.payload.series.global.queued?.length ? String(Math.max(...engine.payload.series.global.queued)) : "—"} /></div></details></div>{inspectorHost && inspector && createPortal(inspector, inspectorHost)}</> : <div className={`sim-dashboard-body ${editing && selectedWidget && !integrated ? "has-inspector" : ""}`}>
      <div className="sim-dashboard-sections">
        {layout.groups.map((group, index) => <section key={group.id} className="sim-widget-section" aria-label={group.title || t("simulation.studio.sectionNumber", { n: index + 1 })}>
          <header className="sim-section-header">
            {editing ? <label className="sim-section-title"><span className="sr-only">{t("simulation.studio.sectionTitle")}</span><input maxLength={120} value={group.title} placeholder={t("simulation.studio.sectionNumber", { n: index + 1 })} onChange={(event) => changeLayout((current) => ({ ...current, groups: current.groups.map((item) => item.id === group.id ? { ...item, title: event.target.value } : item) }))} /></label> : <h3>{group.title || t("simulation.studio.sectionNumber", { n: index + 1 })}</h3>}
            {editing && group.widgets.length === 0 && layout.groups.length > 1 && <Button variant="ghost" size="sm" onClick={() => changeLayout((current) => ({ ...current, groups: current.groups.filter((item) => item.id !== group.id) }))}>{t("simulation.studio.removeSection")}</Button>}
          </header>
          <div className="sim-widget-grid">
            {group.widgets.map((widget) => {
              const data = widgetData(engine, frame, widget.metric, widget.activityId || (widget.followFilter ? activityId : "all"));
              const title = widget.title || t(`simulation.studio.metric.${widget.metric}`);
              const beforeProcess = process && group.id === processGroupId && processBeforeId === widget.id;
              return <React.Fragment key={widget.id}>{beforeProcess && processTile}<article className={`sim-widget ${widget.width === "full" ? "is-full" : ""} ${editing ? "is-editing" : ""} ${selected === widget.id ? "is-selected" : ""}`} data-widget-id={widget.id}
                onDragOver={(event) => { if (editing && event.dataTransfer.types.includes(DRAG_TYPE)) event.preventDefault(); }}
                onDrop={(event) => { if (!editing || !event.dataTransfer.types.includes(DRAG_TYPE)) return; event.preventDefault(); const id = event.dataTransfer.getData(DRAG_TYPE); if (id === "__process__") updateProcess({ groupId: group.id, beforeId: widget.id }); else changeLayout((current) => moveWidget(current, id, group.id, widget.id)); }}>
                <header className="sim-widget-heading">
                  {editing && <button type="button" className="sim-drag-handle" draggable aria-label={t("simulation.studio.drag", { title })} onDragStart={(event) => { event.dataTransfer.setData(DRAG_TYPE, widget.id); event.dataTransfer.effectAllowed = "move"; }} onClick={() => setSelected(widget.id)}><GripVertical aria-hidden className="size-4" /></button>}
                  <div className="min-w-0"><h4>{title}</h4><p>{t(`simulation.studio.kind.${widget.kind}`)} · {t(data.filtered ? "simulation.studio.filteredScope" : "simulation.studio.globalScope")}</p></div>
                  {editing && <Button id={`configure-${widget.id}`} size="icon" variant="ghost" onClick={() => setSelected(widget.id)} aria-label={t("simulation.studio.configure", { title })}><Settings2 aria-hidden className="size-4" /></Button>}
                </header>
                <WidgetView widget={widget} engine={engine} frame={frame} activityId={activityId} unavailable={unavailable} loading={artifactLoading} summary={final ? run.summary : undefined} />
              </article></React.Fragment>;
            })}
            {process && group.id === processGroupId && !group.widgets.some((widget) => widget.id === processBeforeId) && processTile}
            {group.widgets.length === 0 && <p className="sim-empty-section">{t("simulation.studio.emptySection")}</p>}
          </div>
        </section>)}
        {editing && <div className="sim-layout-actions"><Button variant="outline" size="sm" disabled={layout.groups.length >= 12} onClick={() => changeLayout((current) => ({ ...current, groups: [...current.groups, { id: crypto.randomUUID(), title: "", widgets: [] }] }))}><Plus aria-hidden className="size-4" />{t("simulation.studio.addSection")}</Button><Button variant="ghost" size="sm" onClick={() => { changeLayout(defaultLayout()); setSelected(null); }}><RotateCcw aria-hidden className="size-4" />{t("simulation.studio.reset")}</Button></div>}
        <details className="sim-final-results"><summary>{t("simulation.studio.finalResults")}</summary><p className="sim-help">{t("simulation.studio.finalHint")}</p><div className="sim-final-grid"><StatTile label={t("simulation.results.cycleTime")} value={run.summary ? formatDuration(run.summary.cycle.avg, lang) : "—"} /><StatTile label={t("simulation.results.costPerCase")} value={run.summary ? formatCurrency(run.summary.cost.perCase, lang) : "—"} /><StatTile label={t("simulation.dashboard.peakQueue")} value={engine.payload.series.global.queued?.length ? String(Math.max(...engine.payload.series.global.queued)) : "—"} /></div></details>
      </div>
      {integrated ? inspectorHost && inspector && createPortal(inspector, inspectorHost) : inspector}
    </div>}
    <Dialog open={library} onOpenChange={setLibrary}><DialogContent onCloseAutoFocus={(event) => { if (selected) { event.preventDefault(); editorRef.current?.querySelector<HTMLInputElement>("input")?.focus({ preventScroll: true }); } }} className="max-h-[85vh] overflow-y-auto sm:max-w-xl"><DialogTitle>{t("simulation.studio.libraryTitle")}</DialogTitle><DialogDescription>{t("simulation.studio.libraryHint")}</DialogDescription><div className="sim-library-questions"><p>{t("simulation.unified.startQuestion")}</p>{(["activityQueued", "resourceBusy", "throughput"] as const).map((metric) => <Button key={metric} variant="outline" onClick={() => { const widget = { ...createWidget(metric === "throughput" ? "line" : "bar"), metric }; const group = layout.groups.find((item) => item.widgets.length < 24); if (!group) return; setEditing(true); setLibrary(false); changeLayout((current) => ({ ...current, groups: current.groups.map((item) => item.id === group.id ? { ...item, widgets: [...item.widgets, widget] } : item) })); setSelected(widget.id); }}>{t(`simulation.unified.question.${metric}`)}</Button>)}</div><div className="sim-widget-library">{KINDS.map((kind) => <button type="button" key={kind} onClick={() => addWidget(kind)}><ChartNoAxesCombined aria-hidden className="size-5" /><strong>{t(`simulation.studio.kind.${kind}`)}</strong><span>{t(`simulation.studio.kindHint.${kind}`)}</span></button>)}</div></DialogContent></Dialog>
  </div>;
}
