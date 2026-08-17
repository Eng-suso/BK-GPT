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
  const [activeView, setActiveView] = React.useState<ProcessView>("chat");
  const [currentCanvasXml, setCurrentCanvasXml] = React.useState<string | null>(null);
  const propertiesPanelRef = React.useRef<HTMLDivElement | null>(null);
  const isBpmnView = activeView === "canvas" || activeView === "properties";

  return (
    <section className="process-workspace">
      <header className="project-workspace-header">
        <div className="project-title-group">
          <button type="button" className="project-back-button" onClick={onBack}>
            Indietro
          </button>
          <div>
            <p className="product-eyebrow">{project.name}</p>
            <h2>{process.name}</h2>
          </div>
        </div>

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
      </header>

      <div className={`process-workspace-grid process-view-${activeView}`}>
        {isBpmnView ? (
          <div className="process-studio" aria-label="Studio processo">
            <section className="process-studio-chat" aria-label="Chat canvas">
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

            <section className="process-studio-canvas" aria-label="Canvas BPMN">
              <ProcessBpmnCanvas
                bpmnModelId={process.bpmnModelId}
                processName={process.name}
                propertiesPanelRef={propertiesPanelRef}
                onCurrentXmlChange={setCurrentCanvasXml}
              />
            </section>

            <aside className="process-studio-properties" aria-label="Proprieta BPMN">
              <header className="process-studio-properties-header">
                <div>
                  <p className="product-eyebrow">BPMN 2.0</p>
                  <h3>Proprieta</h3>
                </div>
                <span>{activeView === "properties" ? "Attivo" : "Pannello"}</span>
              </header>
              <div className="process-bpmn-properties-host" ref={propertiesPanelRef} />
            </aside>
          </div>
        ) : (
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
