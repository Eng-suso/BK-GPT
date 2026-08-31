import React from "react";
import { useTranslation } from "react-i18next";
import NavigatedViewer from "bpmn-js/lib/NavigatedViewer";
import TokenSimulationViewerModule from "bpmn-js-token-simulation/lib/viewer";
import {
  Maximize2,
  Minus,
  PanelLeftOpen,
  Pause,
  Play,
  Plus,
  RotateCcw,
} from "lucide-react";

import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";
import "bpmn-js-token-simulation/assets/css/bpmn-js-token-simulation.css";

import { Button } from "@/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";
import { cn } from "@/lib/utils";

/** One diagram node's simulation annotation. */
export type SimulationNodeOverlay = {
  elementId: string;
  waitLabel: string;
  /** 0 (cool) – 4 (hot) heat bucket by average waiting time. */
  heat: 0 | 1 | 2 | 3 | 4;
  /** Show a text badge (bottleneck + worst few); the rest get a tint only. */
  showBadge: boolean;
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
    opts: {
      position: Record<string, number>;
      html: string;
      scale?: boolean | { min?: number; max?: number };
    },
  ) => string;
  clear: () => void;
};

type Canvas = {
  zoom: (mode?: "fit-viewport" | number, center?: unknown) => number;
  resized?: () => void;
  addMarker: (elementId: string, marker: string) => void;
  removeMarker: (elementId: string, marker: string) => void;
  scrollToElement?: (elementId: string) => void;
};

type ToggleMode = { toggleMode: (active?: boolean) => void };
type PauseSimulation = { toggle: () => void };
type ResetSimulation = { resetSimulation: () => void };
type Animation = { setAnimationSpeed: (speed: number) => void };
type Simulator = {
  findSubscriptions: (opts: { element: unknown }) => unknown[];
  trigger: (subscription: unknown) => void;
};
type ElementRegistry = {
  get: (id: string) => unknown;
  filter: (fn: (el: { type?: string }) => boolean) => Array<{ type?: string }>;
};

const HEAT_MARKERS = ["sim-heat-0", "sim-heat-1", "sim-heat-2", "sim-heat-3", "sim-heat-4"];
const BOTTLENECK_MARKER = "sim-node-bottleneck";
const SELECTED_MARKER = "sim-node-selected";
const SPEEDS = [0.5, 1, 2] as const;

function fitCanvas(viewer: BpmnViewer) {
  try {
    const canvas = viewer.get("canvas") as Canvas;
    canvas.resized?.();
    canvas.zoom("fit-viewport");
  } catch {
    /* not imported yet */
  }
}

type SimulationBpmnViewProps = {
  bpmnXml: string | null | undefined;
  overlays?: SimulationNodeOverlay[];
  selectedElementId?: string | null;
  onSelectElement?: (elementId: string | null) => void;
  /** When set, a leading "open scenario" button appears in the toolbar. */
  onExpandRail?: () => void;
  className?: string;
};

