import React from "react";
import { useTranslation } from "react-i18next";
import NavigatedViewer from "bpmn-js/lib/NavigatedViewer";
import TokenSimulationViewerModule from "bpmn-js-token-simulation/lib/viewer";
import { Gauge, Maximize2, Pause, Play, RotateCcw } from "lucide-react";

import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";
import "bpmn-js-token-simulation/assets/css/bpmn-js-token-simulation.css";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";

/** Per-node KPI badge shown on the diagram after a Prosimos run. */
export type SimulationNodeOverlay = {
  elementId: string;
  waitLabel: string;
  utilizationPct?: number;
  isBottleneck: boolean;
};

type BpmnViewer = {
  importXML: (xml: string) => Promise<{ warnings?: unknown[] }>;
  destroy: () => void;
  get: (name: string) => unknown;
  on: (event: string, cb: (e: unknown) => void) => void;
};

type Overlays = {
  add: (
    elementId: string,
    opts: { position: Record<string, number>; html: string; scale?: boolean | { min?: number; max?: number } },
  ) => string;
  clear: () => void;
};

type Canvas = {
  zoom: (mode: "fit-viewport" | number, center?: unknown) => void;
  resized?: () => void;
  addMarker: (elementId: string, marker: string) => void;
  removeMarker: (elementId: string, marker: string) => void;
  scrollToElement?: (elementId: string) => void;
};

function fitCanvas(viewer: BpmnViewer) {
  try {
    const canvas = viewer.get("canvas") as Canvas;
    canvas.resized?.();
    canvas.zoom("fit-viewport");
  } catch {
    /* not imported yet */
  }
}

type ToggleMode = { toggleMode: (active?: boolean) => void };
type PauseSimulation = { toggle: () => void; pause: () => void; unpause: () => void };
type ResetSimulation = { resetSimulation: () => void };
type Simulator = {
  findSubscriptions: (opts: { element: unknown }) => unknown[];
  trigger: (subscription: unknown) => void;
};
type ElementRegistry = {
  get: (id: string) => unknown;
  filter: (fn: (el: { type?: string }) => boolean) => Array<{ type?: string }>;
};

type SimulationBpmnViewProps = {
  bpmnXml: string | null | undefined;
  overlays?: SimulationNodeOverlay[];
  selectedElementId?: string | null;
  onSelectElement?: (elementId: string | null) => void;
  className?: string;
};

const BOTTLENECK_MARKER = "sim-node-bottleneck";
const ANNOTATED_MARKER = "sim-node-annotated";

