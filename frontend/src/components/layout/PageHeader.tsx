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
  compact?: boolean;
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

/**
 * Renders a page header with optional breadcrumbs, description, metadata, count, and actions.
 *
 * @param compact - Whether to use reduced spacing and a smaller title.
 * @returns The rendered page header.
 */
export function PageHeader({
  compact = false,
  breadcrumbs,
  title,
  description,
  meta,
  count,
  actions,
  className,
}: PageHeaderProps): React.JSX.Element {
  return (
    <header className={cn("flex min-w-0 flex-col", compact ? "gap-2" : "gap-4", className)}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav aria-label="Breadcrumb">
          <ol className="flex min-w-0 items-center gap-1.5 overflow-hidden text-xs text-muted-foreground">
            {breadcrumbs.map((crumb, i) => {
              const isLast = i === breadcrumbs.length - 1;
              return (
                <li key={crumb.label} className="flex min-w-0 items-center gap-1.5 [&>a]:truncate [&>span]:truncate [&>svg]:shrink-0">
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

      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2.5">
            <h1 className={cn("font-semibold tracking-[-0.03em] text-foreground", compact ? "text-lg leading-6" : "text-2xl")}>
              {title}
            </h1>
            {count !== undefined && (
              <span className="text-sm font-normal text-muted-foreground tabular-nums">
                {count}
              </span>
            )}
          </div>
          {description && (
            <p className="mt-1.5 max-w-xl text-body-sm leading-relaxed text-muted-foreground">
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
          <div className="flex max-w-full flex-shrink-0 flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
    </header>
  );
}
