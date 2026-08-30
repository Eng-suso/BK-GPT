import type { ReactNode } from "react";
import { TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";

export type ErrorStateProps = {
  title?: string;
  description?: string;
  onRetry?: () => void;
  retryLabel?: string;
  action?: ReactNode;
  className?: string;
};

export function ErrorState({
  title = "Si è verificato un errore",
  description = "Non è stato possibile caricare i dati. Riprova.",
  onRetry,
  retryLabel = "Riprova",
  action,
  className,
}: ErrorStateProps): React.JSX.Element {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center gap-2.5 px-6 py-9 text-center",
        className,
      )}
    >
      <div className="grid size-10 place-items-center rounded-[9px] bg-[var(--red-50)] text-[var(--color-status-danger)]">
        <TriangleAlert className="size-5" />
      </div>
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      <p className="max-w-[300px] text-xs text-muted-foreground">{description}</p>
      {(onRetry || action) && (
        <div className="mt-1 flex items-center gap-2">
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              {retryLabel}
            </Button>
          )}
          {action}
        </div>
      )}
    </div>
  );
}
