import React from "react";
import { useTranslation } from "react-i18next";
import { Copy, Trash2, X, ArrowUp, ArrowDown } from "lucide-react";

import { Button } from "@/ui/button";
import { useReplayFrame } from "../replay/useReplay";
import type { ReplayEngine } from "../replay/replayEngine";
import { interpolateText } from "./dashboardExpressions";
import { KINDS, METRICS, UNITS, widgetData, type DashboardWidget, type DashboardLayout, type Metric, type WidgetKind } from "./dashboardModel";

export function WidgetInspector({ widget, layout, engine, activityId, onChange, onClose, onDelete, onDuplicate, onMove, onGroup }: {
  widget: DashboardWidget; layout: DashboardLayout; engine: ReplayEngine; activityId: string;
  onChange: (patch: Partial<DashboardWidget>) => void; onClose: () => void; onDelete: () => void; onDuplicate: () => void;
  onMove: (direction: -1 | 1) => void; onGroup: (id: string) => void;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language.startsWith("it") ? "it" : "en";
  const frame = useReplayFrame(engine);
  const group = layout.groups.find((item) => item.widgets.some((item) => item.id === widget.id))!;
  const index = group.widgets.findIndex((item) => item.id === widget.id);
  const value = frame ? widgetData(engine, frame, widget.metric, widget.followFilter ? activityId : "all").value : null;
  const expression = interpolateText(widget.text, { metric: value === null ? 0 : value * (UNITS[widget.metric] === "duration" ? 1000 : 1), total: frame ? frame.global.activeCases + frame.global.completedCases : 0, currentTime: frame?.global.clockMs ?? 0 }, lang);
  const id = React.useId();
  const field = (name: string, control: React.ReactElement<{ "aria-label"?: string }>) => <label className="sim-field"><span>{t(`simulation.studio.${name}`)}</span>{React.cloneElement(control, { "aria-label": t(`simulation.studio.${name}`) })}</label>;

  return <aside className="sim-widget-inspector" aria-label={t("simulation.studio.inspector")}>
    <header><div><p className="sim-eyebrow">{t("simulation.studio.settings")}</p><h3>{t("simulation.studio.inspector")}</h3></div><Button size="icon" variant="ghost" onClick={onClose} aria-label={t("simulation.studio.closeInspector")}><X aria-hidden className="size-4" /></Button></header>
    <div className="sim-inspector-body">
      <details open><summary>{t("simulation.studio.general")}</summary><div className="sim-inspector-fields">
        {field("title", <input value={widget.title} maxLength={120} placeholder={t(`simulation.studio.metric.${widget.metric}`)} onChange={(event) => onChange({ title: event.target.value })} />)}
        {field("type", <select value={widget.kind} onChange={(event) => onChange({ kind: event.target.value as WidgetKind })}>{KINDS.map((kind) => <option key={kind} value={kind}>{t(`simulation.studio.kind.${kind}`)}</option>)}</select>)}
        {field("section", <select value={group.id} onChange={(event) => onGroup(event.target.value)}>{layout.groups.map((item, i) => <option value={item.id} key={item.id}>{item.title || t("simulation.studio.sectionNumber", { n: i + 1 })}</option>)}</select>)}
        {field("width", <select value={widget.width} onChange={(event) => onChange({ width: event.target.value as DashboardWidget["width"] })}><option value="half">{t("simulation.studio.half")}</option><option value="full">{t("simulation.studio.full")}</option></select>)}
      </div></details>
      <details open><summary>{t("simulation.studio.metricLabel")}</summary><div className="sim-inspector-fields">
        {field("metricLabel", <select value={widget.metric} onChange={(event) => onChange({ metric: event.target.value as Metric })}>{METRICS.map((metric) => <option key={metric} value={metric}>{t(`simulation.studio.metric.${metric}`)}</option>)}</select>)}
        {widget.kind === "gauge" && field("targetLabel", <input type="number" min="0.01" step="any" value={widget.target} onChange={(event) => { const target = Number(event.target.value); if (Number.isFinite(target) && target > 0) onChange({ target }); }} />)}
        <p className="sim-help">{t(widget.metric === "cycle" ? "simulation.studio.cycleHelp" : "simulation.studio.scopeHelp")}</p>
      </div></details>
      <details><summary>{t("simulation.studio.filters")}</summary><div className="sim-inspector-fields">
        <label className="sim-checkbox"><input type="checkbox" checked={widget.followFilter} onChange={(event) => onChange({ followFilter: event.target.checked })} />{t("simulation.studio.followFilter")}</label>
        <p className="sim-help">{t("simulation.studio.filterHelp")}</p>
      </div></details>
      <details><summary>{t("simulation.studio.labelsStyle")}</summary><div className="sim-inspector-fields">
        <label className="sim-checkbox"><input type="checkbox" checked={widget.showLabels} onChange={(event) => onChange({ showLabels: event.target.checked })} />{t("simulation.studio.showLabels")}</label>
        {field("color", <select value={widget.color} onChange={(event) => onChange({ color: event.target.value as DashboardWidget["color"] })}>{["blue", "amber", "teal", "violet"].map((color) => <option key={color} value={color}>{t(`simulation.studio.colors.${color}`)}</option>)}</select>)}
      </div></details>
      {widget.kind === "text" && <details open><summary>{t("simulation.studio.markdown")}</summary><div className="sim-inspector-fields">
        <label className="sim-field"><span>{t("simulation.studio.text")}</span><textarea aria-label={t("simulation.studio.text")} aria-describedby={`${id}-expression`} aria-invalid={!expression.valid} value={widget.text} maxLength={4000} rows={6} onChange={(event) => onChange({ text: event.target.value })} /></label>
        <p id={`${id}-expression`} className={expression.valid ? "sim-help" : "text-sm text-destructive"}>{t(expression.valid ? "simulation.studio.expressionHelp" : "simulation.studio.invalidExpression")}</p>
        <p className="sim-expression-preview">{expression.valid ? expression.text : "—"}</p>
        <Button variant="outline" size="sm" onClick={() => onChange({ text: widget.text + (UNITS[widget.metric] === "duration" ? " ${formatDuration(metric)}" : " ${round(metric, 1)}") })}>{t("simulation.studio.insertExpression")}</Button>
      </div></details>}
    </div>
    <footer><div className="flex gap-1"><Button size="icon" variant="outline" disabled={index === 0} onClick={() => onMove(-1)} aria-label={t("simulation.studio.moveUp")}><ArrowUp aria-hidden className="size-4" /></Button><Button size="icon" variant="outline" disabled={index === group.widgets.length - 1} onClick={() => onMove(1)} aria-label={t("simulation.studio.moveDown")}><ArrowDown aria-hidden className="size-4" /></Button></div>
      <Button size="icon" variant="outline" disabled={group.widgets.length >= 24} onClick={onDuplicate} aria-label={t("simulation.studio.duplicate")}><Copy aria-hidden className="size-4" /></Button><Button size="icon" variant="ghost" onClick={onDelete} aria-label={t("simulation.studio.remove")}><Trash2 aria-hidden className="size-4" /></Button>
    </footer>
  </aside>;
}
