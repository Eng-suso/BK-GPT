import type { ReactNode } from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Right-hand context panel. Hairline-separated sections, no nested cards.
 * See docs/design/ (Main / ProjectDetail artboards).
 */
export function DetailPanel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <aside
      className={cn(
        "flex flex-col overflow-hidden border-l border-border bg-card px-5 pt-5",
        "shadow-[-16px_0_40px_-24px_rgba(14,20,32,0.10)]",
        className,
      )}
    >
      {children}
    </aside>
  );
}

export function DetailPanelHeader({
  title,
  subtitle,
  onClose,
}: {
  title: string;
  subtitle?: string;
  onClose?: () => void;
}): React.JSX.Element {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
      <div>
        <h3 className="text-[15.5px] font-semibold tracking-[-0.02em] text-foreground">
          {title}
        </h3>
        {subtitle && (
          <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
        )}
      </div>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Chiudi pannello"
          className="grid size-[26px] place-items-center rounded-[7px] text-muted-foreground hover:bg-muted"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}

export function DetailPanelSection({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}): React.JSX.Element {
  return (
    <section className="border-t border-border/70 py-4 first:border-t-0">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="eyebrow">{title}</h4>
        {action}
      </div>
      {children}
    </section>
  );
}

export type DetailRow = {
  label: string;
  value: ReactNode;
};

export function DetailPanelKeyValue({
  rows,
}: {
  rows: DetailRow[];
}): React.JSX.Element {
  return (
    <dl className="flex flex-col">
      {rows.map((row, i) => (
        <div
          key={row.label}
          className={cn(
            "flex items-baseline justify-between gap-3 py-2 text-xs",
            i < rows.length - 1 && "border-b border-border/60",
          )}
        >
          <dt className="text-muted-foreground">{row.label}</dt>
          <dd className="m-0 text-right font-medium text-foreground">
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
