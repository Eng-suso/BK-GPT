import type { ComponentProps, ReactNode } from "react";
import { Button } from "@/ui/button";
import { Surface } from "@/ui/surface";
import { cn } from "@/lib/utils";

/** Shared hit area and states for tools on editing and reading canvases. */
export function CanvasToolButton({ label, active, children, className, ...props }: Omit<ComponentProps<typeof Button>, "size" | "variant" | "aria-label"> & { label: string; active?: boolean }) {
  return <Button type="button" size="icon" variant="ghost" aria-label={label} title={label} aria-pressed={active} className={cn("ui-canvas-tool", className)} {...props}>{children}</Button>;
}

export function CanvasToolGroup({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return <Surface variant="floating" role="group" aria-label={label} className={cn("ui-canvas-tools", className)}>{children}</Surface>;
}
