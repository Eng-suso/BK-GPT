import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import type { BpmnModeler } from "./types";
import { bindCanvasInteractions, type CanvasNavigationMode } from "./canvasInteractions";
import type { CreationTool } from "./elements";

export type SelectionItem = { id: string; name: string; type: string };
type SelectedShape = Omit<SelectionItem, "name"> & { labelTarget?: SelectedShape; businessObject?: { name?: string }; source?: SelectedShape; target?: SelectedShape };
type UiState = { navigationMode: CanvasNavigationMode; zoomPercent: number; activeTool: string; canUndo: boolean; canRedo: boolean; selectionCount: number; isMultiple: boolean; selectionItems: SelectionItem[]; contextActions: CreationTool[] };
const initial: UiState = { navigationMode:"mouse", zoomPercent: 100, activeTool: "select", canUndo: false, canRedo: false, selectionCount: 0, isMultiple: false, selectionItems: [], contextActions: [] };
type Selection = { get: () => SelectedShape[] };
type ContextPad = { getEntries: (target: unknown) => Record<string, Omit<CreationTool, "id">>; triggerEntry: (id: string, action: string, event: Event) => void };
type Commands = { canUndo: () => boolean; canRedo: () => boolean; undo: () => void; redo: () => void };
const toolIds: Record<string, string> = { hand: "hand-tool", lasso: "lasso-tool", space: "space-tool", "global-connect": "global-connect-tool" };

/** Observes presentation state and forwards existing modeler commands. No XML conversion. */
export function useBpmnCanvasUi(modelerRef: RefObject<BpmnModeler | null>, ready: boolean) {
  const [state, setState] = useState(initial);
  const interactions = useRef<ReturnType<typeof bindCanvasInteractions> | null>(null);
  const requestedTool = useRef("select");
  useEffect(() => {
    const modeler = modelerRef.current;
    if (!ready || !modeler) return;
    const bus = modeler.get("eventBus") as { on: (events: string[], callback: () => void) => void; off: (events: string[], callback: () => void) => void };
    const events = ["selection.changed", "contextPad.open", "contextPad.close", "commandStack.changed", "canvas.viewbox.changed", "tool-manager.update", "create.init", "create.ended", "create.canceled", "lasso.ended", "connect.ended", "connect.canceled"];
    const refresh = () => {
      const selection = (modeler.get("selection") as Selection).get();
      // Labels are alternate graphics of their owner, never additional process elements.
      const items = [...new Map(selection.map(item => {
        const owner = item.labelTarget ?? item;
        return [owner.id, { id: owner.id, name: owner.businessObject?.name?.trim() || (owner.source && owner.target ? [owner.source, owner.target].map(endpoint => endpoint.businessObject?.name?.trim() || endpoint.id).join(" → ") : ""), type: owner.type.replace(/^bpmn:/, "") }];
      })).values()];
      const context = modeler.get("contextPad") as ContextPad;
      const commands = modeler.get("commandStack") as Commands;
      const tool = (modeler.get("toolManager") as { _active?: string })._active;
      const entries = selection.length ? context.getEntries(selection.length === 1 ? selection[0] : selection) : {};
      const drag = (modeler.get("dragging") as { context: () => {prefix:string} | null }).context();
      const next: UiState = { navigationMode: interactions.current?.navigationMode ?? "mouse", zoomPercent: Math.round((modeler.get("canvas") as { zoom: () => number }).zoom() * 100), activeTool: interactions.current?.isPanning ? "hand-tool" : drag?.prefix === "create" ? requestedTool.current : tool ? toolIds[tool] ?? tool : "select", canUndo: commands.canUndo(), canRedo: commands.canRedo(), selectionCount: items.length, isMultiple: selection.length > 1, selectionItems: items, contextActions: (interactions.current?.isPanning || drag ? [] : Object.entries(entries)).map(([id, entry]) => ({ id, title: entry.title, className: entry.className, group: entry.group })) };
      setState(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    };
    const controls = bindCanvasInteractions(modeler, refresh);
    interactions.current = controls;
    bus.on(events, refresh);
    refresh();
    return () => { bus.off(events, refresh); controls.dispose(); if (interactions.current === controls) interactions.current = null; };
  }, [modelerRef, ready]);
  const selectTool = useCallback(() => interactions.current?.select(), []);
  const panTool = useCallback(() => interactions.current?.pan(), []);
  const prepareTool = useCallback((id: string) => { requestedTool.current = id; interactions.current?.select(); }, []);
  const setNavigationMode = useCallback((mode: CanvasNavigationMode) => interactions.current?.setNavigationMode(mode), []);
  const contextAction = useCallback((id: string, event: Event) => {
    (modelerRef.current?.get("contextPad") as ContextPad | undefined)?.triggerEntry(id, "click", event);
  }, [modelerRef]);
  const undo = useCallback(() => { (modelerRef.current?.get("commandStack") as Commands | undefined)?.undo(); interactions.current?.focus(); }, [modelerRef]);
  const redo = useCallback(() => { (modelerRef.current?.get("commandStack") as Commands | undefined)?.redo(); interactions.current?.focus(); }, [modelerRef]);
  const zoomTo = useCallback((percent: number) => (modelerRef.current?.get("canvas") as { zoom: (scale: number) => void } | undefined)?.zoom(Math.min(4, Math.max(.2, percent / 100))), [modelerRef]);
  return { canvasUi: ready ? state : initial, selectTool, panTool, prepareTool, setNavigationMode, contextAction, undo, redo, zoomTo };
}
