import { type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";
import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";

type FormDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Cosa cambia salvando. Letta dagli screen reader insieme al titolo. */
  description?: string;
  submitLabel: string;
  isSubmitting: boolean;
  /** Messaggio dell'errore di salvataggio, gia' tradotto. */
  error?: string | null;
  onSubmit: () => void;
  children: ReactNode;
  className?: string;
};

/**
 * Renders a reusable dialog for workspace record forms.
 *
 * Keeps the dialog actions disabled during submission, displays submission errors,
 * and provides a scrollable area for form content.
 *
 * @param isSubmitting - Whether a submission is currently in progress
 * @param error - An optional error message to display in the form
 * @param onSubmit - Called when the form is submitted
 */
export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  isSubmitting,
  error,
  onSubmit,
  children,
  className,
}: FormDialogProps): React.JSX.Element {
  const { t } = useTranslation("common");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isSubmitting) return;
    onSubmit();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* `flex` sostituisce il `grid` del primitive: in griglia la riga si
          dimensiona sul contenuto, il form sfondava il `max-h` del dialog e il
          corpo non scrollava mai — su un form lungo il footer finiva fuori
          schermo. In colonna flex il corpo prende lo spazio che resta. */}
      <DialogContent
        className={cn(
          "flex max-h-[min(90vh,44rem)] flex-col gap-0 p-0 sm:max-w-xl",
          className,
        )}
      >
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogHeader className="gap-1 border-b border-border px-6 py-4">
            <DialogTitle className="text-body">{title}</DialogTitle>
            {description ? (
              <DialogDescription className="text-xs">
                {description}
              </DialogDescription>
            ) : null}
          </DialogHeader>

          <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-6 py-5">
            {children}
          </div>

          <DialogFooter className="items-center border-t border-border px-6 py-4 sm:justify-between">
            <p
              role="alert"
              aria-live="polite"
              className={cn(
                "min-h-4 text-left text-xs",
                error ? "text-[var(--color-status-danger)]" : "sr-only",
              )}
            >
              {error ?? ""}
            </p>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
              >
                {t("actions.cancel")}
              </Button>
              <Button type="submit" size="sm" disabled={isSubmitting}>
                {isSubmitting ? t("state.loading") : submitLabel}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
