import { describe, expect, it, vi } from "vitest";
import { fetchBpmnModel } from "../api";
import { loadInitialModel } from "./xml";
vi.mock("../api", () => ({ fetchBpmnModel: vi.fn() }));
describe("loading the stored diagram", () => {
  it("does not disguise an unavailable model as an empty process", async () => {
    vi.mocked(fetchBpmnModel).mockRejectedValueOnce(new Error("Server unavailable"));
    await expect(loadInitialModel("model", "Process")).rejects.toThrow("Server unavailable");
  });
  it("uses the stored XML and starts empty only when a successful response has no diagram", async () => {
    vi.mocked(fetchBpmnModel).mockResolvedValueOnce({ xml: "<definitions />", versionId: 4 } as Awaited<ReturnType<typeof fetchBpmnModel>>);
    expect(await loadInitialModel("model", "Process")).toEqual({ xml: "<definitions />", versionId: 4 });
    vi.mocked(fetchBpmnModel).mockResolvedValueOnce({ xml: null, versionId: null } as Awaited<ReturnType<typeof fetchBpmnModel>>);
    const fresh = await loadInitialModel("new-model", "New process");
    expect(fresh.xml).toContain("bpmn:process");
    expect(fresh.versionId).toBeNull();
  });
});
