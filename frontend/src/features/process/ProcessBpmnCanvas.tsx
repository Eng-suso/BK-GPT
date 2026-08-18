import React, { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import Modeler from "bpmn-js/lib/Modeler";
import TokenSimulationModule from "bpmn-js-token-simulation";
import { BpmnPropertiesPanelModule, BpmnPropertiesProviderModule } from "bpmn-js-properties-panel";
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";
// Note: bpmn-js-properties-panel bundles its styles internally; no separate CSS import needed.
import "bpmn-js-token-simulation/assets/css/bpmn-js-token-simulation.css";
import { API_BASE } from "../../lib/api";
import { onWorkspaceChanged } from "../../lib/workspaceEvents";
import { buildInitialProcessDiagram } from "./initialProcessDiagram";

type BpmnModeler = {
  importXML: (xml: string) => Promise<unknown>;
  saveXML: (options?: { format?: boolean }) => Promise<{ xml?: string }>;
  destroy: () => void;
  get: (name: string) => unknown;
};

type BpmnConnection = {
  id: string;
  businessObject?: {
    $type?: string;
  };
  source?: unknown;
  target?: unknown;
  waypoints?: unknown[];
};

type BpmnCanvasService = {
  zoom: (scale?: number | "fit-viewport", center?: unknown) => number;
  resized?: () => void;
  viewbox?: (box?: BpmnCanvasViewbox) => BpmnCanvasViewbox & {
    outer?: { width: number; height: number };
  };
};

type BpmnEventBus = {
  on: (events: string | string[], callback: (event?: any) => void) => void;
};

type BpmnElementRegistry = {
  filter: (predicate: (element: BpmnConnection) => boolean) => BpmnConnection[];
  getAll?: () => BpmnDiagramElement[];
};

type BpmnModeling = {
  layoutConnection: (connection: BpmnConnection) => void;
};

type ProcessBpmnCanvasProps = {
  bpmnModelId: string;
  processName: string;
  propertiesPanelRef: RefObject<HTMLDivElement | null>;
  onCurrentXmlChange?: (xml: string) => void;
};

type BpmnModelResponse = {
  id: string;
  process_id: string;
  name: string;
  xml: string | null;
};

type BpmnVersionResponse = {
  id: number;
  bpmn_model_id: string;
  process_id: string;
  change_summary: string;
  source: string;
  created_at: string;
};

type RestoreBpmnVersionResponse = {
  bpmn_model: BpmnModelResponse;
  restored_from: BpmnVersionResponse;
  created_version: BpmnVersionResponse;
};

type BpmnCanvasViewbox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type BpmnDiagramElement = {
  id?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  waypoints?: Array<{ x: number; y: number }>;
};

function canvas(modeler: BpmnModeler) {
  return modeler.get("canvas") as BpmnCanvasService;
}

function fitCanvas(modeler: BpmnModeler) {
  const canvasService = canvas(modeler);
  canvasService.resized?.();

  const elements = (modeler.get("elementRegistry") as BpmnElementRegistry).getAll?.() ?? [];
  const bounds = getDiagramBounds(elements);
  const outer = canvasService.viewbox?.().outer;

  if (!bounds || !outer?.width || !outer.height || !canvasService.viewbox) {
    canvasService.zoom("fit-viewport");
    return;
  }

  const padded = withViewportPadding(bounds, outer.width / outer.height);
  const scale = outer.width / padded.width;
  const minReadableScale = 0.55;

  if (scale < minReadableScale) {
    canvasService.viewbox({
      x: bounds.x - 140,
      y: bounds.y - 140,
      width: outer.width / minReadableScale,
      height: outer.height / minReadableScale,
    });
    return;
  }

  canvasService.viewbox(padded);
}

function isConnection(element: BpmnConnection) {
  return Boolean(
    element.id &&
      element.source &&
      element.target &&
      Array.isArray(element.waypoints)
  );
}

function isDockableSequenceConnection(element: BpmnConnection) {
  return isConnection(element) && element.businessObject?.$type === "bpmn:SequenceFlow";
}

function getDiagramBounds(elements: BpmnDiagramElement[]) {
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const element of elements) {
    if (element.id === "__implicitroot") continue;

    if (
      typeof element.x === "number" &&
      typeof element.y === "number" &&
      typeof element.width === "number" &&
      typeof element.height === "number"
    ) {
      minX = Math.min(minX, element.x);
      minY = Math.min(minY, element.y);
      maxX = Math.max(maxX, element.x + element.width);
      maxY = Math.max(maxY, element.y + element.height);
    }

    for (const point of element.waypoints ?? []) {
      minX = Math.min(minX, point.x);
      minY = Math.min(minY, point.y);
      maxX = Math.max(maxX, point.x);
      maxY = Math.max(maxY, point.y);
    }
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY)) return null;

  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
  };
}

