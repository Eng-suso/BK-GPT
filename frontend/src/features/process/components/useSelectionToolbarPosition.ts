import { useLayoutEffect, useRef, useState, type RefObject } from "react";

/** Keep contextual actions beside the selection in canvas coordinates. */
export function useSelectionToolbarPosition(host: RefObject<HTMLDivElement | null>, geometryKey: string, selectedId: string | undefined, enabled: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: 8, top: 12 });
  useLayoutEffect(() => {
    const canvas = host.current, toolbar = ref.current;
    if (!enabled || !canvas || !toolbar) return;
    let frame = 0;
    const measure = () => {
      const bounds = canvas.getBoundingClientRect();
      const body = selectedId ? canvas.querySelector(`[data-element-id="${CSS.escape(selectedId)}"] .djs-visual > :first-child`) : null;
      const shape = body?.getBoundingClientRect();
      const minimumTop = matchMedia("(max-width:620px)").matches ? 72 : 8;
      const left = Math.max(8, Math.min(bounds.width - toolbar.offsetWidth - 8, shape ? shape.right - bounds.left - toolbar.offsetWidth : 8));
      const top = Math.max(minimumTop, Math.min(bounds.height - toolbar.offsetHeight - 8, shape ? shape.top - bounds.top - toolbar.offsetHeight - 12 : minimumTop));
      setPosition(previous => previous.left === left && previous.top === top ? previous : { left, top });
    };
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    measure();
    const observer = new ResizeObserver(schedule);
    observer.observe(canvas); observer.observe(toolbar);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, [host, geometryKey, selectedId, enabled]);
  return { ref, position };
}
