import React from "react";
import { useTranslation } from "react-i18next";

import { PanelShellHeader } from "@/components/panel";
import { ResizeHandle } from "@/components/layout";
import { usePanelSize } from "@/lib/usePanelSize";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { cn } from "@/lib/utils";
import type { Project, ProjectProcess } from "../../contracts/workspace";
import { ChatExperience } from "../chat/ChatExperience";
import { ProcessBpmnCanvas } from "./ProcessBpmnCanvas";
import { SimulationWorkspace } from "./SimulationWorkspace";

export type ProcessView = "chat" | "canvas" | "simulation";

type ProcessWorkspaceProps = {
  project: Project;
  process: ProjectProcess;
  /** Active view — owned by the route (URL `?view=`). */
  view: ProcessView;
  /** BPMN properties dock — owned by the route (URL `?panel=properties`). */
  propertiesOpen: boolean;
  onTogglePropertiesPanel: () => void;
};

/**
 * Body of the process studio. The page shell (breadcrumb, title, meta, tab bar)
 * lives in ProcessStudioPage; this component only renders the panels for the
 * active view. bpmn-js lifecycle and the inner ChatExperience are untouched.
 *
 * Below 1280px the model view has no room for three side-by-side columns, so
 * the chat rail and the properties dock become overlay drawers over a
 * full-bleed canvas.
 */
export const ProcessWorkspace: React.FC<ProcessWorkspaceProps> = ({
  project,
  process,
  view,
  propertiesOpen,
  onTogglePropertiesPanel,
}) => {
  const { t } = useTranslation("process");
  const compact = useMediaQuery("(max-width: 1280px)");
  // The model view's chat rail is inline on wide screens and an overlay drawer
  // below 1280px — where it starts closed so the canvas is usable straight away.
  const [isCanvasChatOpen, setIsCanvasChatOpen] = React.useState(!compact);
  const [chatWidth, setChatWidth] = usePanelSize(
    `process-chat:${process.bpmnModelId}`,
    380,
    260,
    600,
  );
  const dragStart = React.useRef(0);
  const [currentCanvasXml, setCurrentCanvasXml] = React.useState<string | null>(
    null,
  );
  const propertiesPanelRef = React.useRef<HTMLDivElement | null>(null);

  const wasCompact = React.useRef(compact);
  React.useEffect(() => {
    if (compact !== wasCompact.current) {
      setIsCanvasChatOpen(!compact);
      wasCompact.current = compact;
    }
  }, [compact]);

  const dismissOverlays = React.useCallback(() => {
    setIsCanvasChatOpen(false);
    if (propertiesOpen) onTogglePropertiesPanel();
  }, [propertiesOpen, onTogglePropertiesPanel]);

  const overlayOpen = compact && (isCanvasChatOpen || propertiesOpen);

  return (
    <section className="process-workspace process-workspace--embedded">
      <div className={`process-workspace-grid process-view-${view}`}>
        {view === "canvas" && (
          <div
            className={cn(
              "process-studio-flex",
              compact && "process-studio-flex--compact",
            )}
            aria-label="Studio BPMN"
          >
            {overlayOpen && (
              <button
                type="button"
                className="process-studio-scrim"
                aria-label={t("actions.closeOverlays")}
                onClick={dismissOverlays}
              />
            )}

            {isCanvasChatOpen && (
              <>
                <section
                  className={cn(
                    "process-studio-chat",
                    compact && "process-studio-chat--overlay",
                  )}
                  style={
                    compact
                      ? undefined
                      : { width: chatWidth, flex: `0 0 ${chatWidth}px` }
                  }
                  aria-label={t("actions.toggleChat")}
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
                {!compact && (
                  <ResizeHandle
                    ariaLabel={t("actions.toggleChat")}
                    onResizeStart={() => (dragStart.current = chatWidth)}
                    onDelta={(dx) => setChatWidth(dragStart.current + dx)}
                  />
                )}
              </>
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
                isCanvasChatOpen={isCanvasChatOpen}
                onToggleCanvasChat={() => setIsCanvasChatOpen((prev) => !prev)}
                isPropertiesOpen={propertiesOpen}
                onTogglePropertiesPanel={onTogglePropertiesPanel}
              />
            </section>

            {/*
              The properties host stays mounted so bpmn-js keeps its panel
              attached; `hidden` toggles only its visibility / layout.
            */}
            <aside
              className={cn(
                "process-studio-properties",
                compact && "process-studio-properties--overlay",
              )}
              style={
                compact ? undefined : { width: 340, flex: "0 0 340px", marginLeft: 8 }
              }
              aria-label={t("properties.title")}
              hidden={!propertiesOpen}
            >
              <PanelShellHeader
                eyebrow={t("properties.eyebrow")}
                title={t("properties.title")}
                actions={
                  <span className="text-xs text-muted-foreground">
                    {t("properties.hint")}
                  </span>
                }
              />
              <div
                className="process-bpmn-properties-host"
                ref={propertiesPanelRef}
              />
            </aside>
          </div>
        )}

        {view === "simulation" && (
          <section
            className="process-simulation-panel"
            aria-label={t("simulation.diagram.title")}
          >
            <SimulationWorkspace
              process={process}
              currentBpmnXml={currentCanvasXml}
            />
          </section>
        )}

        {view === "chat" && (
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
        )}
      </div>
    </section>
  );
};
