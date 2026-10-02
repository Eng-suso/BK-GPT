import React from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { GripVertical, Minus, Plus, Trash2, Settings2 } from "lucide-react";
import { z } from "zod";

import { Button } from "@/ui/button";
import type { ReplayEngine, ReplayFrame } from "../replay/replayEngine";
import { useSimulationSection } from "../useSimulationSection";
import { KINDS, METRICS, createWidget, widgetSchema, defaultLayout, type DashboardWidget } from "../dashboard/dashboardModel";
import { WidgetInspector } from "../dashboard/WidgetInspector";
import { WidgetView } from "../dashboard/WidgetView";
import { svc, type BpmnViewer, type BpmnOverlays, type BpmnElementRegistry } from "./bpmnViewer";

const pinsSchema = z.array(z.object({
  elementId: z.string().min(1).max(200),
  widget: widgetSchema,
  x: z.number().finite().min(-2000).max(2000),
  y: z.number().finite().min(-2000).max(2000),
  width: z.number().min(220).max(440),
})).max(12).refine((pins) => new Set(pins.map((pin) => pin.widget.id)).size === pins.length);
type Pin = z.infer<typeof pinsSchema>[number];

/** Each host belongs to its own overlay; replay badges must not clear these. */
function PinnedWidget({ pin, viewer, engine, frame, onChange, onRemove, onConfigure }: {
  pin: Pin; viewer: BpmnViewer; engine: ReplayEngine; frame: ReplayFrame;
  onChange: (patch: Partial<Pin>) => void; onRemove: () => void; onConfigure?: () => void;
}): React.JSX.Element | null {
  const { t } = useTranslation("process");
  const [host] = React.useState(() => document.createElement("div"));
  const drag = React.useRef<{ x: number; y: number; dx: number; dy: number } | null>(null);
  React.useEffect(() => {
    const overlays = svc<BpmnOverlays>(viewer, "overlays");
    if (!overlays || !svc<BpmnElementRegistry>(viewer, "elementRegistry")?.get(pin.elementId)) return;
    const id = overlays.add(pin.elementId, { position: { top: 0, left: 0 }, html: host, scale: false });
    return () => { try { overlays.remove(id); } catch { /* Viewer may already be destroyed. */ } };
  }, [viewer, pin.elementId, host]);
  const patchWidget = (patch: Partial<DashboardWidget>) => onChange({ widget: { ...pin.widget, ...patch } });
  const position = (x: number, y: number) => onChange({ x: Math.max(-2000, Math.min(2000, x)), y: Math.max(-2000, Math.min(2000, y)) });
  const name = engine.payload.elements[pin.elementId]?.name ?? pin.elementId;
  return createPortal(<article className="sim-canvas-widget sim-widget" style={{ width: pin.width, transform: `translate(${pin.x}px, ${pin.y}px)` }} data-canvas-widget={pin.widget.id} aria-label={t("simulation.studio.canvasAnalysis", { name })} onPointerDown={(event) => event.stopPropagation()} onWheel={(event) => event.stopPropagation()}>
    <header className="sim-canvas-widget-heading">
      <button type="button" className="sim-canvas-drag" aria-label={t("simulation.studio.moveCanvasWidget")} title={t("simulation.studio.moveCanvasHelp")}
        onKeyDown={(event) => {
          const delta = event.shiftKey ? 40 : 10;
          const offsets: Record<string, [number, number]> = { ArrowLeft: [-delta, 0], ArrowRight: [delta, 0], ArrowUp: [0, -delta], ArrowDown: [0, delta] };
          if (offsets[event.key]) { event.preventDefault(); position(pin.x + offsets[event.key][0], pin.y + offsets[event.key][1]); }
        }}
        onPointerDown={(event) => { event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId); drag.current = { x: event.clientX, y: event.clientY, dx: 0, dy: 0 }; }}
        onPointerMove={(event) => { if (!drag.current) return; drag.current.dx = event.clientX - drag.current.x; drag.current.dy = event.clientY - drag.current.y; (event.currentTarget.closest("article") as HTMLElement).style.transform = `translate(${pin.x + drag.current.dx}px, ${pin.y + drag.current.dy}px)`; }}
        onPointerUp={() => { if (!drag.current) return; position(pin.x + drag.current.dx, pin.y + drag.current.dy); drag.current = null; }}
        onPointerCancel={(event) => { drag.current = null; (event.currentTarget.closest("article") as HTMLElement).style.transform = `translate(${pin.x}px, ${pin.y}px)`; }}
      ><GripVertical aria-hidden className="size-4" /></button>
      <div className="min-w-0 flex-1"><h3>{pin.widget.title || t(`simulation.studio.metric.${pin.widget.metric}`)}</h3><p>{pin.widget.metric.startsWith("activity") ? name : t("simulation.studio.globalScope")}</p></div>
      {onConfigure && <Button id={`configure-pin-${pin.widget.id}`} size="icon" variant="ghost" onClick={onConfigure} aria-label={t("simulation.studio.configure", { title: pin.widget.title || t(`simulation.studio.metric.${pin.widget.metric}`) })}><Settings2 aria-hidden className="size-4" /></Button>}
      <Button size="icon" variant="ghost" onClick={onRemove} aria-label={t("simulation.studio.remove")}><Trash2 aria-hidden className="size-4" /></Button>
    </header>
    <WidgetView widget={pin.widget} engine={engine} frame={frame} activityId={pin.elementId} />
    {!onConfigure && <details className="sim-canvas-settings"><summary>{t("simulation.studio.settings")}</summary>
      <label className="sim-field"><span>{t("simulation.studio.title")}</span><input aria-label={t("simulation.studio.title")} value={pin.widget.title} maxLength={120} onChange={(event) => patchWidget({ title: event.target.value })} /></label>
      <label className="sim-field"><span>{t("simulation.studio.type")}</span><select aria-label={t("simulation.studio.type")} value={pin.widget.kind} onChange={(event) => patchWidget({ kind: event.target.value as DashboardWidget["kind"] })}>{KINDS.map((kind) => <option value={kind} key={kind}>{t(`simulation.studio.kind.${kind}`)}</option>)}</select></label>
      <label className="sim-field"><span>{t("simulation.studio.metricLabel")}</span><select aria-label={t("simulation.studio.metricLabel")} value={pin.widget.metric} onChange={(event) => patchWidget({ metric: event.target.value as DashboardWidget["metric"] })}>{METRICS.map((metric) => <option value={metric} key={metric}>{t(`simulation.studio.metric.${metric}`)}</option>)}</select></label>
      <label className="sim-field"><span>{t("simulation.studio.metricExpression")}</span><input aria-label={t("simulation.studio.metricExpression")} value={pin.widget.metricExpression} maxLength={512} onChange={(event) => patchWidget({ metricExpression: event.target.value })} /></label>
      <p className="sim-help">{t("simulation.studio.metricExpressionHelp")}</p>
      {pin.widget.kind === "text" && <label className="sim-field"><span>{t("simulation.studio.text")}</span><textarea aria-label={t("simulation.studio.text")} rows={3} maxLength={4000} value={pin.widget.text} onChange={(event) => patchWidget({ text: event.target.value })} /></label>}
      {pin.widget.kind === "gauge" && <label className="sim-field"><span>{t("simulation.studio.targetLabel")}</span><input aria-label={t("simulation.studio.targetLabel")} type="number" min="0.01" value={pin.widget.target} onChange={(event) => { const target = Number(event.target.value); if (Number.isFinite(target) && target > 0) patchWidget({ target }); }} /></label>}
      <div className="flex items-center justify-between"><span className="sim-help">{t("simulation.studio.width")}</span><div className="flex gap-1"><Button size="icon" variant="outline" disabled={pin.width <= 220} onClick={() => onChange({ width: Math.max(220, pin.width - 40) })} aria-label={t("simulation.studio.narrowWidget")}><Minus aria-hidden className="size-4" /></Button><Button size="icon" variant="outline" disabled={pin.width >= 440} onClick={() => onChange({ width: Math.min(440, pin.width + 40) })} aria-label={t("simulation.studio.widenWidget")}><Plus aria-hidden className="size-4" /></Button></div></div>
      <p className="sim-help">{t("simulation.studio.moveCanvasHelp")}</p>
    </details>}
  </article>, host);
}

