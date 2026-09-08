import type { ReactNode } from "react";
import { CircleAlert, Info } from "lucide-react";
import { cn } from "@/lib/utils";

/** Compact operational feedback; the action stays with the message. */
export function InlineNotice({
  title,
  children,
  action,
  tone = "info",
  className,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  tone?: "info" | "warning" | "error";
  className?: string;
}) {
  const Icon = tone === "info" ? Info : CircleAlert;
  return (
    <section
      role={tone === "error" ? "alert" : "status"}
      className={cn("ui-inline-notice", className)}
      data-tone={tone}
    >
      <Icon className="ui-inline-notice-icon size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-foreground">{title}</p>
        {children && <div className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{children}</div>}
      </div>
      {action && <div className="ui-inline-notice-action">{action}</div>}
    </section>
  );
}
