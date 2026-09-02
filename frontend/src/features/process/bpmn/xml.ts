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

/** The model's stored XML, or a fresh starter diagram if it can't be loaded. */
export async function loadInitialXml(
  bpmnModelId: string,
  processName: string,
): Promise<string> {
  const fallbackXml = buildInitialProcessDiagram(processName);

  try {
    const model = await fetchBpmnModel(bpmnModelId);
    return model.xml?.trim() || fallbackXml;
  } catch (err) {
    console.warn("[bpmn] model load failed, using starter diagram", err);
    return fallbackXml;
  }
}
