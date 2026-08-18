import React from "react";
import { ChatExperience } from "../chat/ChatExperience";
import type { Project, ProjectProcess } from "../projects/projectData";
import { ProcessBpmnCanvas } from "./ProcessBpmnCanvas";

type ProcessWorkspaceProps = {
  project: Project;
  process: ProjectProcess;
  onBack: () => void;
};

type ProcessView = "chat" | "canvas" | "properties";

const processViews: Array<{ id: ProcessView; label: string }> = [
  { id: "chat", label: "Chat" },
  { id: "canvas", label: "Canvas" },
  { id: "properties", label: "Proprieta" },
];

export const ProcessWorkspace: React.FC<ProcessWorkspaceProps> = ({ project, process, onBack }) => {
  const [activeView, setActiveView] = React.useState<ProcessView>("canvas");
  const [isCanvasChatOpen, setIsCanvasChatOpen] = React.useState(true);
  const [chatWidth, setChatWidth] = React.useState(380);
  const [isDragging, setIsDragging] = React.useState(false);
  const [currentCanvasXml, setCurrentCanvasXml] = React.useState<string | null>(null);
  const propertiesPanelRef = React.useRef<HTMLDivElement | null>(null);

  const handlePointerDown = (e: React.PointerEvent) => {
    setIsDragging(true);
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging) return;
    const containerRect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const newWidth = Math.max(260, Math.min(e.clientX - containerRect.left, 600));
    setChatWidth(newWidth);
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (isDragging) {
      setIsDragging(false);
      try {
        (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        // ignore
      }
    }
  };

  return (
    <section className="process-workspace">
      <header className="project-workspace-header">
        <div className="project-title-group">
          <button type="button" className="project-back-button" onClick={onBack} title="Torna ai processi del progetto">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
            <span>Indietro</span>
          </button>
          <div>
            <p className="product-eyebrow">Progetti &rsaquo; {project.name}</p>
            <h2>{process.name}</h2>
          </div>
        </div>

        <div className="process-workspace-header-actions">
          {(activeView === "canvas" || activeView === "properties") && (
            <button
              type="button"
              className={`process-chat-toggle ${isCanvasChatOpen ? "is-active" : ""}`}
              onClick={() => setIsCanvasChatOpen((prev) => !prev)}
              title={isCanvasChatOpen ? "Nascondi Chat Canvas" : "Mostra Chat Canvas"}
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              <span>Chat Canvas</span>
            </button>
          )}

          <nav className="process-view-switch" aria-label="Viste processo">
            {processViews.map((view) => (
              <button
                key={view.id}
                type="button"
                className={activeView === view.id ? "is-active" : ""}
                onClick={() => setActiveView(view.id)}
              >
                {view.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <div className={`process-workspace-grid process-view-${activeView}`}>
        {(activeView === "canvas" || activeView === "properties") && (
          <div
            className={`process-studio-flex ${isDragging ? "is-dragging" : ""}`}
            aria-label="Studio BPMN"
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
          >
            {/* 1. LEFT PANEL: Chat Canvas (if open) */}
            {isCanvasChatOpen && (
              <section
                className="process-studio-chat"
                style={{ width: `${chatWidth}px`, flex: `0 0 ${chatWidth}px` }}
                aria-label="Chat canvas"
              >
                <ChatExperience
                  chrome="panel"
                  layout="embedded"
                  scope={{
                    type: "canvas",
                    projectId: project.id,
                    processId: process.id,
                    bpmnModelId: process.bpmnModelId,
                    processName: process.name,
                    currentBpmnXml: currentCanvasXml,
                  }}
                />
              </section>
            )}

            {/* 2. RESIZABLE HANDLE */}
            {isCanvasChatOpen && (
              <div
                className={`workspace-splitter ${isDragging ? "is-active" : ""}`}
                onPointerDown={handlePointerDown}
                title="Trascina per ridimensionare la chat"
              >
                <div className="splitter-line" />
              </div>
            )}

            {/* 3. CENTER / MAIN PANEL: Canvas BPMN */}
            <section className="process-studio-canvas" style={{ flex: 1, minWidth: 0 }} aria-label="Canvas BPMN">
              <ProcessBpmnCanvas
                bpmnModelId={process.bpmnModelId}
                processName={process.name}
                propertiesPanelRef={propertiesPanelRef}
                onCurrentXmlChange={setCurrentCanvasXml}
              />
            </section>

            {/* 4. RIGHT PANEL: BPMN Properties (if in properties view) */}
            {activeView === "properties" && (
              <aside className="process-studio-properties" style={{ width: "340px", flex: "0 0 340px", marginLeft: "8px" }} aria-label="Proprietà BPMN">
                <header className="process-studio-properties-header">
                  <div>
                    <p className="product-eyebrow">BPMN 2.0</p>
                    <h3>Pannello Proprietà</h3>
                  </div>
                  <span>Elemento selezionato</span>
                </header>
                <div className="process-bpmn-properties-host" ref={propertiesPanelRef} />
              </aside>
            )}
          </div>
        )}

        {activeView === "chat" && (
          <>
            <section className="process-primary-panel" aria-label="Chat processo">
              <ChatExperience
                chrome="panel"
                layout="embedded"
                scope={{
                  type: "process",
                  projectId: project.id,
                  processId: process.id,
                  processName: process.name,
                }}
              />
            </section>

            <aside className="process-side-panel" aria-label="Pannello processo">
              <ProcessSideSummary
                process={process}
                onOpenCanvas={() => setActiveView("canvas")}
                onOpenProperties={() => setActiveView("properties")}
              />
            </aside>
          </>
        )}
      </div>
    </section>
  );
};

function ProcessSideSummary({
  process,
  onOpenCanvas,
  onOpenProperties,
}: {
  process: ProjectProcess;
  onOpenCanvas: () => void;
  onOpenProperties: () => void;
}) {
  return (
    <div className="process-side-summary">
      <section className="project-panel">
        <h3>Riepilogo</h3>
        <dl className="process-property-list">
          <div><dt>Stato</dt><dd>{process.status}</dd></div>
          <div><dt>Owner</dt><dd>{process.owner}</dd></div>
          <div><dt>Fase</dt><dd>{process.stage}</dd></div>
          <div><dt>Readiness</dt><dd>{process.readiness}%</dd></div>
        </dl>
      </section>

      <section className="project-panel">
        <h3>Transizione</h3>
        <p>
          Parti dalla chat generale del processo, passa al canvas BPMN quando vuoi
          lavorare sul modello, poi apri le proprieta per modificare gli elementi.
        </p>
        <div className="process-transition-actions">
          <button type="button" onClick={onOpenCanvas}>Apri canvas</button>
          <button type="button" onClick={onOpenProperties}>Apri proprieta</button>
        </div>
      </section>

      <section className="project-panel">
        <h3>Qualita</h3>
        <ul className="process-check-list">
          <li>Fonti collegate</li>
          <li>Ruoli verificati</li>
          <li>Eccezioni da completare</li>
        </ul>
      </section>
    </div>
  );
}