export function SimulationBpmnView({
  bpmnXml,
  overlays = [],
  selectedElementId,
  onSelectElement,
  onExpandRail,
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
  const [speed, setSpeed] = React.useState(1);

  React.useEffect(() => {
    onSelectRef.current = onSelectElement;
  }, [onSelectElement]);

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
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : t("simulation.diagram.loadError"));
      });

    return () => {
      cancelled = true;
    };
  }, [bpmnXml, t]);

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

  // Paint heat tints + bottleneck badges after each run / model change.
  React.useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !ready) return;

    const overlayService = viewer.get("overlays") as Overlays;
    const canvas = viewer.get("canvas") as Canvas;
    const registry = viewer.get("elementRegistry") as ElementRegistry;

    overlayService.clear();
    for (const id of markedRef.current) {
      for (const marker of [...HEAT_MARKERS, BOTTLENECK_MARKER]) {
        try {
          canvas.removeMarker(id, marker);
        } catch {
          /* element gone after re-import */
        }
      }
    }
    markedRef.current = [];

    let badgeIndex = 0;
    for (const item of overlays) {
      if (!registry.get(item.elementId)) continue;
      canvas.addMarker(item.elementId, HEAT_MARKERS[item.heat]);
      if (item.isBottleneck) canvas.addMarker(item.elementId, BOTTLENECK_MARKER);
      markedRef.current.push(item.elementId);

      if (item.showBadge) {
        overlayService.add(item.elementId, {
          position: { top: badgeIndex % 2 === 0 ? -12 : -30, left: -4 },
          scale: { min: 1 },
          html: `<div class="sim-badge${
            item.isBottleneck ? " is-bottleneck" : ""
          }">${escapeHtml(item.waitLabel)}</div>`,
        });
        badgeIndex += 1;
      }
    }
  }, [overlays, ready]);

  React.useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !ready || !selectedElementId) return;
    const canvas = viewer.get("canvas") as Canvas;
    const registry = viewer.get("elementRegistry") as ElementRegistry;
    if (!registry.get(selectedElementId)) return;
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

  function svc<T>(name: string): T | null {
    try {
      return (viewerRef.current?.get(name) as T) ?? null;
    } catch {
      return null;
    }
  }

  function setTokenSimulation(active: boolean) {
    const toggle = svc<ToggleMode>("toggleMode");
    if (!toggle) return;
    toggle.toggleMode(active);
    setSimActive(active);
    setSimPaused(true);
  }

  function playCase() {
    if (!simActive) setTokenSimulation(true);
    window.requestAnimationFrame(() => {
      const simulator = svc<Simulator>("simulator");
      const registry = svc<ElementRegistry>("elementRegistry");
      if (!simulator || !registry) return;
      const start = registry.filter((el) => el.type === "bpmn:StartEvent").at(0);
      if (!start) {
        setError(t("simulation.diagram.noStart"));
        return;
      }
      const [subscription] = simulator.findSubscriptions({ element: start });
      if (!subscription) return;
      simulator.trigger(subscription);
      setSimPaused(false);
      setError(null);
    });
  }

  function togglePause() {
    if (!simActive) return;
    svc<PauseSimulation>("pauseSimulation")?.toggle();
    setSimPaused((prev) => !prev);
  }

  function resetSim() {
    if (!simActive) return;
    svc<ResetSimulation>("resetSimulation")?.resetSimulation();
    setSimPaused(true);
  }

  function changeSpeed(next: number) {
    setSpeed(next);
    svc<Animation>("animation")?.setAnimationSpeed(next);
  }

  function nudgeZoom(factor: number) {
    const canvas = svc<Canvas>("canvas");
    if (!canvas) return;
    const current = canvas.zoom() || 1;
    canvas.zoom(Math.max(0.2, Math.min(4, current * factor)));
  }

  return (
    <div className={cn("simulation-bpmn-view relative flex min-h-0 flex-col", className)}>
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-2.5 py-2">
        {onExpandRail && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="mr-0.5 size-8 p-0 text-muted-foreground"
            onClick={onExpandRail}
            title={t("simulation.config.expand")}
          >
            <PanelLeftOpen className="size-4" />
          </Button>
        )}
        {!simActive ? (
          <Button type="button" size="sm" variant="outline" onClick={playCase} disabled={!ready}>
            <Play aria-hidden className="size-3.5" />
            {t("simulation.diagram.animate")}
          </Button>
        ) : (
          <>
            <Button type="button" size="sm" variant="outline" onClick={togglePause}>
              {simPaused ? (
                <Play aria-hidden className="size-3.5" />
              ) : (
                <Pause aria-hidden className="size-3.5" />
              )}
              {simPaused ? t("simulation.diagram.resume") : t("simulation.diagram.pause")}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={playCase} disabled={!ready}>
              <Plus aria-hidden className="size-3.5" />
              {t("simulation.diagram.newCase")}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={resetSim}>
              <RotateCcw aria-hidden className="size-3.5" />
              {t("simulation.diagram.reset")}
            </Button>
            <Select value={String(speed)} onValueChange={(v) => changeSpeed(Number(v))}>
              <SelectTrigger size="sm" className="w-[72px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SPEEDS.map((s) => (
                  <SelectItem key={s} value={String(s)}>
                    {s}×
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </>
        )}

        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="size-8 p-0 text-muted-foreground"
            onClick={() => nudgeZoom(1 / 1.2)}
            disabled={!ready}
            title={t("simulation.diagram.zoomOut")}
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
            title={t("simulation.diagram.zoomIn")}
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
            title={t("simulation.diagram.fit")}
          >
            <Maximize2 aria-hidden className="size-3.5" />
          </Button>
        </div>
      </div>

      {overlays.length > 0 && (
        <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-2.5 py-1.5 text-[11px] text-muted-foreground">
          <span className="font-medium">{t("simulation.diagram.legendWait")}</span>
          <span className="flex overflow-hidden rounded-full">
            {HEAT_MARKERS.map((_, i) => (
              <span
                key={i}
                className="h-2 w-4"
                style={{ background: `var(--sim-heat-${i})` }}
                aria-hidden
              />
            ))}
          </span>
          <span
            className="ml-2 inline-flex items-center gap-1.5 rounded-full border px-1.5 py-0.5"
            style={{
              borderColor: "var(--sim-bottleneck-border)",
              background: "var(--sim-bottleneck-surface)",
            }}
          >
            <span
              className="size-1.5 rounded-full"
              style={{ background: "var(--color-status-warning)" }}
              aria-hidden
            />
            {t("simulation.results.bottleneck")}
          </span>
        </div>
      )}

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

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
