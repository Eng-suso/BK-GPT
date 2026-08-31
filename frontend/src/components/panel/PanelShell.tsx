import type { ElementType, ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The one bordered workspace surface. Every panel in the projects / process /
 * simulation / chat area is a `PanelShell` with a `PanelShellHeader` — same
 * border, radius, shadow and 56px header everywhere, instead of five
 * slightly-different hand-rolled shells.
 *
 * Compose:
 *   <PanelShell aria-label="Canvas BPMN">
 *     <PanelShellHeader eyebrow="BPMN 2.0" title="Canvas" actions={…} />
 *     <div className="min-h-0 flex-1 overflow-auto">…</div>
 *   </PanelShell>
 */
export function PanelShell({
  as: Tag = "section",
  className,
  children,
  ...rest
}: {
  as?: ElementType;
  className?: string;
  children: ReactNode;
} & React.HTMLAttributes<HTMLElement>): React.JSX.Element {
  return (
    <Tag
      className={cn(
        "flex min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-card shadow-[0_1px_2px_var(--shadow-100)]",
        className,
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
}

export function PanelShellHeader({
  eyebrow,
  title,
  status,
  actions,
  className,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  /** Right-aligned status chip, shown before the actions. */
  status?: ReactNode;
  /** Right-aligned action slot (buttons, menus). */
  actions?: ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <header
      className={cn(
        "flex min-h-[var(--inspector-header-height)] shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow != null && <p className="eyebrow">{eyebrow}</p>}
        <h3 className="mt-0.5 truncate text-sm font-semibold text-foreground">
          {title}
        </h3>
      </div>
      {(status != null || actions != null) && (
        <div className="flex shrink-0 items-center gap-2">
          {status}
          {actions}
        </div>
      )}
    </header>
  );
}
