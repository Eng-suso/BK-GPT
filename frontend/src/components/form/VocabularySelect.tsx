import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";
import { cn } from "@/lib/utils";

export type VocabularyOption = {
  value: string;
  label: string;
  /** Cosa significa questa voce. E' il motivo per cui il campo e' un vocabolario. */
  meaning?: string;
};

type VocabularySelectProps = {
  value: string;
  onChange: (value: string) => void;
  options: VocabularyOption[];
  placeholder?: string;
  id?: string;
  "aria-describedby"?: string;
  "aria-required"?: boolean;
  className?: string;
};

/**
 * Renders a closed-vocabulary select control with explanatory meanings for its options.
 *
 * Preserves a nonempty value that is absent from the supplied options by displaying it as
 * the current option.
 *
 * @returns The rendered vocabulary select control
 */
export function VocabularySelect({
  value,
  onChange,
  options,
  placeholder,
  className,
  ...aria
}: VocabularySelectProps): React.JSX.Element {
  const known = options.some((option) => option.value === value);
  const entries = known || !value ? options : [{ value, label: value }, ...options];
  const selected = entries.find((option) => option.value === value);

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger {...aria} className={cn("w-full", className)}>
        {/* Solo l'etichetta nel trigger: la definizione serve mentre si sceglie,
            non dopo aver scelto, e in un controllo a riga singola sfonderebbe. */}
        <SelectValue placeholder={placeholder}>{selected?.label}</SelectValue>
      </SelectTrigger>
      <SelectContent className="max-w-[min(28rem,calc(100vw-2rem))]">
        {entries.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            <span className="flex min-w-0 flex-col gap-0.5 py-0.5">
              <span className="text-body-sm text-foreground">{option.label}</span>
              {option.meaning ? (
                <span className="text-micro text-wrap text-muted-foreground">
                  {option.meaning}
                </span>
              ) : null}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
