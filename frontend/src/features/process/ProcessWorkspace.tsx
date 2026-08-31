import React from "react";
import { useTranslation } from "react-i18next";

import { PanelShellHeader } from "@/components/panel";
import { EmptyState } from "@/components/feedback";
import { Meter } from "@/components/data";
import { ResizeHandle } from "@/components/layout";
import { usePanelSize } from "@/lib/usePanelSize";
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
 * Body of the process studio. The page shell (breadcrumb, title, tab bar)
 * lives in ProcessStudioPage; this component only renders the panels for the
 * active view. bpmn-js lifecycle and the inner ChatExperience are untouched.
 */
export const ProcessWorkspace: React.FC<ProcessWorkspaceProps> = ({
  project,
  process,
  view,
  propertiesOpen,
  onTogglePropertiesPanel,
}) => {
  const { t } = useTranslation("process");
  const [isCanvasChatOpen, setIsCanvasChatOpen] = React.useState(true);
  const CHAT_MIN = 300;
  const CHAT_MAX = 600;
  // One remembered width for the canvas chat, not one per model.
  const [chatWidth, setChatWidth] = usePanelSize(
    "process-chat",
    380,
    CHAT_MIN,
    CHAT_MAX,
  );
  const dragStart = React.useRef(0);
  const [currentCanvasXml, setCurrentCanvasXml] = React.useState<string | null>(
    null,
  );
  const propertiesPanelRef = React.useRef<HTMLDivElement | null>(null);

  return (
    <section className="process-workspace process-workspace--embedded">
      <div className={`process-workspace-grid process-view-${view}`}>
        {view === "canvas" && (
          <div className="process-studio-flex" aria-label="Studio BPMN">
            {isCanvasChatOpen && (
              <>
                <section
                  className="process-studio-chat"
                  style={{ width: chatWidth, flex: `0 0 ${chatWidth}px` }}
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
                <ResizeHandle
                  ariaLabel={t("actions.toggleChat")}
                  onResizeStart={() => (dragStart.current = chatWidth)}
                  onDelta={(dx) => setChatWidth(dragStart.current + dx)}
                  onStep={(dx) => setChatWidth(chatWidth + dx)}
                  valueNow={chatWidth}
                  valueMin={CHAT_MIN}
                  valueMax={CHAT_MAX}
                />
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
              className="process-studio-properties"
              style={{ width: 340, flex: "0 0 340px", marginLeft: 8 }}
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
              <ProcessSideSummary process={process} />
            </aside>
          </>
        )}
      </div>
    </section>
  );
};

function ProcessSideSummary({ process }: { process: ProjectProcess }) {
  const { t } = useTranslation("process");
  return (
    <div className="flex flex-col gap-4 p-6">
      <SidePanel title={t("side.summary.title")}>
        <dl className="flex flex-col">
          <SummaryRow label={t("side.summary.status")} value={process.status} />
          <SummaryRow label={t("side.summary.owner")} value={process.owner} />
          <SummaryRow label={t("side.summary.phase")} value={process.stage} />
        </dl>
        <div className="mt-3">
          <p className="eyebrow mb-1.5">{t("side.summary.readiness")}</p>
          <Meter
            value={process.readiness}
            tone={
              process.readiness >= 70
                ? "ok"
                : process.readiness >= 40
                  ? "warning"
                  : "danger"
            }
          />
        </div>
      </SidePanel>

      <SidePanel title={t("side.quality.title")}>
        <EmptyState variant="inline" title={t("side.quality.unavailable")} />
      </SidePanel>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/60 py-2 text-xs last:border-b-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="m-0 text-right font-medium text-foreground">{value}</dd>
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
      <h3 className="eyebrow mb-2">{title}</h3>
      {children}
    </section>
  );
}
