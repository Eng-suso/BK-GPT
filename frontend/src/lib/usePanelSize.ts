import { useCallback, useState } from "react";

/**
 * A pixel size for a resizable panel, clamped to [min, max] and remembered in
 * localStorage under `delir-panel:{key}`. Best-effort — storage failures fall
 * back to the in-memory value.
 */
export function usePanelSize(
  key: string,
  initial: number,
  min: number,
  max: number,
): readonly [number, (next: number) => void] {
  const [size, setSize] = useState<number>(() => {
    try {
      const stored = Number(window.localStorage.getItem(`delir-panel:${key}`));
      if (Number.isFinite(stored) && stored >= min && stored <= max) return stored;
    } catch {
      /* storage unavailable */
    }
    return initial;
  });

  const set = useCallback(
    (next: number) => {
      const clamped = Math.max(min, Math.min(max, Math.round(next)));
      setSize(clamped);
      try {
        window.localStorage.setItem(`delir-panel:${key}`, String(clamped));
      } catch {
        /* storage unavailable */
      }
    },
    [key, min, max],
  );

  return [size, set] as const;
}
