import { useId, type KeyboardEvent } from "react";
import { Plus, X } from "lucide-react";

import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
import { Button } from "@/ui/button";

type ListFieldProps = {
  label: string;
  hint?: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  addLabel: string;
  /** Etichetta accessibile del pulsante di rimozione, senza la voce. */
  removeLabel: string;
  emptyLabel: string;
};

/**
 * Provides a controlled editor for a list of string values.
 *
 * Pressing Enter inserts a new empty row after the current row without submitting
 * the surrounding form.
 *
 * @param label - The field's accessible label
 * @param hint - Optional descriptive text displayed below the field
 * @param values - The current list of values
 * @param onChange - Called with the updated list when values are added, edited, or removed
 * @param placeholder - Optional placeholder text for each input
 * @param addLabel - Label for the button that adds an empty row
 * @param removeLabel - Label prefix for each row's remove button
 * @param emptyLabel - Message displayed when the list has no values
 */
export function ListField({
  label,
  hint,
  values,
  onChange,
  placeholder,
  addLabel,
  removeLabel,
  emptyLabel,
}: ListFieldProps): React.JSX.Element {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;

  const setAt = (index: number, value: string) =>
    onChange(values.map((item, i) => (i === index ? value : item)));

  const removeAt = (index: number) =>
    onChange(values.filter((_, i) => i !== index));

  const insertAfter = (index: number) =>
    onChange([...values.slice(0, index + 1), "", ...values.slice(index + 1)]);

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>, index: number) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    insertAfter(index);
  };

  return (
    <fieldset className="flex flex-col gap-1.5" aria-describedby={hintId}>
      <Label asChild className="text-xs font-medium text-foreground">
        <legend>{label}</legend>
      </Label>

      {values.length === 0 ? (
        <p className="py-1 text-micro text-muted-foreground">{emptyLabel}</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {values.map((value, index) => (
            // L'indice e' l'identita' della riga: due voci possono avere lo
            // stesso testo mentre si scrive, e una riga nuova nasce vuota.
            <li key={index} className="flex items-center gap-1.5">
              <Input
                value={value}
                placeholder={placeholder}
                aria-label={`${label} ${index + 1}`}
                onChange={(event) => setAt(index, event.target.value)}
                onKeyDown={(event) => handleKeyDown(event, index)}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8 flex-none text-muted-foreground"
                aria-label={`${removeLabel}: ${value || index + 1}`}
                onClick={() => removeAt(index)}
              >
                <X />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange([...values, ""])}
        >
          <Plus /> {addLabel}
        </Button>
      </div>

      {hint ? (
        <p id={hintId} className="text-micro text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </fieldset>
  );
}
