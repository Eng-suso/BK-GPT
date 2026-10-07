import React from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { WorkspaceInspector, WorkspaceResizeSeparator } from "@/components/layout/CanvasWorkspace";
import { Button } from "@/ui/button";
import { usePanelSize } from "@/lib/usePanelSize";
import { useElementWidth } from "@/lib/useElementWidth";
import type { Project, ProjectProcess } from "@/contracts/workspace";
import { ChatExperience } from "../chat/ChatExperience";
import { ProcessBpmnCanvas } from "./ProcessBpmnCanvas";
import { ProcessReviewWorkspace } from "./review/ProcessReviewWorkspace";

export type ProcessView = "chat" | "canvas" | "review" | "tobe";
type ProcessWorkspaceProps = {
  project: Project;
  process: ProjectProcess;
  view: ProcessView;
  propertiesOpen: boolean;
  onTogglePropertiesPanel: () => void;
  /** Switches to the discussion view — where an empty model gets reconstructed. */
  onOpenDiscussion: () => void;
  onReviewModeChange: (mode: "canvas" | "review" | "tobe") => void;
  onOpenSimulation: () => void;
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
export function ProcessWorkspace(props: ProcessWorkspaceProps): React.JSX.Element {
  if (props.view === "review" || props.view === "tobe") return <ProcessReviewWorkspace key={props.process.id} processId={props.process.id} bpmnModelId={props.process.bpmnModelId} mode={props.view} onModeChange={props.onReviewModeChange} onSimulation={props.onOpenSimulation} />;
  return <ModelingProcessWorkspace {...props} />;
}

function ModelingProcessWorkspace({ project, process, view, propertiesOpen, onTogglePropertiesPanel, onOpenDiscussion }: ProcessWorkspaceProps): React.JSX.Element {
  const { t } = useTranslation("process");
  const { ref, width } = useElementWidth<HTMLElement>();
  const [chatOpen, setChatOpen] = React.useState(false);
  const [chatWidth, setChatWidth] = usePanelSize("process-chat", 360, 320, 480);
  const [inspectorCloseLabel, setInspectorCloseLabel] = React.useState<string | null>(null);
  const [inspectorTitle, setInspectorTitle] = React.useState<string | null>(null);
  const inspectorClose = React.useRef<(() => void) | null>(null);
  const inspectorHost = React.useRef<HTMLDivElement | null>(null);
  const onInspectorChange = React.useCallback((inspector: { title: string; closeLabel: string; close: () => void } | null) => { inspectorClose.current = inspector?.close ?? null; setInspectorTitle(inspector?.title ?? null); setInspectorCloseLabel(inspector?.closeLabel ?? null); }, []);
  const [currentCanvasXml, setCurrentCanvasXml] = React.useState<string | null>(null);
  const [currentCanvasVersionId, setCurrentCanvasVersionId] = React.useState<number | null>(null);
  const propertiesPanelRef = React.useRef<HTMLDivElement | null>(null);
  // A support pane is inline only when at least 720 px remain for the model.
  const inline = width >= 1090;
  const availableChatWidth = Math.min(chatWidth, Math.max(320, width - 792));
  const bothFit = width >= availableChatWidth + 480 + 792;
  const showChat = chatOpen && (!propertiesOpen || bothFit);
  const detailsOpen = Boolean(inspectorTitle) && (!showChat || bothFit);
  const rightOpen = propertiesOpen || detailsOpen;
  const supportReplacesCanvas = !inline && (showChat || propertiesOpen);
  const lastTrigger = React.useRef<HTMLElement | null>(null);
  const closeRef = React.useRef<HTMLButtonElement | null>(null);

  const restoreSupportFocus = React.useRef(false);
  React.useLayoutEffect(() => {
    if (supportReplacesCanvas) (closeRef.current ?? ref.current?.querySelector<HTMLButtonElement>(`.process-studio-properties button[aria-label="${CSS.escape(t("actions.closeOverlays"))}"]`))?.focus();
    else if (restoreSupportFocus.current && !propertiesOpen && !showChat) {
      restoreSupportFocus.current = false;
      lastTrigger.current?.focus({ preventScroll: true });
    }
  }, [supportReplacesCanvas, propertiesOpen, showChat, ref, t]);

  const closeSupport = () => {
    restoreSupportFocus.current = true;
    setChatOpen(false);
    if (propertiesOpen) onTogglePropertiesPanel();
  };
  const closeInspector = () => { if (propertiesOpen) closeSupport(); else { inspectorClose.current?.(); ref.current?.querySelector<HTMLButtonElement>(`button[aria-label="${CSS.escape(t("actions.toggleProperties"))}"]`)?.focus({ preventScroll: true }); } };
  const toggleChat = () => {
    lastTrigger.current = ref.current?.querySelector<HTMLElement>(`button[aria-label="${CSS.escape(t("actions.toggleChat"))}"]`) ?? document.activeElement as HTMLElement | null;
    if (!showChat && propertiesOpen && !bothFit) onTogglePropertiesPanel();
    setChatOpen(!showChat);
  };
  const toggleProperties = () => {
    lastTrigger.current = ref.current?.querySelector<HTMLElement>(`button[aria-label="${CSS.escape(t("actions.toggleProperties"))}"]`) ?? document.activeElement as HTMLElement | null;
    if (!propertiesOpen && !bothFit) setChatOpen(false);
    onTogglePropertiesPanel();
  };

  return (
    <section ref={ref} className="process-workspace process-workspace--embedded" onKeyDown={(event) => {
      if (event.key === "Escape" && supportReplacesCanvas) { event.preventDefault(); closeSupport(); }
    }}>
      <div className={`process-workspace-grid process-view-${view}`}>
        {view === "canvas" ? (
          <div className={`process-studio-flex ${!inline && detailsOpen && !propertiesOpen ? "process-studio-flex--stacked" : ""}`} aria-label="Studio BPMN">
            {showChat && <>
              <section className="process-studio-chat flex flex-col" style={{ width: inline ? availableChatWidth : "100%", flex: inline ? `0 0 ${availableChatWidth}px` : "1" }} aria-label={t("actions.toggleChat")}>
                <div className="flex h-10 shrink-0 items-center justify-between border-b border-border px-3">
                  <span className="text-xs font-medium">{t("actions.toggleChat")}</span>
                  <Button ref={!propertiesOpen ? closeRef : undefined} variant="ghost" size="icon-sm" aria-label={t("actions.closeOverlays")} onClick={closeSupport}><X className="size-4" /></Button>
                </div>
                <div className="min-h-0 flex-1">
                  <ChatExperience chrome="panel" layout="embedded" scope={{ type: "canvas", projectId: project.id, processId: process.id, bpmnModelId: process.bpmnModelId, processName: process.name, currentBpmnXml: currentCanvasXml, currentBpmnVersionId: currentCanvasVersionId }} />
                </div>
              </section>
              {inline && <div className="process-chat-resize"><WorkspaceResizeSeparator label={t("actions.toggleChat")} value={availableChatWidth} minimum={320} maximum={Math.min(480, width - 792)} edge="end" onResize={setChatWidth} /></div>}
            </>}
            <section className="process-studio-canvas" style={{ flex: 1, minWidth: 0 }} hidden={supportReplacesCanvas} aria-label="Canvas BPMN">
              <ProcessBpmnCanvas bpmnModelId={process.bpmnModelId} processId={process.id} processName={process.name} propertiesPanelRef={propertiesPanelRef} inspectorHost={inspectorHost} onInspectorChange={onInspectorChange} onCurrentXmlChange={setCurrentCanvasXml} onBaseVersionChange={setCurrentCanvasVersionId} onOpenDiscussion={onOpenDiscussion} isCanvasChatOpen={showChat} onToggleCanvasChat={toggleChat} isPropertiesOpen={propertiesOpen} onTogglePropertiesPanel={toggleProperties} />
            </section>
            <WorkspaceInspector label={t("properties.title")} title={propertiesOpen ? t("properties.title") : inspectorTitle ?? t("properties.title")} closeLabel={propertiesOpen ? t("actions.closeOverlays") : inspectorCloseLabel ?? t("actions.closeOverlays")} onClose={closeInspector} hidden={!rightOpen} resizeLabel={inline ? t("actions.resizeInspector") : undefined} initialWidth={360} maximumWidth={480} minimumStageWidth={784 + (showChat && inline ? availableChatWidth + 12 : 0)} className={`process-studio-properties ${inline ? "" : "process-studio-properties--compact"}`} bodyClassName="process-inspector-body">
              {/* Both hosts stay mounted: opening a pane must not rebuild the modeler. */}
              <div className="process-bpmn-properties-host ui-scrollbar" ref={propertiesPanelRef} hidden={!propertiesOpen} />
              <div ref={inspectorHost} className="process-detail-host ui-scrollbar" hidden={propertiesOpen} />
            </WorkspaceInspector>
          </div>
        ) : (
          <section className="process-primary-panel" aria-label={t("canvas.processChat")}>
            <ChatExperience chrome="panel" layout="embedded" scope={{ type: "process", projectId: project.id, processId: process.id, processName: process.name, bpmnModelId: process.bpmnModelId }} />
          </section>
        )}
      </div>
    </section>
  );
}
