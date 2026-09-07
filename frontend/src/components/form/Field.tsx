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
 * Groups a label, form control, and optional hint with accessible associations.
 *
 * @param hint - Optional explanatory text linked to the control.
 * @param children - Function that renders the control with generated accessibility attributes.
 * @returns The grouped field markup.
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
