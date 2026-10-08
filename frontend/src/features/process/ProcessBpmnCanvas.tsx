import React from "react";
import { createPortal } from "react-dom";
import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { MessagesSquare, Upload, Maximize2, Plus, Minus } from "lucide-react";

import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";
import "@bpmn-io/properties-panel/dist/assets/properties-panel.css";

import type { StatusTone } from "@/components/status";
import { Button } from "@/ui/button";
import { useElementWidth } from "@/lib/useElementWidth";
import { Surface } from "@/ui/surface";
import { WorkspaceDisclosure } from "@/components/layout/CanvasWorkspace";
import { BpmnCreationTools } from "./components/BpmnCreationTools";
import { BpmnElementNavigator } from "./components/BpmnElementNavigator";
import { useBpmnCanvas } from "./bpmn/useBpmnCanvas";
import { BpmnCanvasToolbar } from "./components/BpmnCanvasToolbar";
import { BpmnNodeInspector } from "./components/BpmnNodeInspector";
import { BpmnVersionHistory } from "./components/BpmnVersionHistory";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/ui/dialog";
import { useQueryClient } from "@tanstack/react-query";
import { onWorkspaceChanged } from "@/lib/workspaceEvents";
import { provenanceKeys, useProcessProvenanceQuery } from "./api";
import { EvidenceReviewPanel } from "./components/EvidenceReviewPanel";
import { BpmnCanvasIdentity } from "./components/BpmnCanvasIdentity";

