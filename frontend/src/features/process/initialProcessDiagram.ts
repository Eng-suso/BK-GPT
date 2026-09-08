function xmlText(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

/**
 * The diagram a process starts from: its own name, and nothing else.
 *
 * It used to open on a ready-made "Raccolta dati → Validazione → Decisione"
 * chain. Nobody had described that process, so the canvas showed a plausible
 * invention as if it were the client's reconstruction — and the consultant had
 * to delete it before starting. An empty model says the truth: the process is
 * still to be reconstructed, and that starts from the discussion.
 *
 * @param processName - The process name, written onto the empty BPMN process
 * @returns The BPMN 2.0 XML of an empty, valid diagram
 */
export function buildInitialProcessDiagram(processName: string) {
  const name = xmlText(processName || "Processo");

  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Process_Workspace" targetNamespace="https://workspace.local/bpmn">
  <bpmn:process id="Process_Workspace" name="${name}" isExecutable="false" />
  <bpmndi:BPMNDiagram id="BPMNDiagram_Process_Workspace">
    <bpmndi:BPMNPlane id="BPMNPlane_Process_Workspace" bpmnElement="Process_Workspace" />
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`;
}
