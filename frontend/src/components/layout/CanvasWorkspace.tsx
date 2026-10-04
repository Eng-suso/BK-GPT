import React from "react";
import { X } from "lucide-react";
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
export function CanvasWorkspaceShell({ label, commands, children, inspector, playback, className, bodyClassName, stageClassName }: { label: string; commands?: Slot; children: Slot; inspector?: Slot; playback?: Slot; className?: string; bodyClassName?: string; stageClassName?: string }): React.JSX.Element {
  return <section data-workspace-layer="workspace" aria-label={label} className={cn("flex h-full min-h-0 min-w-0 flex-col gap-2", className)}>
    <h2 className="sr-only">{label}</h2>{commands}<div data-workspace-layer="body" className={cn("flex min-h-0 min-w-0 flex-1 gap-3", bodyClassName)}>
      <div data-workspace-layer="stage" className={cn("relative flex min-h-0 min-w-0 flex-1 flex-col", stageClassName)}>{children}</div>{inspector}
    </div>{playback && <Surface asChild variant="toolbar"><div data-workspace-layer="playback" className="shrink-0">{playback}</div></Surface>}
  </section>;
}

export const WorkspaceInspector = React.forwardRef<HTMLElement, { label: string; title: string; scope?: string; closeLabel: string; onClose: () => void; children: Slot; hidden?: boolean; className?: string; bodyClassName?: string }>(({ label, title, scope, closeLabel, onClose, children, hidden, className, bodyClassName }, ref) =>
  <Surface asChild variant="panel"><aside ref={ref} hidden={hidden} aria-label={label} data-workspace-layer="inspector" className={cn("flex min-h-0 shrink-0 flex-col overflow-hidden", className)} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }}>
    <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3"><div className="min-w-0">{scope && <p className="text-xs text-muted-foreground">{scope}</p>}<h2 data-dock-title tabIndex={-1} className="text-sm font-semibold focus-visible:outline-2 focus-visible:outline-ring">{title}</h2></div><Button size="icon" variant="ghost" onClick={onClose} aria-label={closeLabel}><X aria-hidden className="size-4" /></Button></header>
    <div className={cn("min-h-0 flex-1 overflow-auto p-4", bodyClassName)}>{children}</div>
  </aside></Surface>);
WorkspaceInspector.displayName = "WorkspaceInspector";

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