export function SimulationBpmnView({
  bpmnXml,
  overlays = [],
  selectedElementId,
  onSelectElement,
  className,
}: SimulationBpmnViewProps): React.JSX.Element {
  const { t } = useTranslation("process");
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const viewerRef = React.useRef<BpmnViewer | null>(null);
  const markedRef = React.useRef<string[]>([]);
  const onSelectRef = React.useRef(onSelectElement);
  const [ready, setReady] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [simActive, setSimActive] = React.useState(false);
  const [simPaused, setSimPaused] = React.useState(true);

  React.useEffect(() => {
    onSelectRef.current = onSelectElement;
  }, [onSelectElement]);

  // Mount the viewer once.
  React.useEffect(() => {
    if (!containerRef.current) return;
    const viewer = new NavigatedViewer({
      container: containerRef.current,
      additionalModules: [TokenSimulationViewerModule],
    }) as unknown as BpmnViewer;
    viewerRef.current = viewer;

    viewer.on("element.click", (event: unknown) => {
      const el = (event as { element?: { id?: string; type?: string } }).element;
      if (!el?.id || el.type === "bpmn:Process" || el.type === "label") {
        onSelectRef.current?.(null);
        return;
      }
      onSelectRef.current?.(el.id);
    });

    return () => {
      viewer.destroy();
      viewerRef.current = null;
      setReady(false);
    };
  }, []);

  // (Re)import whenever the model changes.
  React.useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !bpmnXml) return;
    let cancelled = false;

    setReady(false);
    setError(null);
    viewer
      .importXML(bpmnXml)
      .then(() => {
        if (cancelled) return;
        fitCanvas(viewer);
        // Container height often settles a frame later in the grid.
        window.requestAnimationFrame(() => !cancelled && fitCanvas(viewer));
        window.setTimeout(() => !cancelled && fitCanvas(viewer), 150);
        setReady(true);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Diagramma non caricabile.");
      });

    return () => {
      cancelled = true;
    };
  }, [bpmnXml]);

  // Keep the diagram fitted as the split layout resizes.
  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      const viewer = viewerRef.current;
      if (!viewer || !ready) return;
      window.requestAnimationFrame(() => fitCanvas(viewer));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ready]);

  // Paint KPI overlays + heat markers after each run / model change.
  React.useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !ready) return;

    const overlayService = viewer.get("overlays") as Overlays;
    const canvas = viewer.get("canvas") as Canvas;
    const registry = viewer.get("elementRegistry") as ElementRegistry;

    overlayService.clear();
    for (const id of markedRef.current) {
      try {
        canvas.removeMarker(id, BOTTLENECK_MARKER);
        canvas.removeMarker(id, ANNOTATED_MARKER);
      } catch {
        /* element gone after re-import */
      }
    }
    markedRef.current = [];

    for (const item of overlays) {
      if (!registry.get(item.elementId)) continue;
      const util =
        typeof item.utilizationPct === "number"
          ? `<span class="sim-badge-util">${item.utilizationPct}%</span>`
          : "";
      overlayService.add(item.elementId, {
        position: { top: -12, left: -4 },
        scale: { min: 1 },
        html: `<div class="sim-badge${item.isBottleneck ? " is-bottleneck" : ""}"><span class="sim-badge-wait">${escapeHtml(item.waitLabel)}</span>${util}</div>`,
      });
      canvas.addMarker(
        item.elementId,
        item.isBottleneck ? BOTTLENECK_MARKER : ANNOTATED_MARKER,
      );
      markedRef.current.push(item.elementId);
    }
  }, [overlays, ready]);

  // Reflect external selection.
  React.useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !ready || !selectedElementId) return;
    const canvas = viewer.get("canvas") as Canvas;
    const registry = viewer.get("elementRegistry") as ElementRegistry;
    if (!registry.get(selectedElementId)) return;
    canvas.scrollToElement?.(selectedElementId);
    canvas.addMarker(selectedElementId, "sim-node-selected");
    return () => {
      try {
        canvas.removeMarker(selectedElementId, "sim-node-selected");
      } catch {
        /* ignore */
      }
    };
  }, [selectedElementId, ready]);

  function setTokenSimulation(active: boolean) {
    const viewer = viewerRef.current;
    if (!viewer) return;
    try {
      (viewer.get("toggleMode") as ToggleMode).toggleMode(active);
      setSimActive(active);
      setSimPaused(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulazione visiva non disponibile.");
    }
  }

  function playCase() {
    const viewer = viewerRef.current;
    if (!viewer) return;
    if (!simActive) setTokenSimulation(true);
    window.requestAnimationFrame(() => {
      const v = viewerRef.current;
      if (!v) return;
      try {
        const simulator = v.get("simulator") as Simulator;
        const registry = v.get("elementRegistry") as ElementRegistry;
        const start = registry
          .filter((el) => el.type === "bpmn:StartEvent")
          .at(0);
        if (!start) {
          setError("Il modello non ha uno start event.");
          return;
        }
        const [subscription] = simulator.findSubscriptions({ element: start });
        if (!subscription) return;
        simulator.trigger(subscription);
        setSimPaused(false);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Avvio animazione non riuscito.");
      }
    });
  }

  function togglePause() {
    const viewer = viewerRef.current;
    if (!viewer || !simActive) return;
    try {
      (viewer.get("pauseSimulation") as PauseSimulation).toggle();
      setSimPaused((prev) => !prev);
    } catch {
      /* ignore */
    }
  }

  function resetSim() {
    const viewer = viewerRef.current;
    if (!viewer || !simActive) return;
    try {
      (viewer.get("resetSimulation") as ResetSimulation).resetSimulation();
      setSimPaused(true);
    } catch {
      /* ignore */
    }
  }

  function fit() {
    if (viewerRef.current) fitCanvas(viewerRef.current);
  }

  return (
    <div className={cn("simulation-bpmn-view relative flex min-h-0 flex-col", className)}>
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-2.5 py-1.5">
        <Gauge aria-hidden className="mr-0.5 size-3.5 text-muted-foreground" />
        {!simActive ? (
          <Button type="button" size="sm" variant="outline" onClick={playCase} disabled={!ready}>
            <Play aria-hidden className="size-3.5" /> {t("simulation.diagram.animate")}
          </Button>
        ) : (
          <>
            <Button type="button" size="sm" variant="outline" onClick={togglePause}>
              {simPaused ? <Play aria-hidden className="size-3.5" /> : <Pause aria-hidden className="size-3.5" />}
              {simPaused ? t("simulation.diagram.resume") : t("simulation.diagram.pause")}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={playCase} disabled={!ready}>
              <Play aria-hidden className="size-3.5" /> {t("simulation.diagram.newCase")}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={resetSim}>
              <RotateCcw aria-hidden className="size-3.5" /> {t("simulation.diagram.reset")}
            </Button>
          </>
        )}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="ml-auto text-muted-foreground"
          onClick={fit}
          disabled={!ready}
          title={t("simulation.diagram.fit")}
        >
          <Maximize2 aria-hidden className="size-3.5" />
        </Button>
      </div>

      {overlays.length > 0 && (
        <p className="border-b border-border bg-muted/30 px-2.5 py-1 text-[11px] text-muted-foreground">
          {t("simulation.diagram.legend")}
        </p>
      )}

      <div
        ref={containerRef}
        className="min-h-0 w-full flex-1 overflow-hidden bg-card"
      />

      {error && (
        <p
          role="alert"
          className="absolute inset-x-2 bottom-2 rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-1.5 text-xs font-medium text-destructive"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
