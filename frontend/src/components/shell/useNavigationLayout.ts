import { useEffect, useState } from "react";

const STORAGE_KEY = "delir-navigation-layout";
const WIDTH = { default: 272, minimum: 224, maximum: 384 };
type NavigationLayout = { collapsed: boolean | null; width: number };
const clamp = (width: number) => Math.max(WIDTH.minimum, Math.min(WIDTH.maximum, width));

function readLayout(): NavigationLayout {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    return {
      collapsed: typeof saved?.collapsed === "boolean" ? saved.collapsed : null,
      width: typeof saved?.width === "number" && Number.isFinite(saved.width) ? clamp(saved.width) : WIDTH.default,
    };
  } catch {
    return { collapsed: null, width: WIDTH.default };
  }
}

/** The same preference follows the user between product sections. */
export function useNavigationLayout(defaultCollapsed: boolean) {
  const [layout, setLayout] = useState(readLayout);
  const collapsed = layout.collapsed ?? defaultCollapsed;
  useEffect(() => {
    // Keep synchronous storage writes out of the pointer-move path.
    const timer = window.setTimeout(() => {
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(layout)); } catch { /* Session still works without storage. */ }
    }, 180);
    return () => window.clearTimeout(timer);
  }, [layout]);
  return {
    collapsed,
    width: layout.width,
    minimum: WIDTH.minimum,
    maximum: WIDTH.maximum,
    toggle: () => setLayout(previous => ({ ...previous, collapsed: !collapsed })),
    resize: (width: number) => setLayout(previous => ({ ...previous, width: clamp(width) })),
  };
}
