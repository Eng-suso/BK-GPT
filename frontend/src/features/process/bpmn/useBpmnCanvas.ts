import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import Modeler from "bpmn-js/lib/Modeler";
import {
  BpmnPropertiesPanelModule,
  BpmnPropertiesProviderModule,
} from "bpmn-js-properties-panel";

import { httpErrorMessage } from "@/lib/http";
import type { BpmnVersion } from "@/contracts/workspace";
import { onWorkspaceChanged } from "@/lib/workspaceEvents";
import {
  fetchBpmnVersions,
  restoreBpmnVersion as restoreBpmnVersionRequest,
  saveBpmnModelXml,
} from "../api";
import {
  clearLocalBpmnDraft,
  readLocalBpmnDraft,
  writeLocalBpmnDraft,
} from "./draft";
import { canvas, fitCanvas, keepSequenceConnectionsDocked } from "./viewport";
import { assertBpmnXml, downloadBpmn, loadInitialXml } from "./xml";
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
};

export type UseBpmnCanvas = {
  containerRef: RefObject<HTMLDivElement | null>;
  fileInputRef: RefObject<HTMLInputElement | null>;
  isReady: boolean;
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
  restoreVersion: (versionId: number) => void;
  exportXml: () => void;
  importFile: (file: File | undefined) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  zoomFit: () => void;
};

export function useBpmnCanvas({
  bpmnModelId,
  processName,
  propertiesPanelRef,
  onCurrentXmlChange,
}: UseBpmnCanvasArgs): UseBpmnCanvas {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const modelerRef = useRef<BpmnModeler | null>(null);
  const hasUnsavedChangesRef = useRef(false);
  const isImportingRef = useRef(false);
  const isSavingRef = useRef(false);
  const draftSaveTimerRef = useRef<number | null>(null);
  const changeCheckTimerRef = useRef<number | null>(null);
  const fitTimerRef = useRef<number | null>(null);
  const lastSavedXmlRef = useRef<string | null>(null);
  const onCurrentXmlChangeRef = useRef(onCurrentXmlChange);

  const [status, setStatus] = useState("Caricamento canvas...");
  const [error, setError] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [restoringVersionId, setRestoringVersionId] = useState<number | null>(
    null,
  );
  const [versions, setVersions] = useState<BpmnVersion[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [selectedElement, setSelectedElement] =
    useState<SelectedBpmnElement | null>(null);

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
          writeLocalBpmnDraft(bpmnModelId, xml);
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

  // Debounced: one fit after the layout settles. Collapses the burst of
  // ResizeObserver callbacks fired while the user drags the chat splitter, and
  // the double mount/import fit, into a single reframe.
  const scheduleCanvasFit = useCallback(() => {
    if (fitTimerRef.current) window.clearTimeout(fitTimerRef.current);
    fitTimerRef.current = window.setTimeout(() => {
      fitTimerRef.current = null;
      if (document.hidden || !modelerRef.current) return;
      fitCanvas(modelerRef.current);
    }, 100);
  }, []);

  const loadVersions = useCallback(async () => {
    try {
      setVersions(await fetchBpmnVersions(bpmnModelId));
    } catch (err) {
      console.warn("[bpmn] version history load failed", err);
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
            BpmnPropertiesPanelModule,
            BpmnPropertiesProviderModule,
          ],
        }) as BpmnModeler;

        modelerRef.current = modeler;
        keepSequenceConnectionsDocked(modeler);

        const localDraft = readLocalBpmnDraft(bpmnModelId);
        const xml = localDraft ?? (await loadInitialXml(bpmnModelId, processName));
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

        eventBus.on("selection.changed", (event?: unknown) => {
          const e = event as { newSelection?: BpmnElementSelection[] };
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
      modelerRef.current?.destroy();
      modelerRef.current = null;
      setIsReady(false);
    };
  }, [
    bpmnModelId,
    processName,
    propertiesPanelRef,
    loadVersions,
    scheduleUnsavedCheck,
    scheduleCanvasFit,
  ]);

  useEffect(() => {
    if (!containerRef.current) return;

    const resizeObserver = new ResizeObserver(() => {
      scheduleCanvasFit();
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      clearFitTimer();
    };
  }, [scheduleCanvasFit]);

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
        setError(
          err instanceof Error
            ? err.message
            : "Aggiornamento canvas non riuscito",
        );
      }
    });
  }, [bpmnModelId, processName, loadVersions, scheduleCanvasFit]);

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

      await saveBpmnModelXml(bpmnModelId, xml);

      clearDraftTimer();
      clearLocalBpmnDraft(bpmnModelId);
      lastSavedXmlRef.current = xml;
      markUnsaved(false);
      setStatus("Salvato");
      void loadVersions();
    } catch (err) {
      setError(httpErrorMessage(err, "Salvataggio BPMN non riuscito"));
      setStatus("Errore salvataggio");
    } finally {
      setIsSaving(false);
      window.setTimeout(() => {
        isSavingRef.current = false;
      }, 250);
    }
  }, [bpmnModelId, loadVersions]);

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
        const xml = model.xml;
        if (!xml) throw new Error("La versione ripristinata non contiene XML BPMN.");

        isImportingRef.current = true;
        await modelerRef.current.importXML(xml);
        onCurrentXmlChangeRef.current?.(xml);
        isImportingRef.current = false;
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
    [bpmnModelId, loadVersions, scheduleCanvasFit],
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
    },
    [bpmnModelId, scheduleCanvasFit],
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
        const elem = elementRegistry.get?.(selectedElement.id);
        if (elem) {
          const docObj = bpmnFactory.create("bpmn:Documentation", {
            text: newDoc,
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

  const clearSelection = useCallback(() => setSelectedElement(null), []);

  return {
    containerRef,
    fileInputRef,
    isReady,
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
    restoreVersion: (versionId: number) => void restoreVersion(versionId),
    exportXml: () => void exportXml(),
    importFile: (file: File | undefined) => void importFile(file),
    zoomIn,
    zoomOut,
    zoomFit,
  };
}
