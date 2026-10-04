import React from "react";
import { svc, type BpmnCanvas, type BpmnViewer } from "./bpmnViewer";

const INTERACTIVE = "button,input,select,textarea,summary,a,[contenteditable=true],.sim-canvas-widget";

/** Navigate the embedded diagram without moving its analytics workspace or saved layout. */
export function useDiagramNavigation(container: React.RefObject<HTMLDivElement | null>, viewer: React.RefObject<BpmnViewer | null>, enabled: boolean): void {
  React.useEffect(() => {
    const element = container.current;
    if (!element || !enabled) return;
    let gesture: { pointerId: number; x: number; y: number; lastX: number; lastY: number; scaleX: number; scaleY: number } | null = null;
    let dragged = false;
    const canvas = () => svc<BpmnCanvas>(viewer.current, "canvas");
    const scaling = () => {
      const box = element.getBoundingClientRect();
      return { box, x: box.width / Math.max(1, element.clientWidth), y: box.height / Math.max(1, element.clientHeight) };
    };
    const interactive = (target: EventTarget | null) => target instanceof Element && Boolean(target.closest(INTERACTIVE));
    const down = (event: PointerEvent) => {
      if (event.button !== 0 || interactive(event.target)) return;
      const scale = scaling();
      dragged = false;
      gesture = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, lastX: event.clientX, lastY: event.clientY, scaleX: scale.x, scaleY: scale.y };
      event.stopPropagation();
      element.focus({ preventScroll: true });
    };
    const move = (event: PointerEvent) => {
      if (!gesture || gesture.pointerId !== event.pointerId) return;
      if (event.pointerType === "mouse" && event.buttons === 0) { gesture = null; dragged = false; return; }
      if (!dragged && Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) < 4) return;
      if (!dragged) element.setPointerCapture(event.pointerId);
      dragged = true;
      canvas()?.scroll({ dx: (event.clientX - gesture.lastX) / gesture.scaleX, dy: (event.clientY - gesture.lastY) / gesture.scaleY });
      gesture.lastX = event.clientX; gesture.lastY = event.clientY;
      event.preventDefault(); event.stopPropagation();
    };
    const end = (event: PointerEvent) => {
      if (gesture?.pointerId !== event.pointerId) return;
      if (element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId);
      gesture = null;
    };
    const cancel = (event: PointerEvent) => { end(event); dragged = false; };
    const click = (event: MouseEvent) => {
      if (dragged) { event.preventDefault(); event.stopPropagation(); dragged = false; }
    };
    const wheel = (event: WheelEvent) => {
      if (interactive(event.target)) return;
      const service = canvas();
      if (!service) return;
      event.preventDefault(); event.stopPropagation();
      const scale = scaling();
      if (event.ctrlKey || event.metaKey) service.zoom(Math.max(0.2, Math.min(4, service.zoom() * Math.exp(-event.deltaY * 0.002))), { x: (event.clientX - scale.box.left) / scale.x, y: (event.clientY - scale.box.top) / scale.y });
      else {
        const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element.clientHeight : 1;
        service.scroll({ dx: -(event.shiftKey ? event.deltaY : event.deltaX) * unit / scale.x, dy: event.shiftKey ? 0 : -event.deltaY * unit / scale.y });
      }
    };
    const key = (event: KeyboardEvent) => {
      if (event.target !== element) return;
      const service = canvas();
      if (!service) return;
      const direction: Record<string, [number, number]> = { ArrowLeft: [60, 0], ArrowRight: [-60, 0], ArrowUp: [0, 60], ArrowDown: [0, -60] };
      const step = direction[event.key];
      if (step) service.scroll({ dx: step[0], dy: step[1] });
      else if (event.key === "Home") service.zoom("fit-viewport");
      else if (event.key === "+" || event.key === "-") service.zoom(Math.max(0.2, Math.min(4, service.zoom() * (event.key === "+" ? 1.2 : 1 / 1.2))));
      else return;
      event.preventDefault(); event.stopPropagation();
    };
    element.addEventListener("pointerdown", down);
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", end);
    element.addEventListener("pointercancel", cancel);
    element.addEventListener("click", click, true);
    element.addEventListener("wheel", wheel, { passive: false });
    element.addEventListener("keydown", key);
    return () => {
      element.removeEventListener("pointerdown", down);
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", end);
      element.removeEventListener("pointercancel", cancel);
      element.removeEventListener("click", click, true);
      element.removeEventListener("wheel", wheel);
      element.removeEventListener("keydown", key);
    };
  }, [container, viewer, enabled]);
}
