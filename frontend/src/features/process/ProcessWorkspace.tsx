import React from "react";
import { MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";
import { DetailPanelKeyValue } from "@/components/panel";
import type { Project, ProjectProcess } from "../../contracts/workspace";
import { ChatExperience } from "../chat/ChatExperience";
import { ProcessBpmnCanvas } from "./ProcessBpmnCanvas";
import { SimulationWorkspace } from "./SimulationWorkspace";

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
          <Button
            type="button"
            variant={isCanvasChatOpen ? "secondary" : "outline"}
            size="sm"
            onClick={() => setIsCanvasChatOpen((prev) => !prev)}
            title={t("actions.toggleChat")}
          >
            <MessageSquare aria-hidden className="size-3.5" />
            {t("actions.toggleChat")}
          </Button>
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
                <header className="flex min-h-14 items-center justify-between gap-3 border-b border-border px-3.5 py-3">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                      BPMN 2.0
                    </p>
                    <h3 className="mt-0.5 text-sm font-semibold text-foreground">
                      Pannello Proprietà
                    </h3>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    Elemento selezionato
                  </span>
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
            <SimulationWorkspace
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
    <div className="flex flex-col gap-3.5 p-3.5">
      <SidePanel title="Riepilogo">
        <DetailPanelKeyValue
          rows={[
            { label: "Stato", value: process.status },
            { label: "Owner", value: process.owner },
            { label: "Fase", value: process.stage },
            { label: "Readiness", value: `${process.readiness}%` },
          ]}
        />
      </SidePanel>

      <SidePanel title="Transizione">
        <p className="text-[12.5px] leading-relaxed text-muted-foreground">
          Parti dalla chat generale del processo, passa al canvas BPMN quando vuoi
          lavorare sul modello, poi apri le proprieta per modificare gli elementi.
        </p>
        <div className="mt-3.5 grid gap-2">
          <Button variant="outline" size="sm" onClick={onOpenCanvas}>
            Apri canvas
          </Button>
          <Button variant="outline" size="sm" onClick={onOpenProperties}>
            Apri proprieta
          </Button>
        </div>
      </SidePanel>

      <SidePanel title="Qualita">
        <ul className="grid gap-2 text-[12px] font-medium text-muted-foreground">
          <li className="rounded-md bg-muted/60 px-2.5 py-2">Fonti collegate</li>
          <li className="rounded-md bg-muted/60 px-2.5 py-2">Ruoli verificati</li>
          <li className="rounded-md bg-muted/60 px-2.5 py-2">
            Eccezioni da completare
          </li>
        </ul>
      </SidePanel>
    </div>
  );
}

function SidePanel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-card p-4 shadow-[0_1px_2px_var(--shadow-100)]">
      <h3 className="mb-2 text-sm font-semibold text-foreground">{title}</h3>
      {children}
    </section>
  );
}
