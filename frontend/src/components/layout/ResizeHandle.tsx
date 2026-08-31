import React from "react";

import { cn } from "@/lib/utils";

type ResizeHandleProps = {
  /** Fired once when a pointer drag begins — snapshot the current size here. */
  onResizeStart?: () => void;
  /** Called with the horizontal pointer delta (px) since the drag started. */
  onDelta: (deltaX: number) => void;
  /**
   * Called with a signed px step from an arrow key (±`step`, ±`step * 4` with
   * Shift). Wire this to add the delta to the current size. Falls back to
   * `onResizeStart` + `onDelta` when omitted.
   */
  onStep?: (deltaX: number) => void;
  ariaLabel: string;
  /** Current / min / max panel px — exposed to assistive tech as a slider. */
  valueNow?: number;
  valueMin?: number;
  valueMax?: number;
  /** px moved per arrow keypress (Shift = 4×). Default 16. */
  step?: number;
  className?: string;
};

/**
 * Vertical drag divider for side-by-side panels. Emits a cumulative pointer
 * delta; the parent maps it onto a panel width (see `usePanelSize`). Also
 * keyboard-operable: focus it and use ←/→ (Shift for a bigger jump).
 * Uses the shared `.workspace-splitter` / `.splitter-line` styles.
 */
export function ResizeHandle({
  onResizeStart,
  onDelta,
  onStep,
  ariaLabel,
  valueNow,
  valueMin,
  valueMax,
  step = 16,
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

  const nudge = (deltaX: number) => {
    if (onStep) {
      onStep(deltaX);
      return;
    }
    onResizeStart?.();
    onDelta(deltaX);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const jump = e.shiftKey ? step * 4 : step;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      nudge(-jump);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      nudge(jump);
    } else if (e.key === "Home" && valueNow !== undefined && valueMin !== undefined) {
      e.preventDefault();
      nudge(valueMin - valueNow);
    } else if (e.key === "End" && valueNow !== undefined && valueMax !== undefined) {
      e.preventDefault();
      nudge(valueMax - valueNow);
    }
  };

  return (
    <div
      role="separator"
      tabIndex={0}
      aria-orientation="vertical"
      aria-label={ariaLabel}
      aria-valuenow={valueNow}
      aria-valuemin={valueMin}
      aria-valuemax={valueMax}
      className={cn("workspace-splitter", active && "is-active", className)}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={handleKeyDown}
    >
      <div className="splitter-line" />
    </div>
  );
}
