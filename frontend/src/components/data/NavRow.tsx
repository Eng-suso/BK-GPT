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
            "block truncate text-[12.5px] font-medium text-foreground",
            titleClassName,
          )}
        >
          {title}
        </span>
        {meta != null && (
          <span className="block truncate text-[11.5px] text-muted-foreground">
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
    "flex items-center justify-between gap-3 border-b border-border/60 px-4 py-2.5 text-left transition-colors last:border-b-0 hover:bg-muted/40",
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