export function CanvasAnalytics({ viewer, engine, frame, selectedId, visible, onVisibilityChange, inspectorHost }: {
  viewer: BpmnViewer | null; engine: ReplayEngine; frame: ReplayFrame; selectedId: string | null; visible: boolean;
  onVisibilityChange: (visible: boolean) => void; inspectorHost?: HTMLElement | null;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const { projectId, processId, panel, inspectedWidgetId, inspectWidget } = useSimulationSection();
  const key = `delir:simulation:canvas:${projectId}:${processId}`;
  const [stored] = React.useState(() => {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return { pins: [] as Pin[], error: false };
      const parsed = pinsSchema.safeParse(JSON.parse(raw));
      return { pins: parsed.success ? parsed.data : [], error: !parsed.success };
    } catch { return { pins: [] as Pin[], error: true }; }
  });
  const [pins, setPins] = React.useState<Pin[]>(stored.pins);
  const [error, setError] = React.useState<"restore" | "save" | null>(stored.error ? "restore" : null);
  const save = (next: Pin[]) => {
    setPins(next);
    try { localStorage.setItem(key, JSON.stringify(pinsSchema.parse(next))); setError(null); }
    catch { setError("save"); }
  };
  const selectedPin = panel === "widget" ? pins.find((pin) => `pin:${pin.widget.id}` === inspectedWidgetId) : undefined;
  const inspectorRef = React.useRef<HTMLDivElement>(null);
  const selectedPinId = selectedPin?.widget.id;
  React.useEffect(() => {
    if (selectedPinId) inspectorRef.current?.querySelector<HTMLInputElement>("input")?.focus({ preventScroll: true });
  }, [selectedPinId, inspectorHost]);
  const closeInspector = () => {
    const opener = document.getElementById(`configure-pin-${selectedPin?.widget.id}`);
    inspectWidget?.(null); opener?.focus({ preventScroll: true });
  };
  const canAdd = Boolean(selectedId && engine.payload.elements[selectedId] && pins.length < 12);
  return <>
    <div className="sim-canvas-analysis-actions">
      <Button size="sm" variant="outline" disabled={!canAdd} onClick={() => {
        if (!selectedId) return;
        const widget = { ...createWidget("kpi"), metric: "activityQueued" as const, activityId: selectedId };
        save([...pins, { elementId: selectedId, widget, x: 0, y: 110, width: 260 }]);
        onVisibilityChange(true);
      }}><Plus aria-hidden className="size-4" />{t("simulation.studio.addCanvasAnalysis")}</Button>
      {pins.length > 0 && <Button size="sm" variant="ghost" onClick={() => save(pins.map((pin, index) => ({ ...pin, x: (index % 2) * 20, y: 110 + (index % 3) * 20 })))}>{t("simulation.studio.repositionCharts")}</Button>}
      <span className="sim-help">{t(canAdd ? "simulation.studio.canvasLocal" : "simulation.studio.selectActivity")}</span>
      {error && <span role="alert" className="text-xs text-destructive">{t(error === "restore" ? "simulation.studio.restoreError" : "simulation.studio.saveError")}</span>}
    </div>
    {viewer && visible && pins.map((pin) => <PinnedWidget key={pin.widget.id} pin={pin} viewer={viewer} engine={engine} frame={frame}
      onConfigure={inspectorHost && inspectWidget ? () => inspectWidget(`pin:${pin.widget.id}`) : undefined}
      onChange={(patch) => save(pins.map((item) => item.widget.id === pin.widget.id ? { ...item, ...patch } : item))}
      onRemove={() => save(pins.filter((item) => item.widget.id !== pin.widget.id))} />)}
    {inspectorHost && selectedPin && createPortal(<div ref={inspectorRef} className="sim-inspector-slot"><WidgetInspector pinned widget={selectedPin.widget}
      layout={{ ...defaultLayout(), groups: [{ id: "pins", title: "", widgets: pins.map((pin) => pin.widget) }] }} engine={engine} activityId={selectedPin.elementId}
      onClose={closeInspector} onGroup={() => {}}
      onChange={(patch) => save(pins.map((pin) => pin.widget.id === selectedPin.widget.id ? { ...pin, width: patch.width ? patch.width === "full" ? 440 : 260 : pin.width, widget: { ...pin.widget, ...patch } } : pin))}
      onDelete={() => { save(pins.filter((pin) => pin.widget.id !== selectedPin.widget.id)); closeInspector(); }}
      onDuplicate={() => { if (pins.length >= 12) return; const copy = { ...selectedPin, x: selectedPin.x + 20, y: selectedPin.y + 20, widget: { ...selectedPin.widget, id: crypto.randomUUID() } }; save([...pins, copy]); inspectWidget?.(`pin:${copy.widget.id}`); }}
      onMove={(direction) => { const next = [...pins]; const index = next.findIndex((pin) => pin.widget.id === selectedPin.widget.id); const target = index + direction; if (target < 0 || target >= next.length) return; [next[index], next[target]] = [next[target], next[index]]; save(next); }}
    /></div>, inspectorHost)}
  </>;
}
