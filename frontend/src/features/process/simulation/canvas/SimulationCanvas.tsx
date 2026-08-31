import React from "react";
import { useTranslation } from "react-i18next";
import NavigatedViewer from "bpmn-js/lib/NavigatedViewer";
import { Maximize2, Minus, Plus } from "lucide-react";

import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";

import {
  svc,
  type BpmnCanvas,
  type BpmnElementRegistry,
  type BpmnOverlays,
  type BpmnViewer,
} from "./bpmnViewer";

/** One node's simulation annotation: marker classes + an optional badge. */
export type NodeDecoration = {
  elementId: string;
  markers?: string[];
  /** Small HTML pill rendered above the node (already escaped by the caller). */
  badge?: string;
  badgeTone?: "neutral" | "warning" | "danger";
};

const SELECTED_MARKER = "sim-node-selected";

type SimulationCanvasProps = {
  bpmnXml: string | null | undefined;
  decorations?: NodeDecoration[];
  selectedElementId?: string | null;
  onSelectElement?: (elementId: string | null) => void;
  /** Called once the viewer has imported the diagram — lets a token layer grab
   *  `elementRegistry` / `canvas`. Called again with null on teardown. */
  onViewerReady?: (viewer: BpmnViewer | null) => void;
  /** Extra controls rendered on the left of the toolbar. */
  toolbarStart?: React.ReactNode;
  className?: string;
};

function fitCanvas(viewer: BpmnViewer): void {
  try {
    const canvas = svc<BpmnCanvas>(viewer, "canvas");
    canvas?.resized?.();
    canvas?.zoom("fit-viewport");
  } catch {
    /* not imported yet */
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function SimulationCanvas({
  bpmnXml,
  decorations = [],
  selectedElementId,
  onSelectElement,
  onViewerReady,
  toolbarStart,
  className,
}: SimulationCanvasProps): React.JSX.Element {
  const { t } = useTranslation("process");
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const viewerRef = React.useRef<BpmnViewer | null>(null);
  const markedRef = React.useRef<string[]>([]);
  const onSelectRef = React.useRef(onSelectElement);
  const onReadyRef = React.useRef(onViewerReady);
  const [ready, setReady] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    onSelectRef.current = onSelectElement;
    onReadyRef.current = onViewerReady;
  });

  // -- viewer lifecycle ------------------------------------------------
  React.useEffect(() => {
    if (!containerRef.current) return;
    const viewer = new NavigatedViewer({
      container: containerRef.current,
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
      onReadyRef.current?.(null);
      viewer.destroy();
      viewerRef.current = null;
      setReady(false);
    };
  }, []);

  // -- import ------------------------------------------------------
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
        window.requestAnimationFrame(() => !cancelled && fitCanvas(viewer));
        window.setTimeout(() => !cancelled && fitCanvas(viewer), 150);
        setReady(true);
        onReadyRef.current?.(viewer);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : t("simulation.diagram.loadError"));
      });

    return () => {
      cancelled = true;
    };
  }, [bpmnXml, t]);

  // -- keep fitted on resize ----------------------------------------
  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      const viewer = viewerRef.current;
      if (viewer && ready) window.requestAnimationFrame(() => fitCanvas(viewer));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ready]);

  // -- decorations (markers + badges) ------------------------------
  React.useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !ready) return;

    const overlays = svc<BpmnOverlays>(viewer, "overlays");
    const canvas = svc<BpmnCanvas>(viewer, "canvas");
    const registry = svc<BpmnElementRegistry>(viewer, "elementRegistry");
    if (!overlays || !canvas || !registry) return;

    overlays.clear();
    for (const id of markedRef.current) {
      const el = registry.get(id);
      if (!el) continue;
      // markers are re-applied below; strip the full known set first
      for (const marker of KNOWN_MARKERS) {
        try {
          canvas.removeMarker(id, marker);
        } catch {
          /* element gone */
        }
      }
    }
    markedRef.current = [];

    let badgeIndex = 0;
    for (const item of decorations) {
      if (!registry.get(item.elementId)) continue;
      for (const marker of item.markers ?? []) canvas.addMarker(item.elementId, marker);
      markedRef.current.push(item.elementId);

      if (item.badge) {
        overlays.add(item.elementId, {
          position: { top: badgeIndex % 2 === 0 ? -12 : -30, left: -4 },
          scale: { min: 1 },
          html: `<div class="sim-badge${
            item.badgeTone && item.badgeTone !== "neutral"
              ? ` is-${item.badgeTone}`
              : ""
          }">${escapeHtml(item.badge)}</div>`,
        });
        badgeIndex += 1;
      }
    }
  }, [decorations, ready]);

  // -- selection highlight ---------------------------------------
  React.useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !ready || !selectedElementId) return;
    const canvas = svc<BpmnCanvas>(viewer, "canvas");
    const registry = svc<BpmnElementRegistry>(viewer, "elementRegistry");
    if (!canvas || !registry?.get(selectedElementId)) return;
    canvas.scrollToElement?.(selectedElementId);
    canvas.addMarker(selectedElementId, SELECTED_MARKER);
    return () => {
      try {
        canvas.removeMarker(selectedElementId, SELECTED_MARKER);
      } catch {
        /* ignore */
      }
    };
  }, [selectedElementId, ready]);

  function nudgeZoom(factor: number): void {
    const canvas = svc<BpmnCanvas>(viewerRef.current, "canvas");
    if (!canvas) return;
    const current = canvas.zoom() || 1;
    canvas.zoom(Math.max(0.2, Math.min(4, current * factor)));
  }

  return (
    <div className={cn("simulation-bpmn-view relative flex min-h-0 flex-col", className)}>
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-2.5 py-2">
        {toolbarStart}
        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="size-8 p-0 text-muted-foreground"
            onClick={() => nudgeZoom(1 / 1.2)}
            disabled={!ready}
            aria-label={t("simulation.diagram.zoomOut")}
          >
            <Minus aria-hidden className="size-3.5" />
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="size-8 p-0 text-muted-foreground"
            onClick={() => nudgeZoom(1.2)}
            disabled={!ready}
            aria-label={t("simulation.diagram.zoomIn")}
          >
            <Plus aria-hidden className="size-3.5" />
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="size-8 p-0 text-muted-foreground"
            onClick={() => viewerRef.current && fitCanvas(viewerRef.current)}
            disabled={!ready}
            aria-label={t("simulation.diagram.fit")}
          >
            <Maximize2 aria-hidden className="size-3.5" />
          </Button>
        </div>
      </div>

      <div ref={containerRef} className="min-h-0 w-full flex-1 overflow-hidden bg-card" />

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

const KNOWN_MARKERS = [
  "sim-heat-0",
  "sim-heat-1",
  "sim-heat-2",
  "sim-heat-3",
  "sim-heat-4",
  "sim-node-bottleneck",
  "sim-pressure-building",
  "sim-pressure-high",
  "sim-pressure-saturated",
  "sim-delta-better",
  "sim-delta-worse",
  "sim-delta-neutral",
];
