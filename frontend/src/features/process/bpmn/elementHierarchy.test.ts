import { describe, expect, it } from "vitest";
import { elementHierarchy } from "./elementHierarchy";
import type { CanvasElement } from "./elements";

const elements: CanvasElement[] = [
  { id: "task", name: "Approve", type: "UserTask", kind: "task", parentId: "lane" },
  { id: "pool", name: "Company", type: "Participant", kind: "other" },
  { id: "lane", name: "Purchasing", type: "Lane", kind: "other", parentId: "pool" },
  { id: "end", name: "Done", type: "EndEvent", kind: "end", parentId: "lane" },
];

describe("BPMN element hierarchy", () => {
  it("shows pool, lane and work in ownership order", () => {
    expect(elementHierarchy(elements).map(row => [row.element.id, row.depth])).toEqual([
      ["pool", 0], ["lane", 1], ["task", 2], ["end", 2],
    ]);
  });

  it("keeps ancestors visible when searching for an activity", () => {
    expect(elementHierarchy(elements, "Approve").map(row => row.element.id)).toEqual(["pool", "lane", "task"]);
    expect(elementHierarchy(elements, "Purchasing").map(row => row.element.id)).toEqual(["pool", "lane", "task", "end"]);
  });
});
