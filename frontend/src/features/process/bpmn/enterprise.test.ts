import { describe, expect, it } from "vitest";
import { readSelectedElement } from "./enterprise";

describe("selected BPMN activity", () => {
  it("shows its lane separately from the optional operational owner", () => {
    const selected = readSelectedElement({
      id: "approve",
      type: "bpmn:Task",
      businessObject: { name: "Approve purchase" },
      parent: {
        id: "purchasing",
        type: "bpmn:Lane",
        businessObject: { name: "Purchasing Department" },
      },
    });

    expect(selected.laneName).toBe("Purchasing Department");
    expect(selected.metadata.owner).toBe("");
  });
});
