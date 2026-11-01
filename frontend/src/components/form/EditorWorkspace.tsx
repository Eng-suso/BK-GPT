import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** One scrolling form body between persistent navigation and actions. */
export function EditorWorkspace({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("ui-editor-workspace", className)} {...props} />;
}

export function EditorBody({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("ui-editor-body ui-scrollbar", className)} {...props} />;
}

export function EditorActions({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("ui-editor-actions", className)} {...props} />;
}
