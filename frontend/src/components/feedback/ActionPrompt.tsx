import type { ReactNode } from "react";
import { X } from "lucide-react";
import { Surface } from "@/ui/surface";
import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";

/** A persistent next step, with context and an action in one shared surface. */
export function ActionPrompt({ label, title, children, meta, icon, action, dismissLabel, onDismiss, className }: {
  label: string;
  title: string;
  children?: ReactNode;
  meta?: ReactNode;
  icon: ReactNode;
  action?: ReactNode;
  dismissLabel: string;
  onDismiss: () => void;
  className?: string;
}) {
  return <Surface asChild variant="workspace"><section role="region" aria-label={label} className={cn("ui-action-prompt", className)}>
    <span className="ui-action-prompt-icon" aria-hidden="true">{icon}</span>
    <div className="ui-action-prompt-copy">
      {meta && <span className="ui-action-prompt-meta">{meta}</span>}
      <p>{title}</p>
      {children && <div>{children}</div>}
    </div>
    {action && <div className="ui-action-prompt-action">{action}</div>}
    <Button className="ui-action-prompt-dismiss" type="button" variant="ghost" size="icon-sm" aria-label={dismissLabel} onClick={onDismiss}><X aria-hidden="true" /></Button>
  </section></Surface>;
}
