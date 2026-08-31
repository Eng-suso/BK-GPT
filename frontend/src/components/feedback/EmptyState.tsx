import type { ComponentType, ReactNode } from "react";
import { Inbox } from "lucide-react";

import { cn } from "@/lib/utils";

export type EmptyStateProps = {
  title: string;
  description?: string;
  icon?: ComponentType<{ className?: string }>;
  /** Optional action (button / link). */
  action?: ReactNode;
  /** "block" fills a card area and centres; "inline" left-aligns for panels. */
  variant?: "block" | "inline";
  className?: string;
};

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
  variant = "block",
  className,
}: EmptyStateProps): React.JSX.Element {
  if (variant === "inline") {
    return (
      <div className={cn("flex flex-col items-start gap-1.5 py-3.5", className)}>
        <h4 className="text-xs font-semibold text-muted-foreground">{title}</h4>
        {description && (
          <p className="max-w-[300px] text-xs leading-relaxed text-muted-foreground/80">
            {description}
          </p>
        )}
        {action && <div className="mt-1">{action}</div>}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col items-center gap-2.5 px-6 py-9 text-center",
        className,
      )}
    >
      <div className="grid size-10 place-items-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="size-5" />
      </div>
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      {description && (
        <p className="max-w-[280px] text-xs text-muted-foreground">
          {description}
        </p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
