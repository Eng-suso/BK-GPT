import { describe, expect, it, vi } from "vitest";
import { fetchBpmnModel } from "../api";
import { loadInitialXml } from "./xml";
vi.mock("../api", () => ({ fetchBpmnModel: vi.fn() }));
describe("loading the stored diagram", () => {
  it("does not disguise an unavailable model as an empty process", async () => {
    vi.mocked(fetchBpmnModel).mockRejectedValueOnce(new Error("Server unavailable"));
    await expect(loadInitialXml("model", "Process")).rejects.toThrow("Server unavailable");
  });
  it("uses the stored XML and starts empty only when a successful response has no diagram", async () => {
    vi.mocked(fetchBpmnModel).mockResolvedValueOnce({ xml: "<definitions />" } as Awaited<ReturnType<typeof fetchBpmnModel>>);
    expect(await loadInitialXml("model", "Process")).toBe("<definitions />");
    vi.mocked(fetchBpmnModel).mockResolvedValueOnce({ xml: null } as Awaited<ReturnType<typeof fetchBpmnModel>>);
    expect(await loadInitialXml("new-model", "New process")).toContain("bpmn:process");
  });
});
