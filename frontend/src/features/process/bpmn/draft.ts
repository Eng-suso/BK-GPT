/** Best-effort local persistence of unsaved canvas edits, keyed per model. */

function getLocalDraftKey(bpmnModelId: string): string {
  return `workspace:bpmn-draft:${bpmnModelId}`;
}

export type LocalBpmnDraft = {
  xml: string;
  /**
   * The saved version the draft was edited from. A restored draft sends it
   * back on save, so it can never overwrite a version saved after it.
   * `undefined` for drafts written before the version was stored: those
   * must reload before saving.
   */
  baseVersionId: number | null | undefined;
};

export function readLocalBpmnDraft(bpmnModelId: string): LocalBpmnDraft | null {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(getLocalDraftKey(bpmnModelId));
  } catch (err) {
    console.warn("[bpmn] could not read local draft", err);
    return null;
  }
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed === "object" &&
      "xml" in parsed &&
      typeof parsed.xml === "string"
    ) {
      const base = "baseVersionId" in parsed ? parsed.baseVersionId : undefined;
      return {
        xml: parsed.xml,
        baseVersionId: typeof base === "number" || base === null ? base : undefined,
      };
    }
  } catch {
    // Not JSON: a draft from before the version was stored, plain XML.
  }
  return { xml: raw, baseVersionId: undefined };
}

export function writeLocalBpmnDraft(
  bpmnModelId: string,
  xml: string,
  baseVersionId: number | null | undefined,
): void {
  try {
    window.localStorage.setItem(
      getLocalDraftKey(bpmnModelId),
      JSON.stringify({ xml, baseVersionId }),
    );
  } catch (err) {
    console.warn("[bpmn] could not persist local draft", err);
  }
}

export function clearLocalBpmnDraft(bpmnModelId: string): void {
  try {
    window.localStorage.removeItem(getLocalDraftKey(bpmnModelId));
  } catch (err) {
    console.warn("[bpmn] could not clear local draft", err);
  }
}

/**
 * The baseline a restored draft saves against. A draft with no stored base
 * (written before the base was stored), or drafted when the model had no
 * version while it has one now, cannot prove which version it extends: it
 * gets a base no saved version has, so the save answers 409 instead of
 * overwriting.
 */
const UNPROVABLE_BASE = -1;

export function draftBaseVersion(
  draftBase: number | null | undefined,
  serverVersion: number | null,
): number | null {
  if (draftBase === undefined) return UNPROVABLE_BASE;
  if (draftBase === null && serverVersion !== null) return UNPROVABLE_BASE;
  return draftBase;
}
