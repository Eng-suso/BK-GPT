import { ToggleGroup } from "radix-ui";

/** Exclusive display modes share a surface without claiming separate tab panels. */
export function SegmentedControl({ label, value, options, onValueChange }: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onValueChange: (value: string) => void;
}) {
  return <ToggleGroup.Root type="single" value={value} onValueChange={next => { if (next) onValueChange(next); }} aria-label={label} className="ui-segmented inline-flex w-fit items-center rounded-full p-[3px]">
    {options.map(option => <ToggleGroup.Item key={option.value} value={option.value} className="min-h-8 rounded-full border border-transparent px-3 text-sm font-medium text-muted-foreground transition-colors duration-200 hover:text-foreground data-[state=on]:text-foreground focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none">{option.label}</ToggleGroup.Item>)}
  </ToggleGroup.Root>;
}
