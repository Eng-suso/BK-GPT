import "../bpmn/canvasIdentity.css";
import { DelirLogo } from "@/components/brand/DelirLogo";

/** Product identity belongs to the canvas chrome, never the BPMN XML. */
export function BpmnCanvasIdentity() {
  return <div className="delir-canvas-identity"><DelirLogo className="text-[16px] opacity-80" /></div>;
}
