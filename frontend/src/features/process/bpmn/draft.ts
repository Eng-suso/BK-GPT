/** Best-effort local persistence of unsaved canvas edits, keyed per model. */

function getLocalDraftKey(bpmnModelId: string): string {
  return `workspace:bpmn-draft:${bpmnModelId}`;
}

export function readLocalBpmnDraft(bpmnModelId: string): string | null {
  try {
    return window.localStorage.getItem(getLocalDraftKey(bpmnModelId));
  } catch (err) {
    console.warn("[bpmn] could not read local draft", err);
    return null;
  }
}

export function writeLocalBpmnDraft(bpmnModelId: string, xml: string): void {
  try {
    window.localStorage.setItem(getLocalDraftKey(bpmnModelId), xml);
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