type ProcessBpmnCanvasProps = {
  bpmnModelId: string;
  /** Il processo del disegno: serve al confronto con le fonti. */
  processId?: string;
  processName: string;
  propertiesPanelRef: RefObject<HTMLDivElement | null>;
  inspectorHost?: RefObject<HTMLDivElement | null>;
  onInspectorChange?: (inspector: { title: string; closeLabel: string; close: () => void } | null) => void;
  onCurrentXmlChange?: (xml: string) => void;
  onBaseVersionChange?: (versionId: number | null) => void;
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
  processId,
  processName,
  propertiesPanelRef,
  inspectorHost,
  onInspectorChange,
  onCurrentXmlChange,
  onBaseVersionChange,
  onOpenDiscussion,
  isCanvasChatOpen,
  onToggleCanvasChat,
  isPropertiesOpen,
  onTogglePropertiesPanel,
}) => {
  const { t } = useTranslation("process");
  const { ref: shellRef, width: shellWidth } = useElementWidth<HTMLElement>();
  const elementsButtonRef = React.useRef<HTMLButtonElement>(null);
  const [elementsOpen, setElementsOpen] = React.useState(false);
  const [coloursEnabled, setColoursEnabled] = React.useState(true);
  const restoreElementsFocus = React.useRef(false);
  React.useLayoutEffect(() => {
    if (!elementsOpen && restoreElementsFocus.current) {
      restoreElementsFocus.current = false;
      elementsButtonRef.current?.focus({ preventScroll: true });
    }
  }, [elementsOpen]);
  const closeElements = () => { restoreElementsFocus.current = true; setElementsOpen(false); };
  const menuButtonRef = React.useRef<HTMLButtonElement>(null);
  const [isEvidenceOpen, setIsEvidenceOpen] = React.useState(false);
  // Un pannello aperto su un processo non resta aperto sul successivo: le
  // evidenze sono di quel disegno.
  const [evidenceIdentity, setEvidenceIdentity] = React.useState(`${processId}:${bpmnModelId}`);
  if (evidenceIdentity !== `${processId}:${bpmnModelId}`) {
    setEvidenceIdentity(`${processId}:${bpmnModelId}`);
    setIsEvidenceOpen(false);
  }
  const queryClient = useQueryClient();
  const provenanceQuery = useProcessProvenanceQuery(processId ?? "", {
    enabled: Boolean(processId),
  });

  // Il disegno cambia anche da fuori - la chat genera una bozza, un'altra
  // scheda salva - e il confronto con le fonti cambia con lui.
  React.useEffect(() => {
    if (!processId) return;
    return onWorkspaceChanged((detail) => {
      if (detail.bpmnModelId && detail.bpmnModelId !== bpmnModelId) return;
      void queryClient.invalidateQueries({ queryKey: provenanceKeys.process(processId) });
    });
  }, [bpmnModelId, processId, queryClient]);
  const {
    elements,
    creationTools,
    activateTool,
    selectElement,
    retryLoad,
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
    hasConflict,
    reloadLatest,
    restoreVersion,
    exportXml,
    importFile,
    zoomIn,
    zoomOut,
    zoomFit,
    zoomReadable,
    focusSourceRef,
  } = useBpmnCanvas({
    bpmnModelId,
    processName,
    propertiesPanelRef,
    onCurrentXmlChange,
    onBaseVersionChange,
  });

  const inspectorTitle = isEvidenceOpen ? t("canvas.evidence.title") : selectedElement ? t("canvas.inspectorLabel") : null;
  React.useLayoutEffect(() => {
    onInspectorChange?.(!isPropertiesOpen && inspectorTitle ? { title: inspectorTitle, closeLabel: isEvidenceOpen ? t("canvas.evidence.close") : t("canvas.inspectorClose"), close: () => { setIsEvidenceOpen(false); clearSelection(); } } : null);
  }, [onInspectorChange, isPropertiesOpen, inspectorTitle, isEvidenceOpen, clearSelection, t]);
  React.useEffect(() => () => onInspectorChange?.(null), [onInspectorChange]);
  const inspectorContent = !isPropertiesOpen && (processId && isEvidenceOpen ? (
    <EvidenceReviewPanel embedded={Boolean(inspectorHost)} processId={processId} bpmnModelId={bpmnModelId} hasUnsavedChanges={hasUnsavedChanges} onLocate={focusSourceRef} onClose={() => setIsEvidenceOpen(false)} />
  ) : selectedElement ? (
    <BpmnNodeInspector embedded={Boolean(inspectorHost)} element={selectedElement} onNameChange={updateSelectedNodeName} onDocChange={updateSelectedNodeDoc} onClose={clearSelection} />
  ) : null);

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
      ? t("canvas.unsaved")
      : t("canvas.saved");

  return (
    <section ref={shellRef} className={`process-bpmn-shell ${coloursEnabled ? "process-bpmn--colours" : ""}`} aria-label="Canvas BPMN" onKeyDown={(event) => { if (event.key === "Escape" && elementsOpen) { event.preventDefault(); closeElements(); } }}>
      <BpmnCanvasToolbar
        elements={{ isOpen: elementsOpen, onToggle: () => { setIsEvidenceOpen(false); setElementsOpen((prev) => !prev); } }}
        elementsButtonRef={elementsButtonRef}
        elementCount={elements.length}
        coloursEnabled={coloursEnabled}
        onToggleColours={() => setColoursEnabled((value) => !value)}
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
        evidence={
          processId
            ? {
                isOpen: isEvidenceOpen,
                onToggle: () => { setElementsOpen(false); if (isPropertiesOpen) onTogglePropertiesPanel?.(); setIsEvidenceOpen((prev) => !prev); },
                awaitingCount: provenanceQuery.data?.awaitingConfirmation ?? 0,
              }
            : undefined
        }
        onSave={save}
        onZoomIn={zoomIn}
        onZoomOut={zoomOut}
        onZoomFit={zoomFit}
        onZoomReadable={zoomReadable}
        onImportClick={() => fileInputRef.current?.click()}
        onImportFile={importFile}
        onExport={exportXml}
        onToggleHistory={() => setIsHistoryOpen((prev) => !prev)}
      />

      <div className={`process-bpmn-body ${elementsOpen ? "process-bpmn-body--elements" : ""}`}>
        {elementsOpen && <BpmnElementNavigator elements={elements} selectedId={selectedElement?.id} isReady={isReady} onClose={closeElements} onSelect={(id) => { if (selectElement(id) && shellWidth < 820) closeElements(); }} />}
        <div className="process-bpmn-stage">
        <BpmnCreationTools tools={creationTools} isReady={isReady} onActivate={activateTool} />
        <div className={`process-bpmn-canvas ${coloursEnabled ? "delir-canvas--colours" : ""}`} ref={containerRef}>
          <BpmnCanvasIdentity />
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
        <Surface variant="floating" className="process-canvas-navigation" role="group" aria-label={t("canvas.zoomGroup")}>
          {coloursEnabled && <WorkspaceDisclosure label={t("canvas.colours")} contentClassName="process-canvas-legend-popover"><div className="process-bpmn-legend">{(["task", "automation", "gateway", "start", "end"] as const).map((kind) => <span key={kind}><i aria-hidden className={`process-element-swatch--${kind}`} />{t(`canvas.legend.${kind}`)}</span>)}</div></WorkspaceDisclosure>}
          <Button variant="ghost" size="sm" onClick={zoomReadable} title={t("canvas.readableTitle")}>{t("canvas.readable")}</Button>
          <Button variant="ghost" size="sm" onClick={zoomFit} title={t("canvas.fitTitle")}><Maximize2 aria-hidden />{t("canvas.fit")}</Button>
          <Button variant="ghost" size="icon-sm" onClick={zoomOut} aria-label={t("canvas.zoomOut")}><Minus aria-hidden /></Button>
          <Button variant="ghost" size="icon-sm" onClick={zoomIn} aria-label={t("canvas.zoomIn")}><Plus aria-hidden /></Button>
        </Surface>
        </div>
        {inspectorContent && (inspectorHost?.current ? createPortal(inspectorContent, inspectorHost.current) : inspectorContent)}
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
      {error && <Surface variant="floating" className="process-bpmn-load-error" role="alert"><p>{error}</p>{!isReady && <Button size="sm" variant="outline" onClick={retryLoad}>{t("canvas.retryLoad")}</Button>}{hasConflict && <Button size="sm" variant="outline" onClick={reloadLatest}>{t("canvas.conflict.reloadLatest")}</Button>}</Surface>}
    </section>
  );
};
