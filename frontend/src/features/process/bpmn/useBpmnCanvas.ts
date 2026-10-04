import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import Modeler from "bpmn-js/lib/Modeler";
import { translateBpmnLabel } from "./translate";
import {
  BpmnPropertiesPanelModule,
  BpmnPropertiesProviderModule,
} from "bpmn-js-properties-panel";

import { readCanvasElements, readCreationTools, type CanvasElement, type CreationTool, type PaletteService } from "./elements";
import { HttpError, httpErrorMessage } from "@/lib/http";
import { i18n } from "@/lib/i18n";
import type { BpmnVersion } from "@/contracts/workspace";
import { onWorkspaceChanged } from "@/lib/workspaceEvents";
import {
  fetchBpmnVersions,
  restoreBpmnVersion as restoreBpmnVersionRequest,
  saveBpmnModelXml,
} from "../api";
import {
  clearLocalBpmnDraft,
  draftBaseVersion,
  readLocalBpmnDraft,
  writeLocalBpmnDraft,
} from "./draft";
import {
  canvas,
  fitCanvas,
  frameCanvasForReading,
  hasDiagramContent,
  keepSequenceConnectionsDocked,
} from "./viewport";
import { applyProvenanceMarkers, splitTraceability, withTraceability } from "./provenance";
import { assertBpmnXml, downloadBpmn, loadInitialModel } from "./xml";
import type {
  BpmnCanvasService,
  BpmnElementRegistry,
  BpmnElementSelection,
  BpmnEventBus,
  BpmnFactory,
  BpmnModeler,
  BpmnModeling,
  SelectedBpmnElement,
} from "./types";

type UseBpmnCanvasArgs = {
  bpmnModelId: string;
  processName: string;
  propertiesPanelRef: RefObject<HTMLDivElement | null>;
  onCurrentXmlChange?: (xml: string) => void;
  /** The saved version the canvas XML comes from, for the canvas chat. */
  onBaseVersionChange?: (versionId: number | null) => void;
};

export type UseBpmnCanvas = {
  containerRef: RefObject<HTMLDivElement | null>;
  fileInputRef: RefObject<HTMLInputElement | null>;
  isReady: boolean;
  elements: CanvasElement[];
  creationTools: CreationTool[];
  activateTool: (id: string, action: "click" | "dragstart", event: Event) => void;
  selectElement: (id: string) => boolean;
  retryLoad: () => void;
  /** The model has no elements yet: a process recorded but not reconstructed. */
  isEmptyModel: boolean;
  status: string;
  error: string | null;
  isSaving: boolean;
  hasUnsavedChanges: boolean;
  versions: BpmnVersion[];
  restoringVersionId: number | null;
  isHistoryOpen: boolean;
  setIsHistoryOpen: (updater: boolean | ((prev: boolean) => boolean)) => void;
  selectedElement: SelectedBpmnElement | null;
  clearSelection: () => void;
  updateSelectedNodeName: (name: string) => void;
  updateSelectedNodeDoc: (doc: string) => void;
  save: () => void;
  /** The last save hit a newer version (409): `reloadLatest` loads it. */
  hasConflict: boolean;
  reloadLatest: () => void;
  restoreVersion: (versionId: number) => void;
  exportXml: () => void;
  importFile: (file: File | undefined) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  zoomFit: () => void;
  zoomReadable: () => void;
  /**
   * Seleziona e porta in vista il nodo che rappresenta un elemento del piano.
   * `false` quando il disegno non lo contiene: il pannello delle evidenze lo
   * dice invece di non fare niente.
   */
  focusSourceRef: (sourceRef: string) => boolean;
};

