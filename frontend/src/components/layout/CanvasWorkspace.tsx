import React from "react";
import { MoveDiagonal2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";
import { Surface } from "@/ui/surface";

type Slot = React.ReactNode;

/** Context identifies the document; commands and analytical content belong below it. */
export function WorkspaceContextBar({ title, navigation, actions, className }: { title: string; navigation?: Slot; actions?: Slot; className?: string }): React.JSX.Element {
  return <header data-workspace-layer="context" className={cn("flex min-w-0 shrink-0 items-center gap-3 border-b border-border px-4 py-2", className)}>
    {navigation}<h1 title={title} className="min-w-0 flex-1 truncate text-base font-semibold tracking-tight">{title}</h1>
    {actions && <div className="flex min-w-0 shrink-0 items-center gap-2">{actions}</div>}
  </header>;
}

/** A labelled command group, without implying toolbar arrow-key behavior. */
export function WorkspaceCommandBar({ label, children, className }: { label: string; children: Slot; className?: string }): React.JSX.Element {
  return <Surface asChild variant="toolbar"><div data-workspace-layer="commands" role="group" aria-label={label} className={cn("flex shrink-0 flex-wrap items-center gap-2 px-2 py-1.5", className)}>{children}</div></Surface>;
}

/** The stage owns available height. Inspectors and playback never stack above it. */
export function CanvasWorkspaceShell({ label, commands, children, inspector, playback, resizeLabel, resizeHint, className, bodyClassName, stageClassName }: { label: string; commands?: Slot; children: Slot; inspector?: Slot; playback?: Slot; resizeLabel?: string; resizeHint?: string; className?: string; bodyClassName?: string; stageClassName?: string }): React.JSX.Element {
  const body = React.useRef<HTMLDivElement>(null);
  const stage = React.useRef<HTMLDivElement>(null);
  const [available, setAvailable] = React.useState({ width: 0, height: 0 });
  const [size, setSize] = React.useState<{ width: number; height: number } | null>(null);
  const gesture = React.useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  React.useLayoutEffect(() => {
    const element = body.current;
    if (!element) return;
    const observer = new ResizeObserver(() => {
      const panel = element.querySelector<HTMLElement>('[data-workspace-layer="inspector"]');
      const panelWidth = panel?.offsetWidth ?? 0;
      setAvailable({ width: Math.max(1, element.clientWidth - panelWidth - (panelWidth ? 12 : 0)), height: element.clientHeight });
    });
    observer.observe(element);
    const panel = element.querySelector<HTMLElement>('[data-workspace-layer="inspector"]');
    if (panel) observer.observe(panel);
    return () => observer.disconnect();
  }, []);
  const clamp = (next: { width: number; height: number }) => ({ width: Math.max(Math.min(320, available.width), Math.min(available.width, next.width)), height: Math.max(Math.min(280, available.height), Math.min(available.height, next.height)) });
  const current = size ? clamp(size) : available;
  return <section data-workspace-layer="workspace" aria-label={label} className={cn("ui-scrollbar flex h-full min-h-0 min-w-0 flex-col gap-2", className)}>
    <h2 className="sr-only">{label}</h2>{commands}<div ref={body} data-workspace-layer="body" className={cn("flex min-h-0 min-w-0 flex-1 gap-3", bodyClassName)}>
      <div ref={stage} data-workspace-layer="stage" className={cn("ui-workspace-stage relative flex min-h-0 min-w-0 flex-1 flex-col", stageClassName)} style={size ? { flex: `0 0 ${current.width}px`, height: current.height, alignSelf: "flex-start" } : undefined}>{children}
        {resizeLabel && <CanvasResizeHandle className="ui-workspace-stage-resize" label={resizeLabel} hint={resizeHint} aria-description={`${Math.round(current.width)} × ${Math.round(current.height)} px`} onPointerDown={event => {
          if (event.button !== 0 || !stage.current) return;
          const rect = stage.current.getBoundingClientRect();
          gesture.current = { x: event.clientX, y: event.clientY, width: rect.width, height: rect.height };
          event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
        }} onPointerMove={event => { const start = gesture.current; if (start) setSize(clamp({ width: start.width + event.clientX - start.x, height: start.height + event.clientY - start.y })); }} onPointerUp={() => { gesture.current = null; }} onPointerCancel={() => { gesture.current = null; }} onKeyDown={event => {
          const steps: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] };
          const step = steps[event.key];
          if (step) { event.preventDefault(); setSize(clamp({ width: current.width + step[0], height: current.height + step[1] })); }
          if (event.key === "Home") { event.preventDefault(); setSize(null); }
        }} />}
      </div>{inspector}
    </div>{playback && <Surface asChild variant="toolbar"><div data-workspace-layer="playback" className="shrink-0">{playback}</div></Surface>}
  </section>;
}

