import { describe, expect, it, vi } from "vitest";

// Il canvas salva dicendo da quale versione e' partito: se nel frattempo
// l'agente o un collega ha salvato, il backend risponde 409 invece di
// sovrascrivere. Qui si verifica che la versione viaggi davvero e che quella
// nuova torni indietro per il salvataggio successivo.
const http = vi.fn<(path: string, init: { method?: string; body?: unknown }) => Promise<unknown>>();

vi.mock("@/lib/http", () => ({
  http: (path: string, init: { method?: string; body?: unknown }) => http(path, init),
  httpStream: vi.fn(),
}));

const { saveBpmnModelXml } = await import("./api");

const SAVED = {
  id: "model-1",
  process_id: "process-1",
  name: "Ordine fornitore",
  xml: "<definitions/>",
  version_id: 8,
};

describe("saveBpmnModelXml", () => {
  it("sends the version the canvas was loaded from", async () => {
    http.mockResolvedValue(SAVED);

    await saveBpmnModelXml("model-1", "<definitions/>", 7);

    const [path, init] = http.mock.calls.at(-1) ?? [];
    expect(path).toBe("/v1/workspace/bpmn-models/model-1");
    expect(init?.method).toBe("PUT");
    expect(init?.body).toEqual({ xml: "<definitions/>", expected_version_id: 7 });
  });

  it("returns the new version for the next save", async () => {
    http.mockResolvedValue(SAVED);

    const model = await saveBpmnModelXml("model-1", "<definitions/>", 7);

    expect(model.versionId).toBe(8);
  });

  it("sends no version when the canvas never had a saved one", async () => {
    http.mockResolvedValue({ ...SAVED, version_id: null });

    await saveBpmnModelXml("model-1", "<definitions/>");

    const [, init] = http.mock.calls.at(-1) ?? [];
    expect(init?.body).toEqual({ xml: "<definitions/>", expected_version_id: null });
  });
});