export function useBpmnCanvas({
  bpmnModelId,
  processName,
  propertiesPanelRef,
  onCurrentXmlChange,
  onBaseVersionChange,
}: UseBpmnCanvasArgs): UseBpmnCanvas {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const modelerRef = useRef<BpmnModeler | null>(null);
  const focusedElementIdRef = useRef<string | null>(null);
  const hasUnsavedChangesRef = useRef(false);
  const isImportingRef = useRef(false);
  const isSavingRef = useRef(false);
  const draftSaveTimerRef = useRef<number | null>(null);
  const changeCheckTimerRef = useRef<number | null>(null);
  const fitTimerRef = useRef<number | null>(null);
  const lastSavedXmlRef = useRef<string | null>(null);
  // The saved version the canvas started from: a save sends it back, and the
  // backend refuses (409) if someone saved a newer one in the meantime.
  const savedVersionIdRef = useRef<number | null>(null);
  const onCurrentXmlChangeRef = useRef(onCurrentXmlChange);
  const onBaseVersionChangeRef = useRef(onBaseVersionChange);
  // Riferimento di tracciabilita' -> nodi del disegno. Si ricostruisce a ogni
  // import: un disegno nuovo puo' rappresentare lo stesso passaggio altrove.
  const provenanceIndexRef = useRef<Map<string, string[]>>(new Map());

  const [creationTools, setCreationTools] = useState<CreationTool[]>([]);
  const [elements, setElements] = useState<CanvasElement[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState("Caricamento canvas...");
  const [error, setError] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [isEmptyModel, setIsEmptyModel] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [restoringVersionId, setRestoringVersionId] = useState<number | null>(
    null,
  );
  const [versions, setVersions] = useState<BpmnVersion[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [hasConflict, setHasConflict] = useState(false);
  const [selectedElement, setSelectedElement] =
    useState<SelectedBpmnElement | null>(null);

  useEffect(() => {
    onCurrentXmlChangeRef.current = onCurrentXmlChange;
  }, [onCurrentXmlChange]);

  useEffect(() => {
    onBaseVersionChangeRef.current = onBaseVersionChange;
  }, [onBaseVersionChange]);

  function setBaseVersion(versionId: number | null) {
    savedVersionIdRef.current = versionId;
    onBaseVersionChangeRef.current?.(versionId);
  }

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

  function clearFitTimer() {
    if (fitTimerRef.current) {
      window.clearTimeout(fitTimerRef.current);
      fitTimerRef.current = null;
    }
  }

  const scheduleLocalDraftSave = useCallback(() => {
    clearDraftTimer();
    draftSaveTimerRef.current = window.setTimeout(async () => {
      if (!modelerRef.current || !hasUnsavedChangesRef.current) return;

      try {
        const { xml } = await modelerRef.current.saveXML({ format: true });
        if (xml) {
          writeLocalBpmnDraft(bpmnModelId, xml, savedVersionIdRef.current);
          onCurrentXmlChangeRef.current?.(xml);
        }
      } catch (err) {
        console.warn("[bpmn] local draft save failed", err);
      }
    }, 350);
  }, [bpmnModelId]);

  const scheduleUnsavedCheck = useCallback(() => {
    clearChangeCheckTimer();
    changeCheckTimerRef.current = window.setTimeout(async () => {
      if (
        !modelerRef.current ||
        isImportingRef.current ||
        isSavingRef.current
      )
        return;

      try {
        const { xml } = await modelerRef.current.saveXML({ format: true });
        if (xml) onCurrentXmlChangeRef.current?.(xml);
        if (xml && lastSavedXmlRef.current === xml) {
          markUnsaved(false);
          setStatus("Salvato");
          return;
        }
      } catch (err) {
        console.warn("[bpmn] unsaved-state check failed", err);
      }

      markUnsaved(true);
      setStatus("Modifiche non salvate");
      scheduleLocalDraftSave();
    }, 120);
  }, [scheduleLocalDraftSave]);

  // Fit after importing a document. Resizing panes preserves the user camera.
  const scheduleCanvasFit = useCallback(() => {
    if (fitTimerRef.current) window.clearTimeout(fitTimerRef.current);
    fitTimerRef.current = window.setTimeout(() => {
      fitTimerRef.current = null;
      if (document.hidden || !modelerRef.current) return;
      fitCanvas(modelerRef.current);
      if (focusedElementIdRef.current) {
        const registry = modelerRef.current.get("elementRegistry") as BpmnElementRegistry;
        const element = registry.get?.(focusedElementIdRef.current);
        const service = modelerRef.current.get("canvas") as { scrollToElement?: (element: unknown, padding?: number) => void };
        if (element) service.scrollToElement?.(element, 40);
      }
    }, 100);
  }, []);

  const syncEmptiness = useCallback(() => {
    if (!modelerRef.current) return;
    setIsEmptyModel(!hasDiagramContent(modelerRef.current));
    setElements(readCanvasElements(modelerRef.current));
    setCreationTools(readCreationTools(modelerRef.current));
    const registry = modelerRef.current.get("elementRegistry") as BpmnElementRegistry;
    setSelectedElement((previous) => {
      if (!previous) return null;
      const current = registry.get?.(previous.id) as BpmnElementSelection | undefined;
      if (!current) return null;
      return { ...previous, name: current.businessObject?.name || "", documentation: splitTraceability(current.businessObject?.documentation?.[0]?.text).notes };
    });
    // Ogni punto che importa un XML passa di qui: e' il momento in cui i segni
    // di provenance vanno riletti dal disegno appena caricato.
    try {
      provenanceIndexRef.current = applyProvenanceMarkers(modelerRef.current);
    } catch (err) {
      console.warn("[bpmn] provenance markers failed", err);
      provenanceIndexRef.current = new Map();
    }
  }, []);

  const loadVersions = useCallback(async () => {
    try {
      const owner = modelerRef.current;
      const loaded = await fetchBpmnVersions(bpmnModelId);
      if (modelerRef.current === owner) setVersions(loaded);
    } catch (err) {
      console.warn("[bpmn] version history load failed", err);
    }
  }, [bpmnModelId]);

  useEffect(() => {
    if (!containerRef.current) return;

    let isMounted = true;
    let ownedModeler: BpmnModeler | null = null;
    setIsReady(false);
    focusedElementIdRef.current = null;
    setVersions([]);
    setSelectedElement(null);
    setElements([]);
    setCreationTools([]);
    setError(null);
    async function mountCanvas() {
      try {
        if (!isMounted || !containerRef.current) return;

        const modeler = new Modeler({
          container: containerRef.current,
          propertiesPanel: propertiesPanelRef.current
            ? { parent: propertiesPanelRef.current }
            : undefined,
          additionalModules: [
            BpmnPropertiesPanelModule,
            BpmnPropertiesProviderModule,
            { translate: ["value", translateBpmnLabel] },
          ],
        }) as BpmnModeler;

        ownedModeler = modeler;
        modelerRef.current = modeler;
        keepSequenceConnectionsDocked(modeler);

        const localDraft = readLocalBpmnDraft(bpmnModelId);
        let xml: string;
        if (localDraft) {
          // Una bozza con la sua base non ha bisogno del server; senza base
          // dimostrabile salva contro una base che nessuna versione ha.
          const serverVersion =
            localDraft.baseVersionId === null
              ? (await loadInitialModel(bpmnModelId, processName)).versionId
              : null;
          xml = localDraft.xml;
          setBaseVersion(draftBaseVersion(localDraft.baseVersionId, serverVersion));
        } else {
          const initial = await loadInitialModel(bpmnModelId, processName);
          xml = initial.xml;
          setBaseVersion(initial.versionId);
        }
        if (!isMounted || modelerRef.current !== modeler) return;
        lastSavedXmlRef.current = localDraft ? null : xml;
        isImportingRef.current = true;
        await modeler.importXML(xml);
        if (!isMounted || modelerRef.current !== modeler) return;
        onCurrentXmlChangeRef.current?.(xml);
        isImportingRef.current = false;
        syncEmptiness();

        const eventBus = modeler.get("eventBus") as BpmnEventBus;
        eventBus.on("commandStack.changed", () => {
          syncEmptiness();
          if (!isImportingRef.current && !isSavingRef.current) {
            scheduleUnsavedCheck();
          }
        });

        eventBus.on("selection.changed", (event?: unknown) => {
          const e = event as { newSelection?: BpmnElementSelection[] };
          const selected = e.newSelection?.[0];
          if (!selected || selected.id === "__implicitroot") {
            setSelectedElement(null);
            return;
          }

          const bo = selected.businessObject;
          // Il blocco di tracciabilita' non e' una nota: non si mostra e non si
          // riscrive, cosi' il nodo resta riconoscibile per le evidenze.
          const docs = splitTraceability(bo?.documentation?.[0]?.text).notes;

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
        if (!isMounted) return;
        isImportingRef.current = false;
        if (isMounted) {
          setError(
            err instanceof Error ? err.message : "Canvas BPMN non disponibile",
          );
          setStatus("Errore canvas");
        }
      }
    }

    void mountCanvas();

    return () => {
      isMounted = false;
      clearChangeCheckTimer();
      clearFitTimer();
      ownedModeler?.destroy();
      if (modelerRef.current === ownedModeler) modelerRef.current = null;
      setIsReady(false);
    };
  }, [
    bpmnModelId,
    processName,
    reloadKey,
    propertiesPanelRef,
    loadVersions,
    scheduleUnsavedCheck,
    scheduleCanvasFit,
    syncEmptiness,
  ]);

  useEffect(() => {
    if (!containerRef.current) return;

    const resizeObserver = new ResizeObserver(() => {
      if (modelerRef.current) canvas(modelerRef.current).resized?.();
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      clearFitTimer();
    };
  }, []);

  useEffect(() => {
    return onWorkspaceChanged(async (detail) => {
      if (detail.bpmnModelId && detail.bpmnModelId !== bpmnModelId) return;
      if (
        !modelerRef.current ||
        (hasUnsavedChangesRef.current && !detail.forceCanvasReload)
      )
        return;

      try {
        if (detail.forceCanvasReload) {
          clearDraftTimer();
          clearChangeCheckTimer();
          clearLocalBpmnDraft(bpmnModelId);
          markUnsaved(false);
        }

        const owner = modelerRef.current;
        const loaded = await loadInitialModel(bpmnModelId, processName);
        if (modelerRef.current !== owner) return;
        const { xml } = loaded;
        setBaseVersion(loaded.versionId);
        setHasConflict(false);
        isImportingRef.current = true;
        await owner.importXML(xml);
        if (modelerRef.current !== owner) return;
        onCurrentXmlChangeRef.current?.(xml);
        isImportingRef.current = false;
        syncEmptiness();
        scheduleCanvasFit();
        lastSavedXmlRef.current = xml;
        markUnsaved(false);
        setStatus("Aggiornato dal backend");
        setError(null);
        void loadVersions();
      } catch (err) {
        isImportingRef.current = false;
        setError(
          err instanceof Error
            ? err.message
            : "Aggiornamento canvas non riuscito",
        );
      }
    });
  }, [bpmnModelId, processName, loadVersions, scheduleCanvasFit, syncEmptiness]);

  const save = useCallback(async () => {
    if (!modelerRef.current) return;

    isSavingRef.current = true;
    clearDraftTimer();
    clearChangeCheckTimer();
    setIsSaving(true);
    setError(null);

    try {
      const { xml } = await modelerRef.current.saveXML({ format: true });
      if (!xml) throw new Error("Il canvas non ha restituito XML BPMN.");
      onCurrentXmlChangeRef.current?.(xml);

      const saved = await saveBpmnModelXml(
        bpmnModelId,
        xml,
        savedVersionIdRef.current,
      );
      setBaseVersion(saved.versionId);
      setHasConflict(false);

      clearDraftTimer();
      clearLocalBpmnDraft(bpmnModelId);
      lastSavedXmlRef.current = xml;
      markUnsaved(false);
      setStatus("Salvato");
      void loadVersions();
    } catch (err) {
      if (err instanceof HttpError && err.status === 409) setHasConflict(true);
      setError(httpErrorMessage(err, "Salvataggio BPMN non riuscito"));
      setStatus("Errore salvataggio");
    } finally {
      setIsSaving(false);
      window.setTimeout(() => {
        isSavingRef.current = false;
      }, 250);
    }
  }, [bpmnModelId, loadVersions]);

  // After a 409 the local edits are behind a newer saved version: the way
  // out is to load that version, dropping the local draft.
  const reloadLatest = useCallback(async () => {
    if (!modelerRef.current) return;
    clearDraftTimer();
    clearChangeCheckTimer();
    try {
      const loaded = await loadInitialModel(bpmnModelId, processName);
      isImportingRef.current = true;
      await modelerRef.current.importXML(loaded.xml);
      // Solo adesso: se l'import fallisce, le modifiche in conflitto restano
      // nella bozza e si possono ancora recuperare.
      clearLocalBpmnDraft(bpmnModelId);
      onCurrentXmlChangeRef.current?.(loaded.xml);
      isImportingRef.current = false;
      syncEmptiness();
      scheduleCanvasFit();
      lastSavedXmlRef.current = loaded.xml;
      setBaseVersion(loaded.versionId);
      markUnsaved(false);
      setHasConflict(false);
      setStatus(i18n.t("process:canvas.conflict.reloaded"));
      setError(null);
      void loadVersions();
    } catch (err) {
      isImportingRef.current = false;
      setError(err instanceof Error ? err.message : i18n.t("process:canvas.conflict.reloadFailed"));
    }
  }, [bpmnModelId, processName, loadVersions, scheduleCanvasFit, syncEmptiness]);

  const restoreVersion = useCallback(
    async (versionId: number) => {
      if (!modelerRef.current) return;

      if (hasUnsavedChangesRef.current) {
        setError(
          "Salva o scarta la bozza locale prima di ripristinare una versione.",
        );
        return;
      }

      setRestoringVersionId(versionId);
      setError(null);

      try {
        const model = await restoreBpmnVersionRequest(bpmnModelId, versionId);
        setBaseVersion(model.versionId);
        setHasConflict(false);
        const xml = model.xml;
        if (!xml) throw new Error("La versione ripristinata non contiene XML BPMN.");

        isImportingRef.current = true;
        await modelerRef.current.importXML(xml);
        onCurrentXmlChangeRef.current?.(xml);
        isImportingRef.current = false;
        syncEmptiness();
        clearLocalBpmnDraft(bpmnModelId);
        lastSavedXmlRef.current = xml;
        markUnsaved(false);
        scheduleCanvasFit();
        setStatus(`Ripristinata versione ${versionId}`);
        await loadVersions();
      } catch (err) {
        isImportingRef.current = false;
        setError(httpErrorMessage(err, "Ripristino versione non riuscito"));
      } finally {
        setRestoringVersionId(null);
      }
    },
    [bpmnModelId, loadVersions, scheduleCanvasFit, syncEmptiness],
  );

  const exportXml = useCallback(async () => {
    if (!modelerRef.current) return;

    try {
      const { xml } = await modelerRef.current.saveXML({ format: true });
      if (!xml) throw new Error("Il canvas non ha restituito XML BPMN.");
      onCurrentXmlChangeRef.current?.(xml);
      downloadBpmn(xml, processName);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export BPMN non riuscito");
    }
  }, [processName]);

  const importFile = useCallback(
    async (file: File | undefined) => {
      if (!file || !modelerRef.current) return;

      try {
        const xml = await file.text();
        assertBpmnXml(file, xml);
        isImportingRef.current = true;
        await modelerRef.current.importXML(xml);
        onCurrentXmlChangeRef.current?.(xml);
        isImportingRef.current = false;
        syncEmptiness();
        scheduleCanvasFit();
        markUnsaved(true);
        writeLocalBpmnDraft(bpmnModelId, xml, savedVersionIdRef.current);
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
    },
    [bpmnModelId, scheduleCanvasFit, syncEmptiness],
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void save();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [save]);

  const updateSelectedNodeName = useCallback(
    (newName: string) => {
      if (!modelerRef.current || !selectedElement) return;
      setSelectedElement((prev) => (prev ? { ...prev, name: newName } : null));

      try {
        const elementRegistry = modelerRef.current.get(
          "elementRegistry",
        ) as BpmnElementRegistry;
        const modeling = modelerRef.current.get("modeling") as BpmnModeling;
        const elem = elementRegistry.get?.(selectedElement.id);
        if (elem) {
          modeling.updateProperties(elem, { name: newName });
          scheduleUnsavedCheck();
        }
      } catch (err) {
        console.warn("[bpmn] inline name update failed", err);
      }
    },
    [selectedElement, scheduleUnsavedCheck],
  );

  const updateSelectedNodeDoc = useCallback(
    (newDoc: string) => {
      if (!modelerRef.current || !selectedElement) return;
      setSelectedElement((prev) =>
        prev ? { ...prev, documentation: newDoc } : null,
      );

      try {
        const elementRegistry = modelerRef.current.get(
          "elementRegistry",
        ) as BpmnElementRegistry;
        const bpmnFactory = modelerRef.current.get(
          "bpmnFactory",
        ) as BpmnFactory;
        const modeling = modelerRef.current.get("modeling") as BpmnModeling;
        const elem = elementRegistry.get?.(selectedElement.id) as
          | { businessObject?: { documentation?: Array<{ text?: string }> } }
          | undefined;
        if (elem) {
          const { traceability } = splitTraceability(
            elem.businessObject?.documentation?.[0]?.text,
          );
          const docObj = bpmnFactory.create("bpmn:Documentation", {
            text: withTraceability(newDoc, traceability),
          });
          modeling.updateProperties(elem, { documentation: [docObj] });
          scheduleUnsavedCheck();
        }
      } catch (err) {
        console.warn("[bpmn] inline documentation update failed", err);
      }
    },
    [selectedElement, scheduleUnsavedCheck],
  );

  const zoomBy = useCallback((delta: number) => {
    if (!modelerRef.current) return;
    const canvasService: BpmnCanvasService = canvas(modelerRef.current);
    const currentZoom = (canvasService.zoom() as number) || 1;
    canvasService.zoom(
      Math.min(Math.max(currentZoom + delta, 0.2), 3),
    );
  }, []);

  const zoomIn = useCallback(() => zoomBy(0.2), [zoomBy]);
  const zoomOut = useCallback(() => zoomBy(-0.2), [zoomBy]);
  const zoomFit = useCallback(() => {
    if (modelerRef.current) fitCanvas(modelerRef.current);
  }, []);
  const zoomReadable = useCallback(() => {
    if (modelerRef.current) frameCanvasForReading(modelerRef.current);
  }, []);

  const clearSelection = useCallback(() => {
    focusedElementIdRef.current = null;
    const selection = modelerRef.current?.get("selection") as { select: (elements: unknown[]) => void } | undefined;
    selection?.select([]);
    setSelectedElement(null);
  }, []);

  const selectElement = useCallback((elementId: string) => {
    const modeler = modelerRef.current;
    if (!modeler) return false;
    const registry = modeler.get("elementRegistry") as BpmnElementRegistry;
    const element = registry.get?.(elementId);
    if (!element) return false;
    const selection = modeler.get("selection") as { select: (element: unknown) => void };
    const canvasService = modeler.get("canvas") as {
      scrollToElement?: (element: unknown, padding?: number) => void;
    };
    focusedElementIdRef.current = elementId;
    selection.select(element);
    canvasService.scrollToElement?.(element, 40);
    return true;
  }, []);

  const focusSourceRef = useCallback((sourceRef: string) => {
    const id = provenanceIndexRef.current.get(sourceRef)?.[0];
    return id ? selectElement(id) : false;
  }, [selectElement]);

  const activateTool = useCallback((id: string, action: "click" | "dragstart", event: Event) => {
    const palette = modelerRef.current?.get("palette") as PaletteService | undefined;
    palette?.triggerEntry(id, action, event);
  }, []);

  return {
    creationTools,
    activateTool,
    elements,
    selectElement,
    retryLoad: () => setReloadKey((value) => value + 1),
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
    save: () => void save(),
    hasConflict,
    reloadLatest: () => void reloadLatest(),
    restoreVersion: (versionId: number) => void restoreVersion(versionId),
    exportXml: () => void exportXml(),
    importFile: (file: File | undefined) => void importFile(file),
    zoomIn,
    zoomOut,
    zoomFit,
    zoomReadable,
    focusSourceRef,
  };
}
