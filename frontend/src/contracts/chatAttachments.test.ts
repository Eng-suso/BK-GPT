import { describe, expect, it } from "vitest";

import {
  MAX_NOTE_ATTACHMENT_CHARS,
  apiChatAttachmentSchema,
  chatAttachmentKey,
  toApiChatAttachment,
  type ChatAttachment,
} from "./chat";

/**
 * Gli allegati attraversano il confine con il backend, dove `SourceAttachment`
 * e compagnia sono snake_case. Qui si controlla che la traduzione produca
 * esattamente la forma che il backend accetta — se il nome di un campo cambia
 * da un lato, questo test cade prima che lo faccia una richiesta vera.
 */
describe("toApiChatAttachment", () => {
  it("renames the project reference the way the backend spells it", () => {
    const attachment: ChatAttachment = {
      kind: "source",
      id: "src-1",
      label: "Verbale kickoff",
      projectId: "prj-1",
    };

    const api = toApiChatAttachment(attachment);

    expect(api).toEqual({
      kind: "source",
      id: "src-1",
      label: "Verbale kickoff",
      project_id: "prj-1",
    });
    expect(() => apiChatAttachmentSchema.parse(api)).not.toThrow();
  });

  it("carries the model id for a simulation run", () => {
    const api = toApiChatAttachment({
      kind: "simulation_run",
      id: "7",
      label: "AS-IS baseline",
      bpmnModelId: "bpmn-1",
    });

    expect(api).toEqual({
      kind: "simulation_run",
      id: "7",
      label: "AS-IS baseline",
      bpmn_model_id: "bpmn-1",
    });
    expect(() => apiChatAttachmentSchema.parse(api)).not.toThrow();
  });

  it("clips a pasted text to what the backend will accept", () => {
    // Il backend rifiuta oltre il cap: tagliare qui evita un 422 su un turno
    // che il consulente ha gia' scritto.
    const api = toApiChatAttachment({
      kind: "note",
      id: "note-1",
      label: "Dump",
      text: "x".repeat(MAX_NOTE_ATTACHMENT_CHARS + 500),
    });

    expect(api.kind).toBe("note");
    if (api.kind === "note") {
      expect(api.text).toHaveLength(MAX_NOTE_ATTACHMENT_CHARS);
    }
    expect(() => apiChatAttachmentSchema.parse(api)).not.toThrow();
  });

  it("rejects a reference with no id, instead of sending an empty one", () => {
    expect(() =>
      apiChatAttachmentSchema.parse({
        kind: "process",
        id: "",
        label: "Ciclo ordini",
        project_id: "prj-1",
      }),
    ).toThrow();
  });
});

describe("chatAttachmentKey", () => {
  it("separates two kinds that happen to share an id", () => {
    const source: ChatAttachment = {
      kind: "source",
      id: "1",
      label: "Fonte",
      projectId: "prj-1",
    };
    const process: ChatAttachment = {
      kind: "process",
      id: "1",
      label: "Processo",
      projectId: "prj-1",
    };

    expect(chatAttachmentKey(source)).not.toBe(chatAttachmentKey(process));
  });
});
