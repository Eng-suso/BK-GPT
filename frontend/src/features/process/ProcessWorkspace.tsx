import React from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { PanelShellHeader } from "@/components/panel";
import { ResizeHandle } from "@/components/layout";
import { Button } from "@/ui/button";
import { usePanelSize } from "@/lib/usePanelSize";
import { useElementWidth } from "@/lib/useElementWidth";
import type { Project, ProjectProcess } from "@/contracts/workspace";
import { ChatExperience } from "../chat/ChatExperience";
import { ProcessBpmnCanvas } from "./ProcessBpmnCanvas";

export type ProcessView = "chat" | "canvas";
type ProcessWorkspaceProps = {
  project: Project;
  process: ProjectProcess;
  view: ProcessView;
  propertiesOpen: boolean;
  onTogglePropertiesPanel: () => void;
  /** Switches to the discussion view — where an empty model gets reconstructed. */
  onOpenDiscussion: () => void;
};

/**
 * Renders the process workspace with the BPMN canvas, chat panel, or properties panel for the selected view.
 *
 * @param project - The project containing the process.
 * @param process - The process displayed in the workspace.
 * @param view - The active workspace view.
 * @param propertiesOpen - Whether the properties panel is open.
 * @param onTogglePropertiesPanel - Toggles the properties panel.
 * @returns The process workspace element.
 */
export function ProcessWorkspace({ project, process, view, propertiesOpen, onTogglePropertiesPanel, onOpenDiscussion }: ProcessWorkspaceProps): React.JSX.Element {
  const { t } = useTranslation("process");
  const { ref, width } = useElementWidth<HTMLElement>();
  const [chatOpen, setChatOpen] = React.useState(false);
  const [chatWidth, setChatWidth] = usePanelSize("process-chat", 360, 320, 480);
  const dragStart = React.useRef(0);
  const [currentCanvasXml, setCurrentCanvasXml] = React.useState<string | null>(null);
  const propertiesPanelRef = React.useRef<HTMLDivElement | null>(null);
  // A support pane is inline only when at least 720 px remain for the model.
  const inline = width >= 1090;
  const availableChatWidth = Math.min(chatWidth, Math.max(320, width - 730));
  const bothFit = width >= availableChatWidth + 360 + 740;
  const showChat = chatOpen && (!propertiesOpen || bothFit);
  const supportReplacesCanvas = !inline && (showChat || propertiesOpen);
  const lastTrigger = React.useRef<HTMLElement | null>(null);
  const closeRef = React.useRef<HTMLButtonElement | null>(null);

  React.useEffect(() => {
    if (supportReplacesCanvas) closeRef.current?.focus();
  }, [supportReplacesCanvas]);

  const closeSupport = () => {
    setChatOpen(false);
    if (propertiesOpen) onTogglePropertiesPanel();
    requestAnimationFrame(() => lastTrigger.current?.focus());
  };
  const toggleChat = () => {
    lastTrigger.current = document.activeElement as HTMLElement | null;
    if (!showChat && propertiesOpen && !bothFit) onTogglePropertiesPanel();
    setChatOpen(!showChat);
  };
  const toggleProperties = () => {
    lastTrigger.current = document.activeElement as HTMLElement | null;
    if (!propertiesOpen && !bothFit) setChatOpen(false);
    onTogglePropertiesPanel();
  };

  return (
    <section ref={ref} className="process-workspace process-workspace--embedded" onKeyDown={(event) => {
      if (event.key === "Escape" && supportReplacesCanvas) { event.preventDefault(); closeSupport(); }
    }}>
      <div className={`process-workspace-grid process-view-${view}`}>
        {view === "canvas" ? (
          <div className="process-studio-flex" aria-label="Studio BPMN">
            {showChat && <>
              <section className="process-studio-chat flex flex-col" style={{ width: inline ? availableChatWidth : "100%", flex: inline ? `0 0 ${availableChatWidth}px` : "1" }} aria-label={t("actions.toggleChat")}>
                <div className="flex h-10 shrink-0 items-center justify-between border-b border-border px-3">
                  <span className="text-xs font-medium">{t("actions.toggleChat")}</span>
                  <Button ref={!propertiesOpen ? closeRef : undefined} variant="ghost" size="icon-sm" aria-label={t("actions.closeOverlays")} onClick={closeSupport}><X className="size-4" /></Button>
                </div>
                <div className="min-h-0 flex-1">
                  <ChatExperience chrome="panel" layout="embedded" scope={{ type: "canvas", projectId: project.id, processId: process.id, bpmnModelId: process.bpmnModelId, processName: process.name, currentBpmnXml: currentCanvasXml }} />
                </div>
              </section>
              {inline && <ResizeHandle ariaLabel={t("actions.toggleChat")} onResizeStart={() => (dragStart.current = availableChatWidth)} onDelta={(dx) => setChatWidth(Math.min(dragStart.current + dx, width - 730))} onStep={(dx) => setChatWidth(Math.min(availableChatWidth + dx, width - 730))} valueNow={availableChatWidth} valueMin={320} valueMax={Math.min(480, width - 730)} />}
            </>}
            <section className="process-studio-canvas" style={{ flex: 1, minWidth: 0 }} hidden={supportReplacesCanvas} aria-label="Canvas BPMN">
              <ProcessBpmnCanvas bpmnModelId={process.bpmnModelId} processName={process.name} propertiesPanelRef={propertiesPanelRef} onCurrentXmlChange={setCurrentCanvasXml} onOpenDiscussion={onOpenDiscussion} isCanvasChatOpen={showChat} onToggleCanvasChat={toggleChat} isPropertiesOpen={propertiesOpen} onTogglePropertiesPanel={toggleProperties} />
            </section>
            <aside className="process-studio-properties" style={{ width: inline ? 360 : "100%", flex: inline ? "0 0 360px" : "1", marginLeft: inline ? 12 : 0 }} aria-label={t("properties.title")} hidden={!propertiesOpen}>
              <PanelShellHeader title={t("properties.title")} actions={<Button ref={propertiesOpen ? closeRef : undefined} variant="ghost" size="icon-sm" aria-label={t("actions.closeOverlays")} onClick={closeSupport}><X className="size-4" /></Button>} />
              {/* The host must remain mounted for the modeler's properties provider. */}
              <div className="process-bpmn-properties-host" ref={propertiesPanelRef} />
            </aside>
          </div>
        ) : (
          <section className="process-primary-panel" aria-label="Chat processo">
            <ChatExperience chrome="panel" layout="embedded" scope={{ type: "process", projectId: project.id, processId: process.id, processName: process.name, bpmnModelId: process.bpmnModelId }} />
          </section>
        )}
      </div>
    </section>
  );
}
