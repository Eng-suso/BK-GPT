import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

export type Crumb = {
  label: string;
  /** Omit on the last crumb (current page). */
  to?: string;
};

export type PageHeaderProps = {
  breadcrumbs?: Crumb[];
  title: string;
  /** Optional short lead paragraph under the title. */
  description?: string;
  /** Inline meta row under the title (client, status, phase…). */
  meta?: ReactNode;
  /** Inline count shown next to the title (e.g. total rows). */
  count?: number | string;
  /** Right-aligned action slot (buttons, menus). */
  actions?: ReactNode;
  className?: string;
};

export function PageHeader({
  breadcrumbs,
  title,
  description,
  meta,
  count,
  actions,
  className,
}: PageHeaderProps): React.JSX.Element {
  return (
    <header className={cn("flex flex-col gap-4", className)}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav aria-label="Breadcrumb">
          <ol className="flex items-center gap-1.5 text-xs text-muted-foreground">
            {breadcrumbs.map((crumb, i) => {
              const isLast = i === breadcrumbs.length - 1;
              return (
                <li key={crumb.label} className="flex items-center gap-1.5">
                  {crumb.to && !isLast ? (
                    <Link to={crumb.to} className="hover:text-foreground">
                      {crumb.label}
                    </Link>
                  ) : (
                    <span className={cn(isLast && "text-foreground/80")}>
                      {crumb.label}
                    </span>
                  )}
                  {!isLast && (
                    <ChevronRight className="size-3 text-muted-foreground/70" />
                  )}
                </li>
              );
            })}
          </ol>
        </nav>
      )}

      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-baseline gap-2.5">
            <h1 className="text-2xl font-semibold tracking-[-0.03em] text-foreground">
              {title}
            </h1>
            {count !== undefined && (
              <span className="text-sm font-normal text-muted-foreground tabular-nums">
                {count}
              </span>
            )}
          </div>
          {description && (
            <p className="mt-1.5 max-w-xl text-[13px] leading-relaxed text-muted-foreground">
              {description}
            </p>
          )}
          {meta && (
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {meta}
            </div>
          )}
        </div>
        {actions && (
          <div className="flex flex-shrink-0 items-center gap-2">{actions}</div>
        )}
      </div>
    </header>
  );
}
