import { fetchBpmnModel } from "../api";
import { buildInitialProcessDiagram } from "../initialProcessDiagram";

export function downloadBpmn(xml: string, processName: string): void {
  const fileName = `${processName || "processo"}.bpmn`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  const url = URL.createObjectURL(new Blob([xml], { type: "application/xml" }));
  const link = document.createElement("a");

  link.href = url;
  link.download = `${fileName || "processo"}.bpmn`;
  link.click();
  URL.revokeObjectURL(url);
}

export function assertBpmnXml(file: File, xml: string): void {
  const fileName = file.name.toLowerCase();

  if (fileName.endsWith(".bpm") || !xml.trimStart().startsWith("<")) {
    throw new Error(
      "Importa un file BPMN 2.0 XML valido, non un file .bpm proprietario.",
    );
  }
}

export function formatVersionDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export type InitialBpmnModel = {
  xml: string;
  /** The saved version the XML comes from; `null` for the starter diagram. */
  versionId: number | null;
};

/** The model's stored XML and version, or a starter diagram for an empty model. */
export async function loadInitialModel(
  bpmnModelId: string,
  processName: string,
): Promise<InitialBpmnModel> {
  // A failed request is not an empty process. Let the canvas show the error
  // instead of presenting an editable starter model over an existing diagram.
  const model = await fetchBpmnModel(bpmnModelId);
  return {
    xml: model.xml?.trim() || buildInitialProcessDiagram(processName),
    versionId: model.versionId,
  };
}
