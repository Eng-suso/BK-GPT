import React from "react";
import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { MessagesSquare, Upload } from "lucide-react";

import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";
// Note: bpmn-js-properties-panel bundles its styles internally; no separate CSS import needed.

import type { StatusTone } from "@/components/status";
import { Button } from "@/ui/button";
import { useBpmnCanvas } from "./bpmn/useBpmnCanvas";
import { BpmnCanvasToolbar } from "./components/BpmnCanvasToolbar";
import { BpmnNodeInspector } from "./components/BpmnNodeInspector";
import { BpmnVersionHistory } from "./components/BpmnVersionHistory";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/ui/dialog";

type ProcessBpmnCanvasProps = {
  bpmnModelId: string;
  processName: string;
  propertiesPanelRef: RefObject<HTMLDivElement | null>;
  onCurrentXmlChange?: (xml: string) => void;
  /** Sends the consultant to the discussion, where the model is reconstructed. */
  onOpenDiscussion?: () => void;
  /** Canvas-chat rail toggle (owned by ProcessWorkspace). */
  isCanvasChatOpen?: boolean;
  onToggleCanvasChat?: () => void;
  /** BPMN properties dock toggle (owned by the route, URL `?panel=properties`). */
  isPropertiesOpen?: boolean;
  onTogglePropertiesPanel?: () => void;
};

/**
 * Thin shell around the BPMN canvas: `useBpmnCanvas` owns the bpmn-js lifecycle,
 * persistence and version history; this component wires that state to the
 * toolbar, canvas host, node inspector and history panel.
 */
export const ProcessBpmnCanvas: React.FC<ProcessBpmnCanvasProps> = ({
  bpmnModelId,
  processName,
  propertiesPanelRef,
  onCurrentXmlChange,
  onOpenDiscussion,
  isCanvasChatOpen,
  onToggleCanvasChat,
  isPropertiesOpen,
  onTogglePropertiesPanel,
}) => {
  const { t } = useTranslation("process");
  const menuButtonRef = React.useRef<HTMLButtonElement>(null);
  const {
    containerRef,
    fileInputRef,
    isReady,
    isEmptyModel,
    status,
    error,
    isSaving,
    hasUnsavedChanges,
    versions,
    restoringVersionId,
    isHistoryOpen,
    setIsHistoryOpen,
    selectedElement,
    clearSelection,
    updateSelectedNodeName,
    updateSelectedNodeDoc,
    save,
    restoreVersion,
    exportXml,
    importFile,
    zoomIn,
    zoomOut,
    zoomFit,
  } = useBpmnCanvas({
    bpmnModelId,
    processName,
    propertiesPanelRef,
    onCurrentXmlChange,
  });

  const isError = status.toLowerCase().startsWith("errore");
  const saveTone: StatusTone = isError
    ? "danger"
    : hasUnsavedChanges
      ? "warning"
      : "ok";
  // Keep it to one short chip so the toolbar stays on a single row; the full
  // error text still renders in the canvas error banner.
  const saveLabel = isError
    ? status
    : hasUnsavedChanges
      ? "Non salvato"
      : "Salvato";

  return (
    <section className="process-bpmn-shell" aria-label="Canvas BPMN">
      <BpmnCanvasToolbar
        saveTone={saveTone}
        saveLabel={saveLabel}
        isReady={isReady}
        isSaving={isSaving}
        hasUnsavedChanges={hasUnsavedChanges}
        isHistoryOpen={isHistoryOpen}
        versionCount={versions.length}
        fileInputRef={fileInputRef}
        menuButtonRef={menuButtonRef}
        canvasChat={{ isOpen: isCanvasChatOpen, onToggle: onToggleCanvasChat }}
        properties={{
          isOpen: isPropertiesOpen,
          onToggle: onTogglePropertiesPanel,
        }}
        onSave={save}
        onZoomIn={zoomIn}
        onZoomOut={zoomOut}
        onZoomFit={zoomFit}
        onImportClick={() => fileInputRef.current?.click()}
        onImportFile={importFile}
        onExport={exportXml}
        onToggleHistory={() => setIsHistoryOpen((prev) => !prev)}
      />

      <div className="process-bpmn-body">
        <div className="process-bpmn-canvas" ref={containerRef}>
          {selectedElement && !isPropertiesOpen && (
            <BpmnNodeInspector
              element={selectedElement}
              onNameChange={updateSelectedNodeName}
              onDocChange={updateSelectedNodeDoc}
              onClose={clearSelection}
            />
          )}
          {/* Un processo appena creato non ha un modello: prima il canvas
              apriva su un diagramma finto che nessuno aveva descritto. Qui la
              tela resta vuota e dice da dove si parte — la palette bpmn-js
              rimane raggiungibile a sinistra. */}
          {isReady && isEmptyModel && !error && (
            <div className="process-bpmn-blank">
              <h3 className="text-sm font-semibold text-foreground">
                {t("canvas.blank.title")}
              </h3>
              <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                {t("canvas.blank.description")}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {onOpenDiscussion && (
                  <Button size="sm" onClick={onOpenDiscussion}>
                    <MessagesSquare aria-hidden className="size-4" />
                    {t("canvas.blank.openDiscussion")}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload aria-hidden className="size-4" />
                  {t("canvas.blank.import")}
                </Button>
              </div>
            </div>
          )}
        </div>

      </div>
      <Dialog open={isHistoryOpen} onOpenChange={setIsHistoryOpen}>
        <DialogContent onCloseAutoFocus={(event) => { event.preventDefault(); menuButtonRef.current?.focus(); }} className="flex max-h-[85dvh] flex-col overflow-hidden border-border sm:max-w-xl">
          <DialogTitle>Cronologia versioni</DialogTitle>
          <DialogDescription>Consulta le modifiche e ripristina una versione del processo.</DialogDescription>
          <BpmnVersionHistory
            versions={versions}
            restoringVersionId={restoringVersionId}
            isReady={isReady}
            hasUnsavedChanges={hasUnsavedChanges}
            onRestore={restoreVersion}
          />
        </DialogContent>
      </Dialog>
      {error && <p className="process-bpmn-error">{error}</p>}
    </section>
  );
};