function withViewportPadding(bounds: BpmnCanvasViewbox, viewportRatio: number) {
  const paddingX = 140;
  const paddingY = 120;
  let x = bounds.x - paddingX;
  let y = bounds.y - paddingY;
  let width = bounds.width + paddingX * 2;
  let height = Math.max(bounds.height + paddingY * 2, 420);
  const boundsRatio = width / height;

  if (boundsRatio > viewportRatio) {
    const centeredHeight = width / viewportRatio;
    y -= (centeredHeight - height) / 2;
    height = centeredHeight;
  } else {
    const centeredWidth = height * viewportRatio;
    x -= (centeredWidth - width) / 2;
    width = centeredWidth;
  }

  return { x, y, width, height };
}

function keepSequenceConnectionsDocked(modeler: BpmnModeler) {
  const eventBus = modeler.get("eventBus") as BpmnEventBus;
  const elementRegistry = modeler.get("elementRegistry") as BpmnElementRegistry;
  const modeling = modeler.get("modeling") as BpmnModeling;
  let scheduled = false;

  function scheduleRelayout() {
    if (scheduled) return;

    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      for (const connection of elementRegistry.filter(isDockableSequenceConnection)) {
        try {
          modeling.layoutConnection(connection);
        } catch {
          // Ignore transient invalid connections while the user edits the diagram.
        }
      }
    });
  }

  eventBus.on(
    [
      "commandStack.shape.move.postExecuted",
      "commandStack.elements.move.postExecuted",
      "commandStack.shape.resize.postExecuted",
    ],
    scheduleRelayout,
  );
}

function downloadBpmn(xml: string, processName: string) {
  const fileName = `${processName || "processo"}.bpmn`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  const url = URL.createObjectURL(new Blob([xml], { type: "application/xml" }));
  const link = document.createElement("a");

  link.href = url;
  link.download = `${fileName || "processo"}.bpmn`;
  link.click();
  URL.revokeObjectURL(url);
}

function assertBpmnXml(file: File, xml: string) {
  const fileName = file.name.toLowerCase();

  if (fileName.endsWith(".bpm") || !xml.trimStart().startsWith("<")) {
    throw new Error("Importa un file BPMN 2.0 XML valido, non un file .bpm proprietario.");
  }
}

