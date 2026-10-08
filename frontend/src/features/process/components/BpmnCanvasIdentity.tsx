import "../bpmn/canvasIdentity.css";

/** Product identity belongs to the canvas chrome, never the BPMN XML. */
export function BpmnCanvasIdentity() {
  return <div className="delir-canvas-identity" aria-label="DeliR"><svg viewBox="0 0 32 32" aria-hidden="true" focusable="false"><path d="M6 4h9c8 0 13 4 13 12s-5 12-13 12H6Z" fill="none" stroke="currentColor" strokeWidth="2" /><path d="M6 4h5v24H6Zm12 0v8h9" fill="currentColor" /><path d="M18 4v8h9" fill="none" stroke="currentColor" strokeWidth="2" /></svg><span>DeliR</span></div>;
}
