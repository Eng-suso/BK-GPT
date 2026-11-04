import { useLayoutEffect, useState, type RefObject } from "react";
import { ArrowUpRight, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";

/** The connection action belongs to the selected symbol, close to its edge. */
export function BpmnConnectionControl({ host, geometryKey, selectedId, enabled, connecting, targetState, onAction, onCancel }: {
  host: RefObject<HTMLDivElement | null>;
  geometryKey:string;
  selectedId?: string;
  enabled: boolean;
  connecting: boolean;
  targetState: "valid" | "invalid" | null;
  onAction: (id: string, event: Event) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation("process");
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  useLayoutEffect(() => {
    const container = host.current;
    if (!container || !selectedId || !enabled) return;
    const shape = container.querySelector(`[data-element-id="${CSS.escape(selectedId)}"]`);
    const body = shape?.querySelector(".djs-visual > :first-child");
    const viewport = container.querySelector("g.viewport");
    if (!body) return;
    let frame = 0;
    const measure = () => {
      const bounds = container.getBoundingClientRect(), rect = body.getBoundingClientRect();
      if(rect.right<bounds.left || rect.left>bounds.right || rect.bottom<bounds.top || rect.top>bounds.bottom) {setPosition(null);return;}
      const left = rect.right + 8 - bounds.left;
      const next = { left: Math.max(4, Math.min(bounds.width - 40, left)), top: Math.max(4, Math.min(bounds.height - 40, rect.top + rect.height / 2 - bounds.top - 18)) };
      setPosition(previous => previous?.left === next.left && previous.top === next.top ? previous : next);
    };
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    measure();
    const resize = new ResizeObserver(schedule); resize.observe(container);
    const mutation = new MutationObserver(schedule);
    if (shape) mutation.observe(shape, { attributes: true, attributeFilter: ["transform"] });
    if (viewport) mutation.observe(viewport, { attributes: true, attributeFilter: ["transform"] });
    return () => { resize.disconnect(); mutation.disconnect(); cancelAnimationFrame(frame); };
  }, [host, geometryKey, selectedId, enabled]);
  return <>
    {enabled && selectedId && position && !connecting && <Button className="process-node-connect" variant="outline" size="icon" style={position} aria-label={t("canvas.interactions.connect")} title={t("canvas.connectGesture.actionHint")} onMouseDown={event => { if (event.button === 0) { event.preventDefault(); onAction("connect.drag", event.nativeEvent); } }} onTouchStart={event => onAction("connect.drag", event.nativeEvent)} onClick={event => onAction("connect", event.nativeEvent)}><ArrowUpRight aria-hidden className="size-4" /></Button>}
    {connecting && <div className="process-connection-hint" role="status" aria-live="polite"><span>{t(targetState === "invalid" ? "canvas.connectGesture.invalid" : targetState === "valid" ? "canvas.connectGesture.confirm" : "canvas.connectGesture.choose")}</span><Button variant="ghost" size="icon-sm" aria-label={t("canvas.connectGesture.cancel")} onClick={onCancel}><X aria-hidden className="size-4" /></Button></div>}
  </>;
}
