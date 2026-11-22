import { describe, expect, it, vi } from "vitest";
import { bindCanvasInteractions } from "./canvasInteractions";
import type { BpmnModeler } from "./types";

describe("canvas tools", () => {
  it.each(["create.ended", "connect.ended"])("returns to selection after %s", eventName => {
    const host = document.createElement("div");
    host.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg"></svg>';
    document.body.append(host);
    const handlers = new Map<string, (event: unknown) => void>();
    const cancel = vi.fn(), setActive = vi.fn(), focus = vi.fn();
    const services: Record<string, unknown> = {
      canvas: { getContainer: () => host, getRootElement: () => ({ id: "root" }), focus, scroll: vi.fn(), zoom: () => 1 },
      dragging: { cancel, context: () => null },
      toolManager: { setActive },
      selection: { get: () => [], select: vi.fn() },
      elementRegistry: { get: vi.fn() },
      lassoTool: { activateLasso: vi.fn() },
      eventBus: { on: (name: string, _priority: number, handler: (event: unknown) => void) => handlers.set(name, handler), off: (name: string) => handlers.delete(name) },
    };
    const modeler = { get: (name: string) => services[name] } as BpmnModeler;
    const controls = bindCanvasInteractions(modeler, vi.fn());
    handlers.get(eventName)?.({});
    expect(cancel).toHaveBeenCalledOnce();
    expect(setActive).toHaveBeenCalledWith(null);
    expect(focus).toHaveBeenCalledOnce();
    controls.dispose();
    host.remove();
  });
});
