import type { BpmnModeler } from "./types";

export type CanvasNavigationMode = "mouse" | "trackpad";
type Element = { id: string };
type DiagramEvent = { element: Element; originalEvent: MouseEvent };
type Bus = { on: (name: string, priority: number, handler: (event: DiagramEvent) => unknown) => void; off: (name: string, handler: (event: DiagramEvent) => unknown) => void };
const preferenceKey = "delir:canvas:navigation";

/** Viewport and selection policy only. BPMN mutations remain native modeler commands. */
export function bindCanvasInteractions(modeler: BpmnModeler, changed: () => void) {
  const canvas = modeler.get("canvas") as { getContainer: () => HTMLElement; getRootElement: () => Element; focus: () => void; scroll: (delta: {dx:number;dy:number}) => void; zoom: (scale?: number, position?: {x:number;y:number}) => number };
  const host = canvas.getContainer();
  const svg = host.querySelector("svg")!;
  const dragging = modeler.get("dragging") as { cancel: () => void };
  const manager = modeler.get("toolManager") as { _active?: string; setActive: (tool: null) => void };
  const selection = modeler.get("selection") as { get: () => Element[] };
  const lasso = modeler.get("lassoTool") as { activateLasso: (event: MouseEvent) => void };
  const bus = modeler.get("eventBus") as Bus;
  const shell = host.closest(".process-bpmn-shell");
  let hovered = false;
  let hand = false;
  let space = false;
  let mode: CanvasNavigationMode = "mouse";
  try { if (localStorage.getItem(preferenceKey) === "trackpad") mode = "trackpad"; } catch { /* A restricted browser still supports session preferences. */ }
  let gesture: {id:number;x:number;y:number;moved:boolean} | null = null;
  let frame = 0;
  let dx = 0, dy = 0, zoomDelta = 0;
  let anchor = {x:0,y:0};
  let swallowClick = false;
  let clickReset: ReturnType<typeof setTimeout> | undefined;
  const isOverlay = (target: EventTarget | null) => target instanceof globalThis.Element && Boolean(target.closest(".djs-popup,input,textarea,select,button,[contenteditable=true],[role=menu],[role=listbox],[role=combobox]"));
  const cursor = () => { host.dataset.delirCursor = gesture ? "panning" : hand || space ? "pan" : "select"; };
  const flush = () => {
    frame = 0;
    if (dx || dy) canvas.scroll({dx,dy});
    if (zoomDelta) canvas.zoom(Math.min(4,Math.max(.2,canvas.zoom() * Math.exp(zoomDelta))),anchor);
    dx = dy = zoomDelta = 0;
  };
  const schedule = () => { if (!frame) frame = requestAnimationFrame(flush); };
  const stopGesture = () => {
    const previous = gesture; gesture = null;
    if (previous) {
      swallowClick = previous.moved || hand || space;
      clearTimeout(clickReset); clickReset = setTimeout(() => { swallowClick = false; }, 0);
      if (svg.hasPointerCapture(previous.id)) svg.releasePointerCapture(previous.id);
      if (frame) { cancelAnimationFrame(frame); flush(); }
    }
    cursor(); changed();
  };
  const select = () => { stopGesture(); dragging.cancel(); manager.setActive(null); hand = false; space = false; cursor(); canvas.focus(); changed(); };
  const pan = () => { stopGesture(); dragging.cancel(); manager.setActive(null); hand = true; cursor(); canvas.focus(); changed(); };
  const pointerDown = (event: PointerEvent) => {
    if (event.pointerType === "touch" || isOverlay(event.target) || !(event.target instanceof SVGElement)) return;
    if (!(event.button === 1 || event.button === 2 || event.button === 0 && (hand || space))) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (frame) { cancelAnimationFrame(frame); flush(); }
    canvas.focus(); gesture = {id:event.pointerId,x:event.clientX,y:event.clientY,moved:false}; svg.setPointerCapture(event.pointerId); cursor(); changed();
  };
  const pointerMove = (event: PointerEvent) => {
    if (!gesture || gesture.id !== event.pointerId) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const nextX = event.clientX - gesture.x, nextY = event.clientY - gesture.y;
    if (nextX || nextY) { dx += nextX; dy += nextY; gesture.moved = true; gesture.x = event.clientX; gesture.y = event.clientY; schedule(); }
  };
  const pointerEnter = () => { hovered = true; };
  const pointerLeave = () => { hovered = false; };
  const lostCapture = () => { if (gesture) stopGesture(); };
  const pointerEnd = (event: PointerEvent) => { if (gesture?.id === event.pointerId) { event.preventDefault(); event.stopImmediatePropagation(); stopGesture(); } };
  const mouseDuringPan = (event: MouseEvent) => { if (gesture) { event.preventDefault(); event.stopImmediatePropagation(); } };
  const click = (event: MouseEvent) => { if (swallowClick || hand || space) { swallowClick = false; event.preventDefault(); event.stopImmediatePropagation(); } };
  const contextMenu = (event: MouseEvent) => { if (!isOverlay(event.target)) event.preventDefault(); };
  const wheel = (event: WheelEvent) => {
    if (isOverlay(event.target)) { event.stopPropagation(); return; }
    event.preventDefault(); event.stopImmediatePropagation();
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? host.clientHeight : 1;
    const zoom = event.ctrlKey || event.metaKey || mode === "mouse" && !event.shiftKey;
    if (zoom) { const rect = host.getBoundingClientRect(); anchor = {x:event.clientX-rect.left,y:event.clientY-rect.top}; zoomDelta += -event.deltaY * unit * .0015; }
    else { dx -= (event.shiftKey ? event.deltaY : event.deltaX) * unit; dy -= (event.shiftKey ? 0 : event.deltaY) * unit; }
    schedule();
  };
  const keyDown = (event: KeyboardEvent) => {
    const editing = event.target instanceof globalThis.Element && event.target.closest("input,textarea,select,[contenteditable=true],[role=menu],[role=listbox],[role=combobox],[role=dialog]");
    if (editing || event.defaultPrevented || !(host.contains(document.activeElement) || hovered && shell?.contains(document.activeElement)) || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.code === "Space") { event.preventDefault(); event.stopImmediatePropagation(); if (!space) { space = true; canvas.focus(); cursor(); changed(); } }
    else if (!event.repeat && event.key.toLowerCase() === "v") { event.preventDefault(); event.stopImmediatePropagation(); select(); }
    else if (!event.repeat && event.key.toLowerCase() === "h") { event.preventDefault(); event.stopImmediatePropagation(); pan(); }
    else if (event.key === "Escape" && (hand || space)) { event.preventDefault(); event.stopImmediatePropagation(); select(); }
  };
  const keyUp = (event: KeyboardEvent) => { if (event.code === "Space" && space) { event.preventDefault(); event.stopImmediatePropagation(); space = false; cursor(); changed(); } };
  const blur = () => { stopGesture(); space = false; cursor(); changed(); };
  const keepSelection = (event: DiagramEvent) => {
    const mouse = event.originalEvent, selected = selection.get();
    if (!hand && !space && !manager._active && mouse.button === 0 && !mouse.shiftKey && !mouse.ctrlKey && !mouse.metaKey && selected.length === 1 && selected[0] === event.element) return false;
  };
  const startMarquee = (event: DiagramEvent) => {
    const mouse = event.originalEvent;
    if (!hand && !space && !manager._active && mouse.button === 0 && !mouse.ctrlKey && !mouse.metaKey && !mouse.altKey && event.element === canvas.getRootElement()) { canvas.focus(); lasso.activateLasso(mouse); return false; }
  };
  host.addEventListener("pointerenter",pointerEnter);
  host.addEventListener("pointerleave",pointerLeave);
  svg.addEventListener("lostpointercapture",lostCapture);
  host.addEventListener("pointerdown",pointerDown,true);
  host.addEventListener("pointermove",pointerMove,true);
  host.addEventListener("pointerup",pointerEnd,true);
  host.addEventListener("pointercancel",pointerEnd,true);
  host.addEventListener("click",click,true);
  host.addEventListener("contextmenu",contextMenu);
  host.addEventListener("wheel",wheel,{capture:true,passive:false});
  document.addEventListener("mousemove",mouseDuringPan,true);
  document.addEventListener("keydown",keyDown,true);
  document.addEventListener("keyup",keyUp,true);
  window.addEventListener("blur",blur);
  bus.on("element.click",2000,keepSelection);
  bus.on("element.mousedown",2000,startMarquee);
  cursor();
  return {
    select,pan,
    focus: () => canvas.focus(),
    get isPanning() { return hand || space || Boolean(gesture); },
    get navigationMode() { return mode; },
    setNavigationMode(value: CanvasNavigationMode) { mode = value; try { localStorage.setItem(preferenceKey,value); } catch { /* Session-only fallback. */ } changed(); },
    dispose() {
      if (frame) cancelAnimationFrame(frame);
      // Teardown must not refresh UI or flush work against a destroyed modeler.
      const previous = gesture; gesture = null;
      if (previous && svg.hasPointerCapture(previous.id)) svg.releasePointerCapture(previous.id);
      clearTimeout(clickReset);
      host.removeEventListener("pointerenter",pointerEnter);host.removeEventListener("pointerleave",pointerLeave);svg.removeEventListener("lostpointercapture",lostCapture);
      host.removeEventListener("pointerdown",pointerDown,true);host.removeEventListener("pointermove",pointerMove,true);host.removeEventListener("pointerup",pointerEnd,true);host.removeEventListener("pointercancel",pointerEnd,true);host.removeEventListener("click",click,true);host.removeEventListener("contextmenu",contextMenu);host.removeEventListener("wheel",wheel,true);
      document.removeEventListener("mousemove",mouseDuringPan,true);document.removeEventListener("keydown",keyDown,true);document.removeEventListener("keyup",keyUp,true);window.removeEventListener("blur",blur);
      bus.off("element.click",keepSelection);bus.off("element.mousedown",startMarquee);delete host.dataset.delirCursor;
    }
  };
}
