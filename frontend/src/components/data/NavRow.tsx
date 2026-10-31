import * as React from "react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";

export type NavRowProps = {
  /** Primary line. */
  title: React.ReactNode;
  /** Secondary muted line under the title. */
  meta?: React.ReactNode;
  /** Right-aligned slot: status indicator, progress, chevron… */
  trailing?: React.ReactNode;
  /** Render as a router link. Takes precedence over `onClick`. */
  to?: string;
  /** Render as a button when there is no `to`. */
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
  titleClassName?: string;
};

/**
 * Clickable list row used inside bordered section cards (home dashboard,
 * project detail overview / processes). One reproducible shape so every
 * navigable list reads the same.
 */
export function NavRow({
  title,
  meta,
  trailing,
  to,
  onClick,
  disabled,
  className,
  titleClassName,
}: NavRowProps): React.JSX.Element {
  const body = (
    <>
      <span className="min-w-0">
        <span
          className={cn(
            "block truncate text-sm font-medium text-foreground",
            titleClassName,
          )}
        >
          {title}
        </span>
        {meta != null && (
          <span className="mt-1 block truncate text-xs leading-5 text-muted-foreground">
            {meta}
          </span>
        )}
      </span>
      {trailing != null && (
        <span className="flex flex-none items-center gap-2">{trailing}</span>
      )}
    </>
  );

  const shared = cn(
    "flex min-h-14 items-center justify-between gap-3 border-b border-border/60 px-4 py-3 text-left outline-none transition-colors duration-150 last:border-b-0 hover:bg-muted/60 active:bg-muted focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none",
    disabled && "pointer-events-none opacity-40",
    className,
  );

  if (to) {
    return (
      <Link to={to} className={shared}>
        {body}
      </Link>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(shared, "w-full")}
    >
      {body}
    </button>
  );
}
