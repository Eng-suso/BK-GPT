import { describe, expect, it } from "vitest";

import { DeliRRenderer } from "./Renderer";
import { businessObject, type Bus, type CanvasElement } from "./types";

describe("foreign BPMN task labels", () => {
  it("shows the complete task name inside a 100 by 80 imported shape", () => {
    const renderer = new DeliRRenderer({ on: () => undefined } as unknown as Bus);
    const gfx = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const name = "Check if customer has all required information";
    renderer.drawShape(gfx, {
      id: "task", type: "bpmn:Task", businessObject: businessObject("bpmn:Task", { id: "task", name }),
      x: 0, y: 0, width: 100, height: 80,
    } as CanvasElement);
    const label = gfx.querySelector("text.delir-node-label");
    expect(label?.textContent?.replace(/\s+/g, " ").trim()).toBe(name);
    expect(label?.getAttribute("font-size")).toBe("12");
  });
});
