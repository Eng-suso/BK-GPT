import { useId, type ReactNode } from "react";

import { Label } from "@/ui/label";

export type FieldControlProps = {
  id: string;
  "aria-describedby": string | undefined;
  "aria-required": boolean | undefined;
};

type FieldProps = {
  label: string;
  /** Perche' il campo esiste, o cosa ci si aspetta dentro. */
  hint?: string;
  required?: boolean;
  children: (props: FieldControlProps) => ReactNode;
};

/**
 * Etichetta, controllo e spiegazione, legati fra loro.
 *
 * L'`id` non lo sceglie il chiamante: il campo lo genera e lo passa al
 * controllo insieme all'`aria-describedby` del suo hint, cosi' un lettore di
 * schermo sente l'etichetta *e* il motivo del campo, e nessun form puo'
 * dimenticarsi il collegamento.
 */
export function Field({
  label,
  hint,
  required,
  children,
}: FieldProps): React.JSX.Element {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id} className="text-xs font-medium text-foreground">
        {label}
        {required ? (
          <span aria-hidden className="text-[var(--color-status-danger)]">
            *
          </span>
        ) : null}
      </Label>
      {children({
        id,
        "aria-describedby": hintId,
        "aria-required": required || undefined,
      })}
      {hint ? (
        <p id={hintId} className="text-micro text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
