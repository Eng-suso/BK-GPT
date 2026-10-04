import { afterEach, describe, expect, it } from "vitest";

import { draftBaseVersion, readLocalBpmnDraft, writeLocalBpmnDraft } from "./draft";

// Una bozza locale ricorda da quale versione salvata e' partita. Senza, la
// bozza ripresa dopo un 409 (o dopo un salvataggio altrui) prendeva come base
// l'ultima versione del server e il salvataggio successivo la sovrascriveva.
afterEach(() => window.localStorage.clear());

describe("local BPMN draft", () => {
  it("keeps the version it was edited from", () => {
    writeLocalBpmnDraft("model-1", "<definitions/>", 7);

    expect(readLocalBpmnDraft("model-1")).toEqual({
      xml: "<definitions/>",
      baseVersionId: 7,
    });
  });

  it("reads a draft written before the version was stored", () => {
    window.localStorage.setItem("workspace:bpmn-draft:model-1", "<definitions/>");

    expect(readLocalBpmnDraft("model-1")).toEqual({
      xml: "<definitions/>",
      baseVersionId: undefined,
    });
  });
});

describe("draftBaseVersion", () => {
  it("saves a draft against the version it came from, not the latest one", () => {
    expect(draftBaseVersion(7, 9)).toBe(7);
  });

  it("makes a draft that cannot prove its base conflict instead of overwrite", () => {
    expect(draftBaseVersion(undefined, 9)).toBeLessThan(0);
    expect(draftBaseVersion(null, 9)).toBeLessThan(0);
  });

  it("lets a draft of a never-saved model save while it is still unsaved", () => {
    expect(draftBaseVersion(null, null)).toBeNull();
  });
});
