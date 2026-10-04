import { describe, expect, it } from "vitest";

import { toApiChatScope } from "./chat";

// L'XML del canvas va all'agente con la versione salvata da cui viene: e' la
// base su cui il turno controlla di non scrivere sopra un salvataggio altrui.
const SCOPE = {
  type: "canvas" as const,
  projectId: "p",
  processId: "pr",
  processName: "Ordine fornitore",
  bpmnModelId: "m",
  currentBpmnXml: "<definitions/>",
  currentBpmnVersionId: 7,
};

describe("toApiChatScope (canvas)", () => {
  it("sends the saved version together with the canvas XML", () => {
    const api = toApiChatScope(SCOPE);

    expect(api).toMatchObject({ current_bpmn_xml: "<definitions/>", current_bpmn_version_id: 7 });
  });

  it("sends neither when the transient canvas is left out", () => {
    const api = toApiChatScope(SCOPE, { includeTransient: false });

    expect(api).not.toHaveProperty("current_bpmn_xml");
    expect(api).not.toHaveProperty("current_bpmn_version_id");
  });
});