export const WorkspaceInspector = React.forwardRef<HTMLElement, { label: string; title: string; scope?: string; closeLabel: string; onClose: () => void; children: Slot; hidden?: boolean; resizeLabel?: string; initialWidth?: number; className?: string; bodyClassName?: string }>(({ label, title, scope, closeLabel, onClose, children, hidden, resizeLabel, initialWidth = 400, className, bodyClassName }, forwardedRef) => {
  const element = React.useRef<HTMLElement | null>(null);
  const [width, setWidth] = React.useState<number | null>(null);
  const [maximum, setMaximum] = React.useState(760);
  const setRef = React.useCallback((node: HTMLElement | null) => {
    element.current = node;
    if (typeof forwardedRef === "function") forwardedRef(node); else if (forwardedRef) forwardedRef.current = node;
  }, [forwardedRef]);
  React.useLayoutEffect(() => {
    const parent = element.current?.parentElement;
    if (!parent) return;
    const observer = new ResizeObserver(() => setMaximum(Math.max(320, Math.min(760, parent.clientWidth - 492))));
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);
  const current = Math.max(320, Math.min(maximum, width ?? initialWidth));
  return <Surface asChild variant="panel"><aside ref={setRef} hidden={hidden} aria-label={label} data-workspace-layer="inspector" style={resizeLabel ? { "--workspace-inspector-width": `${current}px` } as React.CSSProperties : undefined} className={cn("ui-workspace-inspector relative flex min-h-0 shrink-0 flex-col overflow-hidden", className)} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }}>
    {resizeLabel && <WorkspaceResizeSeparator label={resizeLabel} value={current} minimum={320} maximum={maximum} onResize={setWidth} />}
    <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3"><div className="min-w-0">{scope && <p className="text-xs text-muted-foreground">{scope}</p>}<h2 data-dock-title tabIndex={-1} className="text-sm font-semibold focus-visible:outline-2 focus-visible:outline-ring">{title}</h2></div><Button size="icon" variant="ghost" onClick={onClose} aria-label={closeLabel}><X aria-hidden className="size-4" /></Button></header>
    <div className={cn("ui-scrollbar min-h-0 flex-1 overflow-auto p-4", bodyClassName)}>{children}</div>
  </aside></Surface>;
});
WorkspaceInspector.displayName = "WorkspaceInspector";

/** A keyboard-accessible splitter, with a quiet visual rail and a stable hit area. */
export function WorkspaceResizeSeparator({ label, value, minimum, maximum, onResize }: { label: string; value: number; minimum: number; maximum: number; onResize: (value: number) => void }): React.JSX.Element {
  const gesture = React.useRef<{ x: number; value: number } | null>(null);
  const change = (next: number) => onResize(Math.max(minimum, Math.min(maximum, next)));
  return <div role="separator" tabIndex={0} aria-label={label} aria-orientation="vertical" aria-valuemin={minimum} aria-valuemax={maximum} aria-valuenow={value} aria-valuetext={`${Math.round(value)} px`} className="ui-workspace-splitter" onPointerDown={event => {
    if (event.button !== 0) return;
    event.preventDefault(); gesture.current = { x: event.clientX, value }; event.currentTarget.setPointerCapture(event.pointerId);
  }} onPointerMove={event => { const start = gesture.current; if (start) change(start.value + start.x - event.clientX); }} onPointerUp={() => { gesture.current = null; }} onPointerCancel={() => { gesture.current = null; }} onKeyDown={event => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); change(value + (event.key === "ArrowLeft" ? 20 : -20)); }
    if (event.key === "Home" || event.key === "End") { event.preventDefault(); change(event.key === "Home" ? minimum : maximum); }
  }}><span aria-hidden /></div>;
}

/** Native disclosure keeps secondary data mounted and accessible when requested. */
export function WorkspaceDisclosure({ label, children, className, contentClassName }: { label: string; children: Slot; className?: string; contentClassName?: string }): React.JSX.Element {
  const ref = React.useRef<HTMLDetailsElement>(null);
  const [expanded, setExpanded] = React.useState(false);
  const contentId = React.useId();
  React.useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (ref.current?.open && event.target instanceof Node && !ref.current.contains(event.target)) ref.current.open = false;
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);
  return <details ref={ref} onToggle={event => {
    setExpanded(event.currentTarget.open);
    if (!event.currentTarget.open) return;
    const workspace = event.currentTarget.closest('[data-workspace-layer="workspace"]');
    workspace?.querySelectorAll<HTMLDetailsElement>('[data-workspace-layer="disclosure"][open]').forEach(other => { if (other !== event.currentTarget) other.open = false; });
  }} data-workspace-layer="disclosure" className={cn("relative shrink-0", className)} onKeyDown={event => {
    if (event.key === "Escape" && ref.current?.open) { event.stopPropagation(); ref.current.open = false; ref.current.querySelector("summary")?.focus(); }
  }}><Button asChild size="sm" variant="ghost"><summary role="button" aria-expanded={expanded} aria-controls={contentId} className="list-none [&::-webkit-details-marker]:hidden">{label}</summary></Button>
    <Surface asChild variant="floating"><div id={contentId} className={cn("absolute right-0 top-full z-30 mt-2 max-h-[70vh] w-80 max-w-[calc(100vw-2rem)] overflow-auto p-4", contentClassName)}>{children}</div></Surface>
  </details>;
}

/** Quiet corner affordance; geometry and persistence remain with the canvas owner. */
export function CanvasResizeHandle({ label, hint, className, ...props }: Omit<React.ComponentProps<typeof Button>, "children" | "aria-label" | "variant" | "size"> & { label: string; hint?: string }): React.JSX.Element {
  return <Button variant="ghost" size="icon" type="button" data-slot="canvas-resize-handle" aria-label={label} title={hint} className={cn("ui-canvas-resize", className)} {...props}><MoveDiagonal2 aria-hidden className="size-3.5" /></Button>;
}
