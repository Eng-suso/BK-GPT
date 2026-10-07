import React from "react";
import NavigatedViewer from "bpmn-js/lib/NavigatedViewer";
import { Maximize2, Minus, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Surface } from "@/ui/surface";
import { Button } from "@/ui/button";
import { InlineNotice } from "@/components/feedback/InlineNotice";
import type { BpmnViewer } from "../simulation/canvas/bpmnViewer";
import { fitCanvas } from "../bpmn/viewport";
import type { ReviewNode } from "./reviewModel";
import { ReviewMascot } from "./ReviewMascot";

import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";

type CanvasService = {
  zoom: (scale?: number | "fit-viewport") => number;
  resized: () => void;
  addMarker: (id: string, marker: string) => void;
  removeMarker: (id: string, marker: string) => void;
};
type Registry = { getGraphics: (id: string) => SVGElement | undefined; get: (id: string) => unknown };

/** Read-only viewer: reviewing cannot dispatch modeling commands or save XML. */
export function ReviewCanvas({ xml, nodes, selected, upstream, downstream, documents, focusImpact, gap, onSelect, onInspect }: {
  xml: string; nodes: ReviewNode[]; selected: ReviewNode | null; upstream: string[]; downstream: string[]; documents: string[];
  focusImpact: boolean; gap?: "owner" | "input" | "output" | "evidence"; onSelect: (id: string) => void; onInspect: () => void;
}) {
  const { t } = useTranslation("process");
  const host = React.useRef<HTMLDivElement>(null);
  const viewer = React.useRef<BpmnViewer | null>(null);
  const selectedRef = React.useRef(selected?.id);
  const selectRef = React.useRef(onSelect);
  const nodesRef = React.useRef(nodes);
  const [ready, setReady] = React.useState(false);
  const [error, setError] = React.useState(false);
  const [retry, setRetry] = React.useState(0);
  const [anchor, setAnchor] = React.useState<{ left: number; top: number } | null>(null);
  const [activation, setActivation] = React.useState(0);
  React.useLayoutEffect(() => { selectedRef.current = selected?.id; selectRef.current = onSelect; nodesRef.current = nodes; });

  const measure = React.useCallback(() => {
    const id = selectedRef.current;
    const graphic = id ? (viewer.current?.get("elementRegistry") as Registry | undefined)?.getGraphics(id) : undefined;
    const box = graphic?.getBoundingClientRect();
    const frame = host.current?.getBoundingClientRect();
    if (!box || !frame || box.right < frame.left || box.left > frame.right || box.bottom < frame.top || box.top > frame.bottom) { setAnchor(null); return; }
    const width = Math.min(244, frame.width - 24);
    const left = Math.max(12, Math.min(frame.width - width - 12, box.right - frame.left + 16));
    const preferred = box.top - frame.top - 84;
    const top = Math.max(12, Math.min(frame.height - 100, preferred >= 12 ? preferred : box.bottom - frame.top + 12));
    setAnchor({ left, top });
  }, []);

  React.useEffect(() => {
    if (!host.current) return;
    let mounted = true;
    setReady(false); setError(false); setAnchor(null);
    const tokens = getComputedStyle(host.current);
    const instance = new NavigatedViewer({ container: host.current, textRenderer: {
      defaultStyle: { fontFamily: tokens.getPropertyValue("--font-family-geist").trim(), fontSize: Number.parseFloat(tokens.getPropertyValue("--font-size-300")) },
      externalStyle: { fontFamily: tokens.getPropertyValue("--font-family-geist").trim(), fontSize: Number.parseFloat(tokens.getPropertyValue("--font-size-100")) },
    }, bpmnRenderer: {
      defaultFillColor: tokens.getPropertyValue("--color-surface-primary").trim(),
      defaultStrokeColor: tokens.getPropertyValue("--color-text-secondary").trim(),
    } }) as BpmnViewer;
    viewer.current = instance;
    const canvas = instance.get("canvas") as CanvasService;
    instance.on("element.click", (event: unknown) => {
      const id = (event as { element?: { id?: string } }).element?.id;
      if (id && nodesRef.current.some(node => node.id === id)) selectRef.current(id);
    });
    instance.on("canvas.viewbox.changed", measure);
    const observer = new ResizeObserver(() => { canvas.resized(); measure(); });
    observer.observe(host.current);
    void instance.importXML(xml).then(() => {
      if (!mounted) return;
      fitCanvas(instance); setReady(true); measure();
    }).catch(() => { if (mounted) setError(true); });
    return () => { mounted = false; observer.disconnect(); instance.destroy(); if (viewer.current === instance) viewer.current = null; };
  }, [xml, retry, measure]);

  React.useLayoutEffect(() => {
    if (!ready || !viewer.current) return;
    const canvas = viewer.current.get("canvas") as CanvasService;
    const registry = viewer.current.get("elementRegistry") as Registry;
    const marks: Array<[string[], string]> = [[selected ? [selected.id] : [], "review-selected"], [focusImpact ? upstream : [], "review-upstream"], [focusImpact ? downstream : [], "review-downstream"], [focusImpact ? documents : [], "review-document"]];
    for (const [ids, marker] of marks) for (const id of ids) if (registry.get(id)) canvas.addMarker(id, marker);
    measure();
    return () => { for (const [ids, marker] of marks) for (const id of ids) if (registry.get(id)) canvas.removeMarker(id, marker); };
  }, [selected, upstream, downstream, documents, focusImpact, ready, measure]);

  const zoom = (delta: number) => { const canvas = viewer.current?.get("canvas") as CanvasService | undefined; if (canvas) canvas.zoom(Math.min(3, Math.max(0.2, canvas.zoom() + delta))); };
  return <div className="review-canvas-stage">
    <div ref={host} className="review-canvas" aria-label={t("review.canvasLabel")} />
    {error && <div className="review-canvas-error"><InlineNotice tone="error" title={t("review.diagramError")} action={<Button size="sm" variant="outline" onClick={() => setRetry(value => value + 1)}>{t("review.retry")}</Button>} /></div>}
    {ready && selected && anchor && <Surface variant="floating" className="review-agent-card" style={anchor}>
      <Button variant="ghost" size="icon" className="review-agent-avatar" aria-label={t("review.inspectTask", { name: selected.name })} onClick={() => { setActivation(value => value + 1); onInspect(); }}><span key={`${selected.id}:${activation}`} className="review-mascot-orbit"><ReviewMascot /></span></Button>
      <div className="min-w-0"><p className="review-agent-signature">DeliR <span> / Review</span></p><p className="review-agent-message">{gap ? t(`review.bubbleGap.${gap}`) : t("review.bubbleComplete")}</p></div>
    </Surface>}
    <Surface variant="floating" className="review-canvas-controls" role="group" aria-label={t("canvas.zoomGroup")}>
      <Button variant="ghost" size="sm" disabled={!ready} onClick={() => { if (viewer.current) fitCanvas(viewer.current); }}><Maximize2 aria-hidden />{t("canvas.fit")}</Button>
      <Button variant="ghost" size="icon" disabled={!ready} aria-label={t("canvas.zoomOut")} onClick={() => zoom(-0.2)}><Minus aria-hidden /></Button>
      <Button variant="ghost" size="icon" disabled={!ready} aria-label={t("canvas.zoomIn")} onClick={() => zoom(0.2)}><Plus aria-hidden /></Button>
    </Surface>
  </div>;
}
