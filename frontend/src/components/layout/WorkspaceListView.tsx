import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Standard workspace list screen: a scrolling main column
 * (page header + toolbar + table) beside an optional right detail panel.
 * The panel is hidden below `xl`.
 */
export function WorkspaceListView({
  header,
  toolbar,
  children,
  detail,
  className,
}: {
  header: ReactNode;
  toolbar?: ReactNode;
  /** The table area (DataTable, or an ErrorState wrapper). */
  children: ReactNode;
  /** A <DetailPanel> element, or null. */
  detail?: ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <div
      className={cn(
        "grid h-full min-h-0 grid-cols-1",
        detail && "xl:grid-cols-[minmax(0,1fr)_344px]",
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-4 overflow-hidden px-7 py-6">
        {header}
        {toolbar}
        {children}
      </div>
      {detail}
    </div>
  );
}
