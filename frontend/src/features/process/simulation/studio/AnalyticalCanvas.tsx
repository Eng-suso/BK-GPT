import React from "react";
import { useTranslation } from "react-i18next";
import { GripVertical, Move, Maximize2, Minus, Plus, Workflow, Scaling } from "lucide-react";
import { Surface } from "@/ui/surface";
import { Button } from "@/ui/button";
import type { CanvasRect } from "../dashboard/dashboardModel";
import { bounds, fitCamera, PROCESS_ID, resizeRect, zoomCamera, freeInsertionRect, insertionRect, type Camera } from "./canvasGeometry";

import { PALETTE_DRAG_TYPE, parsePaletteItem, type PaletteItem } from "./canvasPaletteModel";

import { CanvasPalette } from "./CanvasPalette";

export type SceneObject = { id: string; title: string; rect: CanvasRect; content: React.ReactNode };

export function AnalyticalCanvas({ objects, editing, onPlace, onActionsHost, library = false, onCloseLibrary, onAdd, full = false }: {
  library?: boolean; onCloseLibrary?: () => void; onAdd?: (item: PaletteItem, rect: CanvasRect) => string | null; full?: boolean;
  objects: SceneObject[]; editing: boolean; onPlace: (id: string, rect: CanvasRect) => void; onActionsHost?: (host: HTMLDivElement | null) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const viewport = React.useRef<HTMLDivElement>(null);
  const [camera, setCamera] = React.useState<Camera>({ x: 24, y: 24, scale: 0.8 });
  const cameraRef = React.useRef(camera);
  React.useLayoutEffect(() => { cameraRef.current = camera; }, [camera]);
  const [activeObject, setActiveObject] = React.useState(PROCESS_ID);
  const initialized = React.useRef(false);
  const sceneRef = React.useRef(objects);
  React.useLayoutEffect(() => { sceneRef.current = objects; }, [objects]);
  const [draft, setDraft] = React.useState<{ id: string; rect: CanvasRect } | null>(null);
  const gesture = React.useRef<{ id?: string; resize?: boolean; x: number; y: number; camera: Camera; rect?: CanvasRect; pendingRect?: CanvasRect } | null>(null);
  const [addedTitle, setAddedTitle] = React.useState("");
  const [dropping, setDropping] = React.useState(false);
  const insertionFrame = React.useRef<number | null>(null);
  React.useEffect(() => () => { if (insertionFrame.current !== null) cancelAnimationFrame(insertionFrame.current); }, []);
  const process = objects.find(object => object.id === PROCESS_ID);
  const focus = (rect: CanvasRect) => {
    const el = viewport.current;
    if (el) {
      const fitted = fitCamera(rect, el.clientWidth, el.clientHeight);
      const scale = rect.width < 700 ? Math.max(0.75, fitted.scale) : fitted.scale;
      setCamera({ scale, x: (el.clientWidth - rect.width * scale) / 2 - rect.x * scale, y: Math.max(24, (el.clientHeight - rect.height * scale) / 2) - rect.y * scale });
    }
  };
  const insert = (item: PaletteItem, point?: { x: number; y: number }) => {
    const el = viewport.current;
    if (!el || !onAdd) return;
    const start = insertionRect(cameraRef.current, point?.x ?? Math.max(24, (el.clientWidth - 416 * cameraRef.current.scale) / 2), point?.y ?? 24);
    const rect = point ? start : freeInsertionRect(start, objects.map(object => object.rect));
    const id = onAdd(item, rect);
    if (id) {
      if (insertionFrame.current !== null) cancelAnimationFrame(insertionFrame.current);
      insertionFrame.current = requestAnimationFrame(() => {
        setCamera(fitCamera(rect, el.clientWidth, el.clientHeight));
        el.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
        insertionFrame.current = null;
      });
      setActiveObject(id); setAddedTitle(item.note ? t("simulation.authoring.note") : t(`simulation.studio.metric.${item.metric ?? (["bar", "column", "pie", "donut", "radial"].includes(item.kind) ? "activityQueued" : "completed")}`)); }
  };
  React.useEffect(() => {
    const el = viewport.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      const initialObjects = sceneRef.current;
      const initialProcess = initialObjects.find(object => object.id === PROCESS_ID);
      if (!initialized.current && el.clientWidth && el.clientHeight && initialProcess) {
        // Start with legible process and chart labels; taller scenes remain navigable vertically.
        const rect = el.clientWidth < 700 ? initialProcess.rect : bounds(initialObjects.slice(0, 3).map(object => object.rect));
        setCamera(el.clientWidth < 700 ? { x: (el.clientWidth - initialProcess.rect.width * 0.8) / 2 - initialProcess.rect.x * 0.8, y: 24 - initialProcess.rect.y * 0.8, scale: 0.8 } : { x: 24, y: 24, scale: Math.max(0.75, Math.min(1, (el.clientWidth - 48) / rect.width)) });
        initialized.current = true;
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  React.useEffect(() => {
    const el = viewport.current;
    if (!el) return;
    const wheel = (event: WheelEvent) => {
      if ((event.target as Element).closest("button,input,select,textarea,summary,.sim-data-table,.sim-note,.sim-studio-case")) return;
      event.preventDefault();
      const box = el.getBoundingClientRect();
      if (event.ctrlKey || event.metaKey) setCamera(current => zoomCamera(current, Math.exp(-event.deltaY * 0.002), event.clientX - box.left, event.clientY - box.top));
      else setCamera(current => ({ ...current, x: current.x - event.deltaX, y: current.y - event.deltaY }));
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, []);
  const begin = (event: React.PointerEvent<HTMLElement>, id?: string, resize = false) => {
    if (event.button !== 0) return;
    if (id) setActiveObject(id);
    if (!id && (event.target as Element).closest("button,input,select,textarea,summary,.sim-scene-object:not(.is-process),.djs-shape,.djs-connection,.sim-canvas-widget")) return;
    const object = id ? objects.find(item => item.id === id) : null;
    event.preventDefault(); event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    gesture.current = { id, resize, x: event.clientX, y: event.clientY, camera: cameraRef.current, rect: object?.rect };
  };
  const move = (event: React.PointerEvent) => {
    const g = gesture.current;
    if (!g) return;
    const dx = event.clientX - g.x, dy = event.clientY - g.y;
    if (g.id && g.rect) {
      if (!g.pendingRect && Math.hypot(dx, dy) < 4) return;
      g.pendingRect = g.resize ? resizeRect(g.rect, dx / g.camera.scale, dy / g.camera.scale) : { ...g.rect, x: Math.max(-10000, Math.min(10000, g.rect.x + dx / g.camera.scale)), y: Math.max(-10000, Math.min(10000, g.rect.y + dy / g.camera.scale)) };
      setDraft({ id: g.id, rect: g.pendingRect });
    }
    else setCamera({ ...g.camera, x: g.camera.x + dx, y: g.camera.y + dy });
  };
  const finish = () => {
    const current = gesture.current;
    if (current?.id && current.pendingRect) onPlace(current.id, current.pendingRect);
    setDraft(null); gesture.current = null;
  };
  const keyboardPlace = (event: React.KeyboardEvent, object: SceneObject, resize: boolean) => {
    const directions: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    const direction = directions[event.key];
    if (!direction) return;
    event.preventDefault(); event.stopPropagation();
    const step = event.shiftKey ? 100 : 20, [dx, dy] = direction;
    onPlace(object.id, resize ? resizeRect(object.rect, dx * step, dy * step) : { ...object.rect, x: Math.max(-10000, Math.min(10000, object.rect.x + dx * step)), y: Math.max(-10000, Math.min(10000, object.rect.y + dy * step)) });
  };
  const allBounds = bounds(objects.map(object => object.rect));
  const mapScale = Math.min(140 / Math.max(allBounds.width, 1), 68 / Math.max(allBounds.height, 1));
  return <Surface asChild variant="panel"><div className={`sim-analytical-canvas ${editing ? "is-authoring" : ""}`}>
    <div className="sim-scene-controls ui-surface-toolbar" role="group" aria-label={t("simulation.scene.navigation")}>
      <Button variant="outline" size="sm" aria-label={t("simulation.scene.backProcess")} onClick={() => process && focus(process.rect)}><Workflow aria-hidden className="size-4" /><span className="sim-scene-process-label">{t("simulation.scene.backProcess")}</span></Button>
      <label className="sim-scene-jump"><span className="sr-only">{t("simulation.scene.goTo")}</span><select className="ui-field" aria-label={t("simulation.scene.goTo")} value="" onChange={event => { const object = objects.find(item => item.id === event.target.value); if (object) { setActiveObject(object.id); focus(object.rect); } }}><option value="">{t("simulation.scene.goTo")}</option>{objects.map(object => <option value={object.id} key={object.id}>{object.title}</option>)}</select></label>
      <span className="sim-scene-instructions"><Move aria-hidden className="size-3.5" />{t(editing ? "simulation.scene.composeHint" : "simulation.scene.panHint")}</span>
      <div className="sim-scene-extra" ref={onActionsHost} />
      <Button variant="outline" type="button" className="sim-scene-map" aria-label={t("simulation.scene.map")} title={t("simulation.scene.showAll")} onClick={event => {
        const id = event.detail ? (event.target as HTMLElement).getAttribute("data-map-id") : null;
        const object = objects.find(item => item.id === id);
        if (object) setActiveObject(object.id);
        focus(object?.rect ?? allBounds);
      }}>
        {objects.map(object => <span aria-hidden key={object.id} data-map-id={object.id} className={object.id === PROCESS_ID ? "is-process" : ""} style={{ left: `${(8 + (object.rect.x - allBounds.x) * mapScale) / 156 * 100}%`, top: `${(8 + (object.rect.y - allBounds.y) * mapScale) / 84 * 100}%`, width: `${Math.max(8, object.rect.width * mapScale) / 156 * 100}%`, height: `${Math.max(8, object.rect.height * mapScale) / 84 * 100}%` }} />)}
      </Button>
      <div className="sim-scene-zoom">
        <Button variant="ghost" size="icon" aria-label={t("simulation.diagram.zoomOut")} onClick={() => setCamera(current => zoomCamera(current, 1 / 1.2, (viewport.current?.clientWidth ?? 0) / 2, (viewport.current?.clientHeight ?? 0) / 2))}><Minus aria-hidden className="size-4" /></Button>
        <output aria-label={t("simulation.scene.zoom")}>{Math.round(camera.scale * 100)}%</output>
        <Button variant="ghost" size="icon" aria-label={t("simulation.diagram.zoomIn")} onClick={() => setCamera(current => zoomCamera(current, 1.2, (viewport.current?.clientWidth ?? 0) / 2, (viewport.current?.clientHeight ?? 0) / 2))}><Plus aria-hidden className="size-4" /></Button>
        <Button variant="ghost" size="icon" aria-label={t("simulation.scene.showAll")} onClick={() => focus(allBounds)}><Maximize2 aria-hidden className="size-4" /></Button>
      </div>
    </div>
    <span className="sr-only" role="status">{addedTitle && t("simulation.authoring.added", { title: addedTitle })}</span>
    <div className="sim-scene-body">
    {library && onCloseLibrary && <CanvasPalette onAdd={item => insert(item)} onClose={onCloseLibrary} full={full} />}
    <div ref={viewport} className={`sim-scene-viewport ${dropping ? "is-dropping" : ""}`} tabIndex={0} role="region" aria-label={t("simulation.scene.workspace")} onDragOver={event => { if (event.dataTransfer.types.includes(PALETTE_DRAG_TYPE) && !full) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; setDropping(true); } }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropping(false); }} onDrop={event => {
      const item = parsePaletteItem(event.dataTransfer.getData(PALETTE_DRAG_TYPE));
      setDropping(false);
      if (!item || full) return;
      event.preventDefault(); event.stopPropagation();
      const box = event.currentTarget.getBoundingClientRect();
      insert(item, { x: event.clientX - box.left, y: event.clientY - box.top });
    }} onPointerDown={event => begin(event)} onPointerMove={move} onPointerUp={finish} onPointerCancel={() => { gesture.current = null; setDraft(null); }} onKeyDown={event => {
      if (event.target !== event.currentTarget) return;
      const directions: Record<string, [number, number]> = { ArrowLeft: [60, 0], ArrowRight: [-60, 0], ArrowUp: [0, 60], ArrowDown: [0, -60] };
      const direction = directions[event.key];
      if (direction) { event.preventDefault(); setCamera(current => ({ ...current, x: current.x + direction[0], y: current.y + direction[1] })); }
      if (event.key === "Home" && process) { event.preventDefault(); focus(process.rect); }
      if (event.key === "+" || event.key === "-") { event.preventDefault(); setCamera(current => zoomCamera(current, event.key === "+" ? 1.2 : 1 / 1.2, event.currentTarget.clientWidth / 2, event.currentTarget.clientHeight / 2)); }
    }}>
      <div className="sim-scene-world" style={{ transform: `translate(${camera.x}px, ${camera.y}px) scale(${camera.scale})`, "--scene-ui-scale": 1 / camera.scale } as React.CSSProperties}>
        {objects.map(object => {
          const rect = draft?.id === object.id ? draft.rect : object.rect;
          return <div key={object.id} className={`sim-scene-object ${object.id === PROCESS_ID ? "is-process" : ""} ${editing ? "is-composing" : ""} ${activeObject === object.id ? "is-active" : ""}`} data-scene-object={object.id} onPointerDownCapture={event => {
            setActiveObject(object.id);
            const target = event.target as Element;
            if (target.closest(".sim-widget-heading,.sim-process-tile-header") && !target.closest("button,input,select,textarea,a")) begin(event, object.id);
          }} onFocusCapture={event => {
            if (editing) setActiveObject(object.id);
            if (!(event.target as Element).matches(":focus-visible")) return;
            const el = viewport.current;
            if (!el) return;
            const c = cameraRef.current;
            const left = rect.x * c.scale + c.x, top = rect.y * c.scale + c.y;
            if (left < 0 || top < 0 || left + rect.width * c.scale > el.clientWidth || top + rect.height * c.scale > el.clientHeight) focus(rect);
          }} style={{ left: rect.x, top: rect.y, width: rect.width, height: rect.height }}>
            {<Button variant="ghost" size="icon" type="button" className="sim-scene-move" aria-label={t("simulation.scene.move", { title: object.title })} title={t("simulation.scene.keyboardHint")} onPointerDown={event => begin(event, object.id)} onKeyDown={event => keyboardPlace(event, object, false)}><GripVertical aria-hidden className="size-4" /></Button>}
            {object.content}
            {editing && activeObject === object.id && <Button variant="outline" size="icon" type="button" className="sim-scene-resize" aria-label={t("simulation.scene.resize", { title: object.title })} title={t("simulation.scene.keyboardHint")} onPointerDown={event => begin(event, object.id, true)} onKeyDown={event => keyboardPlace(event, object, true)}><Scaling aria-hidden className="size-4" /></Button>}
          </div>;
        })}
      </div>
    </div>
    </div>
  </div></Surface>;
}