export const ProcessBpmnCanvas: React.FC<ProcessBpmnCanvasProps> = ({
  bpmnModelId,
  processName,
  propertiesPanelRef,
  onCurrentXmlChange,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const modelerRef = useRef<BpmnModeler | null>(null);
  const hasUnsavedChangesRef = useRef(false);
  const isImportingRef = useRef(false);
  const isSavingRef = useRef(false);
  const draftSaveTimerRef = useRef<number | null>(null);
  const changeCheckTimerRef = useRef<number | null>(null);
  const lastSavedXmlRef = useRef<string | null>(null);
  const [status, setStatus] = useState("Caricamento canvas...");
  const [error, setError] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [restoringVersionId, setRestoringVersionId] = useState<number | null>(null);
  const [versions, setVersions] = useState<BpmnVersionResponse[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [selectedElement, setSelectedElement] = useState<{
    id: string;
    type: string;
    name: string;
    documentation: string;
  } | null>(null);
  const onCurrentXmlChangeRef = useRef(onCurrentXmlChange);

  useEffect(() => {
    onCurrentXmlChangeRef.current = onCurrentXmlChange;
  }, [onCurrentXmlChange]);

  function markUnsaved(value: boolean) {
    hasUnsavedChangesRef.current = value;
    setHasUnsavedChanges(value);
  }

  function clearDraftTimer() {
    if (draftSaveTimerRef.current) {
      window.clearTimeout(draftSaveTimerRef.current);
      draftSaveTimerRef.current = null;
    }
  }

  function clearChangeCheckTimer() {
    if (changeCheckTimerRef.current) {
      window.clearTimeout(changeCheckTimerRef.current);
      changeCheckTimerRef.current = null;
    }
  }

  const scheduleLocalDraftSave = useCallback(() => {
    clearDraftTimer();
    draftSaveTimerRef.current = window.setTimeout(async () => {
      if (!modelerRef.current || !hasUnsavedChangesRef.current) return;

      try {
        const { xml } = await modelerRef.current.saveXML({ format: true });
        if (xml) {
          writeLocalBpmnDraft(bpmnModelId, xml);
          onCurrentXmlChangeRef.current?.(xml);
        }
      } catch {
        // Local draft persistence is best effort; explicit save still uses the backend.
      }
    }, 350);
  }, [bpmnModelId]);

  const scheduleUnsavedCheck = useCallback(() => {
    clearChangeCheckTimer();
    changeCheckTimerRef.current = window.setTimeout(async () => {
      if (!modelerRef.current || isImportingRef.current || isSavingRef.current) return;

      try {
        const { xml } = await modelerRef.current.saveXML({ format: true });
        if (xml) onCurrentXmlChangeRef.current?.(xml);
        if (xml && lastSavedXmlRef.current === xml) {
          markUnsaved(false);
          setStatus("Salvato");
          return;
        }
      } catch {
        // If comparison fails, keep the conservative unsaved state.
      }

      markUnsaved(true);
      setStatus("Modifiche non salvate");
      scheduleLocalDraftSave();
    }, 120);
  }, [scheduleLocalDraftSave]);

  function scheduleCanvasFit() {
    window.requestAnimationFrame(() => {
      if (document.hidden || !modelerRef.current) return;

      fitCanvas(modelerRef.current);
      window.setTimeout(() => {
        if (modelerRef.current) fitCanvas(modelerRef.current);
      }, 120);
    });
  }

  const loadVersions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/workspace/bpmn-models/${bpmnModelId}/versions`, {
        cache: "no-store",
      });

      if (!res.ok) return;

      setVersions((await res.json()) as BpmnVersionResponse[]);
    } catch {
      // Version history is useful but not required for canvas editing.
    }
  }, [bpmnModelId]);

  useEffect(() => {
    if (!containerRef.current) return;

    let isMounted = true;
    async function mountCanvas() {
      try {
        if (!isMounted || !containerRef.current) return;

        const modeler = new Modeler({
          container: containerRef.current,
          propertiesPanel: propertiesPanelRef.current
            ? { parent: propertiesPanelRef.current }
            : undefined,
          additionalModules: [
            TokenSimulationModule,
            BpmnPropertiesPanelModule,
            BpmnPropertiesProviderModule,
          ],
        }) as BpmnModeler;

        modelerRef.current = modeler;
        keepSequenceConnectionsDocked(modeler);

        const localDraft = readLocalBpmnDraft(bpmnModelId);
        const xml = localDraft ?? await loadInitialXml(bpmnModelId, processName);
        lastSavedXmlRef.current = localDraft ? null : xml;
        isImportingRef.current = true;
        await modeler.importXML(xml);
        onCurrentXmlChangeRef.current?.(xml);
        isImportingRef.current = false;

        const eventBus = modeler.get("eventBus") as BpmnEventBus;
        eventBus.on("commandStack.changed", () => {
          if (!isImportingRef.current && !isSavingRef.current) {
            scheduleUnsavedCheck();
          }
        });

        type BpmnElementSelection = {
          id: string;
          type: string;
          businessObject?: {
            name?: string;
            documentation?: Array<{ text?: string }>;
          };
        };

        eventBus.on("selection.changed", (e: { newSelection?: BpmnElementSelection[] }) => {
          const selected = e.newSelection?.[0];
          if (!selected || selected.id === "__implicitroot") {
            setSelectedElement(null);
            return;
          }

          const bo = selected.businessObject;
          const docs = bo?.documentation?.[0]?.text || "";

          setSelectedElement({
            id: selected.id,
            type: (selected.type || "Elemento").replace(/^bpmn:/, ""),
            name: bo?.name || "",
            documentation: docs,
          });
        });

        scheduleCanvasFit();

        if (isMounted) {
          setIsReady(true);
          markUnsaved(Boolean(localDraft));
          setStatus(localDraft ? "Bozza locale non salvata" : "Bozza BPMN salvata");
          setError(null);
        }
        void loadVersions();
      } catch (err) {
        isImportingRef.current = false;
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Canvas BPMN non disponibile");
          setStatus("Errore canvas");
        }
      }
    }

    void mountCanvas();

    return () => {
      isMounted = false;
      clearChangeCheckTimer();
      modelerRef.current?.destroy();
      modelerRef.current = null;
      setIsReady(false);
    };
  }, [bpmnModelId, processName, propertiesPanelRef, loadVersions, scheduleUnsavedCheck]);

  useEffect(() => {
    if (!containerRef.current) return;

    const resizeObserver = new ResizeObserver(() => {
      scheduleCanvasFit();
    });
    resizeObserver.observe(containerRef.current);

    return () => resizeObserver.disconnect();
  }, []);

  useEffect(() => {
    return onWorkspaceChanged(async () => {
      if (!modelerRef.current || hasUnsavedChangesRef.current) return;

      try {
        const xml = await loadInitialXml(bpmnModelId, processName);
        isImportingRef.current = true;
        await modelerRef.current.importXML(xml);
        onCurrentXmlChangeRef.current?.(xml);
        isImportingRef.current = false;
        scheduleCanvasFit();
        lastSavedXmlRef.current = xml;
        markUnsaved(false);
        setStatus("Aggiornato dal backend");
        setError(null);
        void loadVersions();
      } catch (err) {
        isImportingRef.current = false;
        setError(err instanceof Error ? err.message : "Aggiornamento canvas non riuscito");
      }
    });
  }, [bpmnModelId, processName, loadVersions]);

  async function saveCurrentXml() {
    if (!modelerRef.current) return;

    isSavingRef.current = true;
    clearDraftTimer();
    clearChangeCheckTimer();
    setIsSaving(true);
    setError(null);

    try {
      const { xml } = await modelerRef.current.saveXML({ format: true });
      if (!xml) throw new Error("Il canvas non ha restituito XML BPMN.");
      onCurrentXmlChange?.(xml);

      const res = await fetch(`${API_BASE}/v1/workspace/bpmn-models/${bpmnModelId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ xml }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Salvataggio BPMN non riuscito.");
      }

      clearDraftTimer();
      clearLocalBpmnDraft(bpmnModelId);
      lastSavedXmlRef.current = xml;
      markUnsaved(false);
      setStatus("Salvato");
      void loadVersions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Salvataggio BPMN non riuscito");
      setStatus("Errore salvataggio");
    } finally {
      setIsSaving(false);
      window.setTimeout(() => {
        isSavingRef.current = false;
      }, 250);
    }
  }

  async function restoreVersion(versionId: number) {
    if (!modelerRef.current) return;

    if (hasUnsavedChangesRef.current) {
      setError("Salva o scarta la bozza locale prima di ripristinare una versione.");
      return;
    }

    setRestoringVersionId(versionId);
    setError(null);

    try {
      const res = await fetch(
        `${API_BASE}/v1/workspace/bpmn-models/${bpmnModelId}/versions/${versionId}/restore`,
        { method: "POST" },
      );

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Ripristino versione non riuscito.");
      }

      const result = (await res.json()) as RestoreBpmnVersionResponse;
      const xml = result.bpmn_model.xml;
      if (!xml) throw new Error("La versione ripristinata non contiene XML BPMN.");

      isImportingRef.current = true;
      await modelerRef.current.importXML(xml);
      onCurrentXmlChange?.(xml);
      isImportingRef.current = false;
      clearLocalBpmnDraft(bpmnModelId);
      lastSavedXmlRef.current = xml;
      markUnsaved(false);
      scheduleCanvasFit();
      setStatus(`Ripristinata versione ${versionId}`);
      await loadVersions();
    } catch (err) {
      isImportingRef.current = false;
      setError(err instanceof Error ? err.message : "Ripristino versione non riuscito");
    } finally {
      setRestoringVersionId(null);
    }
  }

  async function exportCurrentXml() {
    if (!modelerRef.current) return;

    try {
      const { xml } = await modelerRef.current.saveXML({ format: true });
      if (!xml) throw new Error("Il canvas non ha restituito XML BPMN.");
      onCurrentXmlChange?.(xml);
      downloadBpmn(xml, processName);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export BPMN non riuscito");
    }
  }

  async function importFile(file: File | undefined) {
    if (!file || !modelerRef.current) return;

    try {
      const xml = await file.text();
      assertBpmnXml(file, xml);
      isImportingRef.current = true;
      await modelerRef.current.importXML(xml);
      onCurrentXmlChange?.(xml);
      isImportingRef.current = false;
      scheduleCanvasFit();
      markUnsaved(true);
      writeLocalBpmnDraft(bpmnModelId, xml);
      setStatus("Importato, non salvato");
      setError(null);
    } catch (err) {
      isImportingRef.current = false;
      setError(err instanceof Error ? err.message : "Import BPMN non riuscito");
      setStatus("Errore import");
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void saveCurrentXml();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [saveCurrentXml]);

  function updateSelectedNodeName(newName: string) {
    if (!modelerRef.current || !selectedElement) return;
    setSelectedElement((prev) => (prev ? { ...prev, name: newName } : null));

    try {
      const elementRegistry = modelerRef.current.get("elementRegistry") as { get: (id: string) => unknown };
      const modeling = modelerRef.current.get("modeling") as { updateProperties: (element: unknown, properties: Record<string, unknown>) => void };
      const elem = elementRegistry.get(selectedElement.id);
      if (elem) {
        modeling.updateProperties(elem, { name: newName });
        scheduleUnsavedCheck();
      }
    } catch {
      // transient edit while modeler updates
    }
  }

  function updateSelectedNodeDoc(newDoc: string) {
    if (!modelerRef.current || !selectedElement) return;
    setSelectedElement((prev) => (prev ? { ...prev, documentation: newDoc } : null));

    try {
      const elementRegistry = modelerRef.current.get("elementRegistry") as { get: (id: string) => unknown };
      const bpmnFactory = modelerRef.current.get("bpmnFactory") as { create: (type: string, props: Record<string, unknown>) => unknown };
      const modeling = modelerRef.current.get("modeling") as { updateProperties: (element: unknown, properties: Record<string, unknown>) => void };
      const elem = elementRegistry.get(selectedElement.id);
      if (elem) {
        const docObj = bpmnFactory.create("bpmn:Documentation", { text: newDoc });
        modeling.updateProperties(elem, { documentation: [docObj] });
        scheduleUnsavedCheck();
      }
    } catch {
      // transient edit
    }
  }

  function handleZoomIn() {
    if (!modelerRef.current) return;
    const canvasService = canvas(modelerRef.current);
    const currentZoom = (canvasService.zoom() as number) || 1;
    canvasService.zoom(Math.min(currentZoom + 0.2, 3));
  }

  function handleZoomOut() {
    if (!modelerRef.current) return;
    const canvasService = canvas(modelerRef.current);
    const currentZoom = (canvasService.zoom() as number) || 1;
    canvasService.zoom(Math.max(currentZoom - 0.2, 0.2));
  }

  function handleZoomFit() {
    if (!modelerRef.current) return;
    fitCanvas(modelerRef.current);
  }

  return (
    <section className="process-bpmn-shell" aria-label="Canvas BPMN">
      <header className="process-bpmn-toolbar">
        <div>
          <p className="product-eyebrow">BPMN 2.0</p>
          <h3>Canvas processo</h3>
        </div>
        <div className="process-bpmn-toolbar-actions">
          <div className="bpmn-zoom-group" aria-label="Controlli Zoom">
            <button type="button" onClick={handleZoomFit} title="Centra e adatta diagramma">
              🔍 Centra
            </button>
            <button type="button" onClick={handleZoomIn} title="Ingrandisci">
              +
            </button>
            <button type="button" onClick={handleZoomOut} title="Riduci">
              -
            </button>
          </div>

          <span className={`status-pill ${hasUnsavedChanges ? "unsaved" : "saved"}`}>
            {hasUnsavedChanges ? "Modifiche non salvate" : status}
          </span>
          <input
            ref={fileInputRef}
            className="process-bpmn-file-input"
            type="file"
            accept=".bpmn,.xml,.bpm"
            onChange={(event) => void importFile(event.target.files?.[0])}
          />
          <button
            type="button"
            className={isHistoryOpen ? "is-active" : ""}
            onClick={() => setIsHistoryOpen((prev) => !prev)}
            title={isHistoryOpen ? "Nascondi Cronologia" : "Mostra Cronologia Versioni"}
          >
            Cronologia {versions.length > 0 ? `(${versions.length})` : ""}
          </button>
          <button
            type="button"
            disabled={!isReady}
            onClick={() => fileInputRef.current?.click()}
          >
            Importa
          </button>
          <button type="button" disabled={!isReady} onClick={() => void exportCurrentXml()}>
            Esporta
          </button>
          <button
            type="button"
            className={hasUnsavedChanges ? "btn-save-unsaved" : ""}
            disabled={!isReady || isSaving || !hasUnsavedChanges}
            onClick={() => void saveCurrentXml()}
            title="Salva processo (Ctrl+S)"
          >
            {isSaving ? "Salvo..." : "Salva (Ctrl+S)"}
          </button>
        </div>
      </header>

      <div className={`process-bpmn-body ${isHistoryOpen ? "with-history" : ""}`}>
        <div className="process-bpmn-canvas" ref={containerRef}>
          {selectedElement && (
            <aside className="bpmn-node-inspector" aria-label="Ispettore nodo selezionato">
              <div className="bpmn-node-inspector-header">
                <div>
                  <span className="bpmn-node-badge">{selectedElement.type}</span>
                  <strong>{selectedElement.name || selectedElement.id}</strong>
                </div>
                <button
                  type="button"
                  className="bpmn-node-inspector-close"
                  onClick={() => setSelectedElement(null)}
                  title="Chiudi ispettore"
                >
                  ×
                </button>
              </div>
              <div className="bpmn-node-inspector-body">
                <label>
                  <span>Etichetta / Nome</span>
                  <input
                    type="text"
                    value={selectedElement.name}
                    onChange={(e) => updateSelectedNodeName(e.target.value)}
                    placeholder="es. Raccolta dati..."
                  />
                </label>
                <label>
                  <span>Note / Documentazione</span>
                  <textarea
                    rows={2}
                    value={selectedElement.documentation}
                    onChange={(e) => updateSelectedNodeDoc(e.target.value)}
                    placeholder="Aggiungi dettagli o regole per questo nodo..."
                  />
                </label>
              </div>
            </aside>
          )}
        </div>

        {isHistoryOpen && (
          <aside className="process-bpmn-history" aria-label="Cronologia BPMN">
            <div className="process-bpmn-history-header">
              <p className="product-eyebrow">Versioni</p>
              <strong>Cronologia</strong>
            </div>
            {versions.length === 0 ? (
              <p className="process-bpmn-history-empty">Nessuna versione salvata.</p>
            ) : (
              <ul>
                {versions.map((version) => (
                  <li key={version.id}>
                    <div>
                      <strong>v{version.id}</strong>
                      <span>{formatVersionDate(version.created_at)}</span>
                      <small>{version.change_summary}</small>
                    </div>
                    <button
                      type="button"
                      disabled={!isReady || restoringVersionId === version.id || hasUnsavedChanges}
                      onClick={() => void restoreVersion(version.id)}
                    >
                      {restoringVersionId === version.id ? "..." : "Ripristina"}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </aside>
        )}
      </div>
      {error && <p className="process-bpmn-error">{error}</p>}
    </section>
  );
};

function getLocalDraftKey(bpmnModelId: string) {
  return `workspace:bpmn-draft:${bpmnModelId}`;
}

function readLocalBpmnDraft(bpmnModelId: string) {
  return window.localStorage.getItem(getLocalDraftKey(bpmnModelId));
}

function writeLocalBpmnDraft(bpmnModelId: string, xml: string) {
  window.localStorage.setItem(getLocalDraftKey(bpmnModelId), xml);
}

function clearLocalBpmnDraft(bpmnModelId: string) {
  window.localStorage.removeItem(getLocalDraftKey(bpmnModelId));
}

function formatVersionDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function loadInitialXml(bpmnModelId: string, processName: string) {
  const fallbackXml = buildInitialProcessDiagram(processName);

  try {
    const res = await fetch(`${API_BASE}/v1/workspace/bpmn-models/${bpmnModelId}`, {
      cache: "no-store",
    });

    if (!res.ok) return fallbackXml;

    const model = (await res.json()) as BpmnModelResponse;
    return model.xml?.trim() || fallbackXml;
  } catch {
    return fallbackXml;
  }
}
