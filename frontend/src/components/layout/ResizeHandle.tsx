import React from "react";

import { cn } from "@/lib/utils";

type ResizeHandleProps = {
  /** Fired once when a drag begins — snapshot the current size here. */
  onResizeStart?: () => void;
  /** Called with the horizontal pointer delta (px) since the drag started. */
  onDelta: (deltaX: number) => void;
  ariaLabel: string;
  className?: string;
};

/**
 * Vertical drag divider for side-by-side panels. Emits a cumulative pointer
 * delta; the parent maps it onto a panel width (see `usePanelSize`).
 * Uses the shared `.workspace-splitter` / `.splitter-line` styles.
 */
export function ResizeHandle({
  onResizeStart,
  onDelta,
  ariaLabel,
  className,
}: ResizeHandleProps): React.JSX.Element {
  const startX = React.useRef<number | null>(null);
  const [active, setActive] = React.useState(false);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    startX.current = e.clientX;
    setActive(true);
    onResizeStart?.();
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (startX.current === null) return;
    onDelta(e.clientX - startX.current);
  };

  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (startX.current === null) return;
    startX.current = null;
    setActive(false);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={ariaLabel}
      className={cn("workspace-splitter", active && "is-active", className)}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
    >
      <div className="splitter-line" />
    </div>
  );
}
