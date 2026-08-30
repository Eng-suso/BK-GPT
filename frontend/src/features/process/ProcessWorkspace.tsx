import React from "react";
import { MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { Project, ProjectProcess } from "../../contracts/workspace";
import { ChatExperience } from "../chat/ChatExperience";
import { ProcessBpmnCanvas } from "./ProcessBpmnCanvas";
import { ProcessSimulationPanel } from "./ProcessSimulationPanel";

export type ProcessView = "chat" | "canvas" | "simulation" | "properties";

type ProcessWorkspaceProps = {
  project: Project;
  process: ProjectProcess;
  /** Active view — owned by the route (URL `?view=`). */
  view: ProcessView;
  onViewChange: (view: ProcessView) => void;
};

/**
 * Body of the process studio. The page shell (breadcrumb, title, tab bar)
 * lives in ProcessStudioPage; this component only renders the panels for the
 * active view. bpmn-js lifecycle and the inner ChatExperience are untouched.
 */
export const ProcessWorkspace: React.FC<ProcessWorkspaceProps> = ({
  project,
  process,
  view,
  onViewChange,
}) => {
  const { t } = useTranslation("process");
  const [isCanvasChatOpen, setIsCanvasChatOpen] = React.useState(true);
  const [chatWidth, setChatWidth] = React.useState(380);
  const [isDragging, setIsDragging] = React.useState(false);
  const [currentCanvasXml, setCurrentCanvasXml] = React.useState<string | null>(
    null,
  );
  const propertiesPanelRef = React.useRef<HTMLDivElement | null>(null);

  const handlePointerDown = (e: React.PointerEvent) => {
    setIsDragging(true);
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setChatWidth(Math.max(260, Math.min(e.clientX - rect.left, 600)));
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (!isDragging) return;
    setIsDragging(false);
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  const showStudio = view === "canvas" || view === "properties";

  return (
    <section className="process-workspace process-workspace--embedded">
      {showStudio && (
        <div className="process-workspace-subbar">
          <button
            type="button"
            className={`process-chat-toggle ${isCanvasChatOpen ? "is-active" : ""}`}
            onClick={() => setIsCanvasChatOpen((prev) => !prev)}
            title={t("actions.toggleChat")}
          >
            <MessageSquare aria-hidden width={14} height={14} />
            <span>{t("actions.toggleChat")}</span>
          </button>
        </div>
      )}

      <div className={`process-workspace-grid process-view-${view}`}>
        {showStudio && (
          <div
            className={`process-studio-flex ${isDragging ? "is-dragging" : ""}`}
            aria-label="Studio BPMN"
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
          >
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

            {isCanvasChatOpen && (
              <div
                className={`workspace-splitter ${isDragging ? "is-active" : ""}`}
                onPointerDown={handlePointerDown}
                title="Trascina per ridimensionare la chat"
              >
                <div className="splitter-line" />
              </div>
            )}

            <section
              className="process-studio-canvas"
              style={{ flex: 1, minWidth: 0 }}
              aria-label="Canvas BPMN"
            >
              <ProcessBpmnCanvas
                bpmnModelId={process.bpmnModelId}
                processName={process.name}
                propertiesPanelRef={propertiesPanelRef}
                onCurrentXmlChange={setCurrentCanvasXml}
              />
            </section>

            {view === "properties" && (
              <aside
                className="process-studio-properties"
                style={{ width: "340px", flex: "0 0 340px", marginLeft: "8px" }}
                aria-label="Proprietà BPMN"
              >
                <header className="process-studio-properties-header">
                  <div>
                    <p className="product-eyebrow">BPMN 2.0</p>
                    <h3>Pannello Proprietà</h3>
                  </div>
                  <span>Elemento selezionato</span>
                </header>
                <div
                  className="process-bpmn-properties-host"
                  ref={propertiesPanelRef}
                />
              </aside>
            )}
          </div>
        )}

        {view === "simulation" && (
          <section
            className="process-simulation-panel"
            aria-label="Simulazione processo"
          >
            <ProcessSimulationPanel
              process={process}
              currentBpmnXml={currentCanvasXml}
            />
          </section>
        )}

        {view === "chat" && (
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
                onOpenCanvas={() => onViewChange("canvas")}
                onOpenProperties={() => onViewChange("properties")}
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
